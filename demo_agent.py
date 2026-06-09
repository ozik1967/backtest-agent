"""
Demo: Full AI agent cycle using ERC-8004 + x402.

This script demonstrates an autonomous AI agent that:
  1. Discovers the service via Agent Card
  2. Probes the API → receives HTTP 402 with payment details
  3. Pays 0.01 MNT on Mantle Sepolia (x402)
  4. Retries with X-Payment header → receives backtest results
  5. Submits on-chain feedback to ERC-8004 ReputationRegistry (Mantle Mainnet)

Two wallets involved:
  PRIVATE_KEY        — pays for the service (Mantle Sepolia, 0.01 MNT)
  CLIENT_PRIVATE_KEY — submits reputation feedback (Mantle Mainnet, ~0.001 MNT gas)
  (can be the same key if funded on both networks)

Requirements:
  pip install web3 requests

Usage:
  PRIVATE_KEY=0x<key> CLIENT_PRIVATE_KEY=0x<key> python demo_agent.py
"""

import os
import sys
import requests
from web3 import Web3

# ── Config ────────────────────────────────────────────────────────────────────
AGENT_CARD_URL  = "https://alphaterminal.live/agent-card.json"
API_BASE        = "https://alphaterminal.live/api"
SEPOLIA_RPC     = "https://rpc.sepolia.mantle.xyz"   # payment network
MAINNET_RPC     = "https://rpc.mantle.xyz"            # reputation network

REPUTATION_REGISTRY = "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63"
AGENT_ID            = 113

PRIVATE_KEY        = os.getenv("PRIVATE_KEY",        "0x...")
CLIENT_PRIVATE_KEY = os.getenv("CLIENT_PRIVATE_KEY", PRIVATE_KEY)  # default: same key

BACKTEST_PARAMS = {
    "ticker":      "BTCUSDT",
    "strategy":    "MACD",
    "timeframe":   "1h",
    "depth_days":  90,
    "deposit":     1000,
    "margin_pct":  10,
    "leverage":    10,
    "sl_pct":      2,
    "tp_pct":      4,
    "direction":   "BOTH",
    "macd_fast":   12,
    "macd_slow":   26,
    "macd_signal": 9,
}

# Minimal ABI for giveFeedback
REPUTATION_ABI = [
    {
        "name": "giveFeedback",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "agentId",       "type": "uint256"},
            {"name": "value",         "type": "int128"},
            {"name": "valueDecimals", "type": "uint8"},
            {"name": "tag1",          "type": "string"},
            {"name": "tag2",          "type": "string"},
            {"name": "endpoint",      "type": "string"},
            {"name": "feedbackURI",   "type": "string"},
            {"name": "feedbackHash",  "type": "bytes32"},
        ],
        "outputs": [],
    },
]


# ── Step 1: Read Agent Card ────────────────────────────────────────────────────
def step1_read_agent_card() -> dict:
    print("Step 1: Reading Agent Card...")
    resp = requests.get(AGENT_CARD_URL, timeout=10)
    card = resp.json()
    print(f"  Agent    : {card['name']}")
    print(f"  Endpoint : {card['services'][0]['endpoint']}")
    print(f"  x402     : {card.get('x402Support', False)}")
    print(f"  Payment  : {card.get('paymentAmount')} {card.get('paymentToken')}")
    return card


# ── Step 2: Probe — discover payment requirements ─────────────────────────────
def step2_probe() -> dict:
    print("\nStep 2: Probing API (no payment)...")
    resp = requests.post(f"{API_BASE}/backtest", json=BACKTEST_PARAMS, timeout=15)
    print(f"  HTTP {resp.status_code}")
    if resp.status_code != 402:
        print(f"  Unexpected: {resp.text[:200]}")
        sys.exit(1)
    payment = resp.json()["payment"]
    print(f"  Required : {int(payment['amount']) / 1e18} {payment['currency']} → {payment['to']}")
    print(f"  Reason   : {payment['reason']}")
    return payment


# ── Step 3: Pay on Mantle Sepolia ─────────────────────────────────────────────
def step3_pay(payment: dict) -> str:
    print("\nStep 3: Sending payment (Mantle Sepolia)...")

    if PRIVATE_KEY == "0x...":
        print("  ⚠  PRIVATE_KEY not set — skipping real payment.")
        print("     Set PRIVATE_KEY env var for end-to-end demo.")
        return "0x" + "ab" * 32   # placeholder, will fail verification

    w3 = Web3(Web3.HTTPProvider(SEPOLIA_RPC))
    account = w3.eth.account.from_key(PRIVATE_KEY)
    balance = w3.eth.get_balance(account.address)
    print(f"  Wallet  : {account.address}")
    print(f"  Balance : {w3.from_wei(balance, 'ether')} MNT (Sepolia)")

    tx = {
        "from":     account.address,
        "to":       Web3.to_checksum_address(payment["to"]),
        "value":    int(payment["amount"]),
        "gas":      21000,
        "gasPrice": w3.eth.gas_price,
        "nonce":    w3.eth.get_transaction_count(account.address),
        "chainId":  payment["chainId"],
    }
    signed  = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    tx_hex  = tx_hash.hex()
    print(f"  Tx sent : {tx_hex}")
    print("  Waiting for confirmation...")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    if receipt.status != 1:
        print("  Transaction reverted!")
        sys.exit(1)
    print(f"  Confirmed in block {receipt.blockNumber}")
    return tx_hex


# ── Step 4: Run backtest with X-Payment ──────────────────────────────────────
def step4_backtest(tx_hash: str) -> dict:
    print("\nStep 4: Running backtest (X-Payment header)...")
    resp = requests.post(
        f"{API_BASE}/backtest",
        json=BACKTEST_PARAMS,
        headers={"X-Payment": tx_hash},
        timeout=60,
    )
    print(f"  HTTP {resp.status_code}")
    data = resp.json()
    if data.get("status") == "error":
        print(f"  Error [{data.get('code')}]: {data.get('message')}")
        sys.exit(1)
    print(f"  Trades    : {data['total_trades']}  |  Win rate: {data['win_rate']}%")
    print(f"  Net PnL   : {data['net_pnl']}%  (${data['net_pnl_usdt']})")
    print(f"  Sharpe    : {data['sharpe_ratio']}")
    return data


# ── Step 5: Submit on-chain feedback (Mantle Mainnet) ─────────────────────────
def step5_reputation(result: dict) -> str:
    print("\nStep 5: Submitting on-chain feedback to ERC-8004 ReputationRegistry...")

    if CLIENT_PRIVATE_KEY == "0x...":
        print("  ⚠  CLIENT_PRIVATE_KEY not set — skipping reputation step.")
        print("     Set CLIENT_PRIVATE_KEY (a separate wallet, NOT the service owner).")
        return ""

    w3 = Web3(Web3.HTTPProvider(MAINNET_RPC))
    account = w3.eth.account.from_key(CLIENT_PRIVATE_KEY)
    balance = w3.eth.get_balance(account.address)
    print(f"  Wallet  : {account.address}")
    print(f"  Balance : {w3.from_wei(balance, 'ether')} MNT (Mainnet)")

    if balance == 0:
        print("  ⚠  No MNT on Mainnet — cannot pay gas. Skipping.")
        return ""

    strategy_tag = result.get("strategy", "unknown").lower().replace("_", "-")[:32]

    registry = w3.eth.contract(
        address=Web3.to_checksum_address(REPUTATION_REGISTRY),
        abi=REPUTATION_ABI,
    )

    nonce = w3.eth.get_transaction_count(account.address)
    tx = registry.functions.giveFeedback(
        AGENT_ID,
        100,                  # value: positive score (int128)
        0,                    # valueDecimals
        "backtest-service",   # tag1
        strategy_tag,         # tag2: strategy used
        "https://alphaterminal.live/api/backtest",   # endpoint
        "",                   # feedbackURI (empty for MVP)
        b'\x00' * 32,         # feedbackHash (bytes32 zero)
    ).build_transaction({
        "from":     account.address,
        "nonce":    nonce,
        "gas":      150_000,
        "gasPrice": w3.eth.gas_price,
        "chainId":  5000,
    })

    signed  = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    tx_hex  = tx_hash.hex()
    print(f"  Tx sent : {tx_hex}")
    print("  Waiting for confirmation...")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    if receipt.status != 1:
        print("  Transaction reverted!")
        return ""
    print(f"  ✅ Feedback confirmed in block {receipt.blockNumber}")
    print(f"  Explorer: https://explorer.mantle.xyz/tx/{tx_hex}")
    return tx_hex


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  BacktestStrategyAgent — Full AI Agent Cycle Demo")
    print("  ERC-8004 Identity + x402 Payment + Reputation")
    print("=" * 60 + "\n")

    step1_read_agent_card()
    payment_info = step2_probe()
    tx_hash      = step3_pay(payment_info)
    result       = step4_backtest(tx_hash)
    rep_tx       = step5_reputation(result)

    print("\n" + "=" * 60)
    print("  Summary")
    print("=" * 60)
    print(f"  Ticker         : {result['ticker']}")
    print(f"  Strategy       : {result['strategy']}")
    print(f"  Total trades   : {result['total_trades']}")
    print(f"  Win rate       : {result['win_rate']}%")
    print(f"  Net PnL        : {result['net_pnl']}%  (${result['net_pnl_usdt']})")
    print(f"  Max Drawdown   : {result['max_drawdown_pct']}%  (${result['max_drawdown_usdt']})")
    print(f"  Final Balance  : ${result['final_balance']}")
    print(f"  Sharpe Ratio   : {result['sharpe_ratio']}")
    if rep_tx:
        print(f"  Reputation TX  : https://explorer.mantle.xyz/tx/{rep_tx}")
    print()


if __name__ == "__main__":
    main()
