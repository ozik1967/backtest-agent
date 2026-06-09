"""
Demo: AI Agent using x402 payment protocol to access BacktestStrategyAgent.

This script demonstrates how an autonomous AI agent can discover payment
requirements and pay for API access without any human interaction.

Flow:
  1. Call POST /api/backtest without payment  →  HTTP 402 with payment details
  2. Parse the 402 response to get: to, amount, chainId
  3. Send MNT payment on Mantle Sepolia
  4. Call POST /api/backtest with X-Payment: <tx_hash>  →  backtest results

Requirements:
  pip install web3 requests

Usage:
  PRIVATE_KEY=0x<your_key> python demo_agent.py
"""

import os
import sys
import time
import requests
from web3 import Web3

# ── Config ────────────────────────────────────────────────────────────────────
API_BASE     = "https://alphaterminal.live/api"
MANTLE_RPC   = "https://rpc.sepolia.mantle.xyz"
PRIVATE_KEY  = os.getenv("PRIVATE_KEY", "0x...")   # set via env var

# Backtest parameters the agent wants to run
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


# ── Step 1: Probe — discover payment requirements ─────────────────────────────
def step1_probe() -> dict:
    print("Step 1: Probing API without payment...")
    resp = requests.post(f"{API_BASE}/backtest", json=BACKTEST_PARAMS)
    print(f"  HTTP {resp.status_code}")

    if resp.status_code != 402:
        print(f"  Unexpected response: {resp.text[:200]}")
        sys.exit(1)

    data = resp.json()
    payment = data["payment"]
    print(f"  x402_version : {data['x402_version']}")
    print(f"  network      : {payment['network']}  chainId={payment['chainId']}")
    print(f"  to           : {payment['to']}")
    print(f"  amount       : {int(payment['amount']) / 1e18} {payment['currency']}")
    print(f"  reason       : {payment['reason']}")
    return payment


# ── Step 2: Pay — send MNT on Mantle Sepolia ──────────────────────────────────
def step2_pay(payment: dict) -> str:
    print("\nStep 2: Sending payment...")

    if PRIVATE_KEY == "0x...":
        print("  ⚠  PRIVATE_KEY not set — skipping real payment.")
        print("     Set PRIVATE_KEY env var to run end-to-end.")
        print("     Returning placeholder tx hash for demo purposes.\n")
        return "0x" + "ab" * 32   # placeholder — will fail payment verification

    w3 = Web3(Web3.HTTPProvider(MANTLE_RPC))
    if not w3.is_connected():
        print("  Cannot connect to Mantle RPC")
        sys.exit(1)

    account = w3.eth.account.from_key(PRIVATE_KEY)
    print(f"  Wallet  : {account.address}")
    balance = w3.eth.get_balance(account.address)
    print(f"  Balance : {w3.from_wei(balance, 'ether')} MNT")

    tx = {
        "from":     account.address,
        "to":       Web3.to_checksum_address(payment["to"]),
        "value":    int(payment["amount"]),
        "gas":      21000,
        "gasPrice": w3.eth.gas_price,
        "nonce":    w3.eth.get_transaction_count(account.address),
        "chainId":  payment["chainId"],
    }

    signed   = account.sign_transaction(tx)
    tx_hash  = w3.eth.send_raw_transaction(signed.raw_transaction)
    tx_hex   = tx_hash.hex()
    print(f"  Tx sent : {tx_hex}")

    print("  Waiting for confirmation...")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    if receipt.status != 1:
        print("  Transaction reverted!")
        sys.exit(1)
    print(f"  Confirmed in block {receipt.blockNumber}")
    return tx_hex


# ── Step 3: Run backtest with X-Payment header ────────────────────────────────
def step3_backtest(tx_hash: str) -> dict:
    print("\nStep 3: Calling /api/backtest with X-Payment header...")
    resp = requests.post(
        f"{API_BASE}/backtest",
        json=BACKTEST_PARAMS,
        headers={"X-Payment": tx_hash},
    )
    print(f"  HTTP {resp.status_code}")
    data = resp.json()

    if data.get("status") == "error":
        print(f"  Error [{data.get('code')}]: {data.get('message')}")
        sys.exit(1)

    return data


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  BacktestStrategyAgent  —  x402 AI Agent Demo")
    print("=" * 60 + "\n")

    payment_info = step1_probe()
    tx_hash      = step2_pay(payment_info)
    result       = step3_backtest(tx_hash)

    print("\n=== Backtest Result ===")
    print(f"  Ticker         : {result['ticker']}")
    print(f"  Strategy       : {result['strategy']}")
    print(f"  Timeframe      : {result['timeframe']}  /  {result['depth_days']} days")
    print(f"  Total trades   : {result['total_trades']}")
    print(f"  Win rate       : {result['win_rate']}%")
    print(f"  Net PnL        : {result['net_pnl']}%  (${result['net_pnl_usdt']})")
    print(f"  Max Drawdown   : {result['max_drawdown_pct']}%  (${result['max_drawdown_usdt']})")
    print(f"  Final Balance  : ${result['final_balance']}")
    print(f"  Sharpe Ratio   : {result['sharpe_ratio']}")
    for w in result.get("warnings", []):
        print(f"  {w}")
    print()


if __name__ == "__main__":
    main()
