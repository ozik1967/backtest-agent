"""
Demo: Verifiable AI agent cycle — ERC-8004 + x402 + IPFS proof.

Every on-chain feedback cryptographically references the full interaction:
  request → payment → result → feedback

Verification chain (what a judge / another agent can check):
  1. On-chain: feedback from address X for agent, with feedbackURI = ipfs://CID
  2. Open the IPFS file → see payment_tx
  3. Check payment_tx on Mantlescan: sender == X (same address!),
     recipient == service wallet, amount == 0.01 MNT, block BEFORE feedback block
  4. The file contains the full request and response summary, bound by hashes
  5. IPFS CID is deterministic from content — the file cannot be forged later

Canonical JSON for all hashes (DOCUMENTED, do not change):
    json.dumps(obj, sort_keys=True, separators=(',', ':'))
  then keccak256 of the UTF-8 bytes.

Usage:
  # Testnet first (agentId 128, free gas):
  CLIENT_PRIVATE_KEY=0x... PINATA_JWT=... python demo_agent.py --testnet

  # Mainnet (agentId 113):
  CLIENT_PRIVATE_KEY=0x... PINATA_JWT=... python demo_agent.py

Env vars:
  CLIENT_PRIVATE_KEY — ONE wallet for both payment and feedback (the whole point:
                       same address proves the feedback author paid)
  PINATA_JWT         — Pinata JWT token (or PINATA_API_KEY + PINATA_API_SECRET)

Requirements:
  pip install web3 requests
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timezone
from web3 import Web3

# ── Config ────────────────────────────────────────────────────────────────────
AGENT_CARD_URL = "https://alphaterminal.live/agent-card.json"
API_BASE       = "https://alphaterminal.live/api"

# Reputation networks (where giveFeedback is sent)
REPUTATION_NETWORKS = {
    "mainnet": {
        "name":     "Mantle Mainnet",
        "chain_id": 5000,
        "rpc":      "https://rpc.mantle.xyz",
        "registry": "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63",
        "agent_id": 113,
        "explorer": "https://explorer.mantle.xyz/tx/",
    },
    "testnet": {
        "name":     "Mantle Sepolia",
        "chain_id": 5003,
        "rpc":      "https://rpc.sepolia.mantle.xyz",
        "registry": "0x8004B663056A597Dffe9eCcC1965A193B7388713",
        "agent_id": 128,
        "explorer": "https://explorer.sepolia.mantle.xyz/tx/",
    },
}

IS_TESTNET = "--testnet" in sys.argv
REP_NET    = REPUTATION_NETWORKS["testnet" if IS_TESTNET else "mainnet"]

CLIENT_PRIVATE_KEY = os.getenv("CLIENT_PRIVATE_KEY", "0x...")

BACKTEST_REQUEST = {
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

REPUTATION_ABI = [{
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
}]


# ── Canonical JSON hashing ────────────────────────────────────────────────────
def canonical_json(obj) -> str:
    """Deterministic JSON: sorted keys, no whitespace. Fixed for hash reproducibility."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def keccak_hex(text: str) -> str:
    h = Web3.keccak(text=text).hex()
    return h if h.startswith("0x") else "0x" + h


def short(h: str) -> str:
    return f"{h[:6]}...{h[-4:]}" if h and len(h) > 12 else h


# ── IPFS via Pinata ───────────────────────────────────────────────────────────
def upload_to_pinata(obj: dict, name: str) -> str:
    """Upload JSON to IPFS via Pinata. Returns CID."""
    jwt        = os.getenv("PINATA_JWT")
    api_key    = os.getenv("PINATA_API_KEY")
    api_secret = os.getenv("PINATA_API_SECRET")

    if jwt:
        headers = {"Authorization": f"Bearer {jwt}"}
    elif api_key and api_secret:
        headers = {"pinata_api_key": api_key, "pinata_secret_api_key": api_secret}
    else:
        raise RuntimeError("Set PINATA_JWT (or PINATA_API_KEY + PINATA_API_SECRET)")

    resp = requests.post(
        "https://api.pinata.cloud/pinning/pinJSONToIPFS",
        json={"pinataContent": obj, "pinataMetadata": {"name": name}},
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["IpfsHash"]


# ── Steps ─────────────────────────────────────────────────────────────────────

def step1_build_request() -> str:
    req_hash = keccak_hex(canonical_json(BACKTEST_REQUEST))
    print(f"[1/6] Building backtest request...  "
          f"{BACKTEST_REQUEST['ticker']} {BACKTEST_REQUEST['strategy']} "
          f"{BACKTEST_REQUEST['timeframe']} {BACKTEST_REQUEST['depth_days']}d")
    print(f"      request_hash: {short(req_hash)}")
    return req_hash


def step2_pay(request_hash: str) -> tuple[str, str]:
    """Probe → 402 → pay. Embeds request_hash in payment tx data field."""
    print(f"[2/6] Requesting service → expecting 402...")
    resp = requests.post(f"{API_BASE}/backtest", json=BACKTEST_REQUEST, timeout=15)
    if resp.status_code != 402:
        print(f"      Unexpected HTTP {resp.status_code}: {resp.text[:150]}")
        sys.exit(1)
    payment = resp.json()["payment"]
    amount_mnt = int(payment["amount"]) / 1e18
    print(f"      402 received → paying {amount_mnt} {payment['currency']} "
          f"on chainId {payment['chainId']}...")

    if CLIENT_PRIVATE_KEY == "0x...":
        print("      ⚠  CLIENT_PRIVATE_KEY not set — cannot pay. Exiting.")
        sys.exit(1)

    # Payment network comes from the 402 response
    pay_rpc = ("https://rpc.sepolia.mantle.xyz" if payment["chainId"] == 5003
               else "https://rpc.mantle.xyz")
    w3      = Web3(Web3.HTTPProvider(pay_rpc))
    account = w3.eth.account.from_key(CLIENT_PRIVATE_KEY)

    tx = {
        "from":     account.address,
        "to":       Web3.to_checksum_address(payment["to"]),
        "value":    int(payment["amount"]),
        # request_hash embedded in tx data: binds the request to the payment on-chain
        "data":     request_hash,
        "gasPrice": w3.eth.gas_price,
        "nonce":    w3.eth.get_transaction_count(account.address),
        "chainId":  payment["chainId"],
    }
    # Mantle's gas model needs estimation (simple transfers cost far more than 21k)
    tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.2)
    signed  = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    tx_hex  = tx_hash.hex()
    if not tx_hex.startswith("0x"):
        tx_hex = "0x" + tx_hex

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=90)
    if receipt.status != 1:
        print("      Payment transaction reverted!")
        sys.exit(1)
    print(f"      TX: {tx_hex}  (block {receipt.blockNumber}, request_hash in tx data)")
    return tx_hex, account.address


def step3_get_result(payment_tx: str) -> tuple[dict, str]:
    print(f"[3/6] Fetching result (X-Payment: {short(payment_tx)})...")
    resp = requests.post(
        f"{API_BASE}/backtest",
        json=BACKTEST_REQUEST,
        headers={"X-Payment": payment_tx},
        timeout=90,
    )
    data = resp.json()
    if data.get("status") == "error":
        print(f"      Error [{data.get('code')}]: {data.get('message')}")
        sys.exit(1)

    resp_hash = keccak_hex(canonical_json(data))
    print(f"      {data['total_trades']} trades, win rate {data['win_rate']}%, "
          f"net PnL {data['net_pnl']}%, Sharpe {data['sharpe_ratio']}")
    print(f"      response_hash: {short(resp_hash)}")
    return data, resp_hash


def step4_build_proof(client: str, payment_tx: str, request_hash: str,
                      result: dict, response_hash: str) -> dict:
    print(f"[4/6] Building verifiable feedback proof...")
    proof = {
        "type":         "alpha-terminal-feedback-v1",
        "agentId":      REP_NET["agent_id"],
        "client":       client,
        "payment_tx":   payment_tx,
        "chain":        "mantle-sepolia" if IS_TESTNET else "mantle-mainnet",
        "request":      BACKTEST_REQUEST,
        "request_hash": request_hash,
        "response_summary": {
            "total_trades": result["total_trades"],
            "win_rate":     result["win_rate"],
            "net_pnl_pct":  result["net_pnl"],
            "sharpe":       result["sharpe_ratio"],
            "max_drawdown": result["max_drawdown_pct"],
        },
        "response_hash": response_hash,
        "canonicalization": "json.dumps(obj, sort_keys=True, separators=(',',':')) → keccak256(utf-8)",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    print(f"      proof links: payment_tx + request_hash + response_hash")
    return proof


def step5_upload_ipfs(proof: dict) -> str:
    print(f"[5/6] Uploading proof to IPFS (Pinata)...")
    cid = upload_to_pinata(proof, f"alpha-terminal-feedback-{int(time.time())}.json")
    print(f"      ipfs://{cid}")
    print(f"      gateway: https://gateway.pinata.cloud/ipfs/{cid}")
    return cid


def step6_give_feedback(cid: str, strategy: str) -> str:
    print(f"[6/6] Submitting on-chain feedback ({REP_NET['name']}, agentId {REP_NET['agent_id']})...")
    w3      = Web3(Web3.HTTPProvider(REP_NET["rpc"]))
    account = w3.eth.account.from_key(CLIENT_PRIVATE_KEY)
    balance = w3.eth.get_balance(account.address)

    if balance == 0:
        print(f"      ⚠  No MNT on {REP_NET['name']} for gas. Top up {account.address}")
        sys.exit(1)

    registry = w3.eth.contract(
        address=Web3.to_checksum_address(REP_NET["registry"]),
        abi=REPUTATION_ABI,
    )

    tag2 = strategy.lower().replace("_", "-")[:32]
    tx = registry.functions.giveFeedback(
        REP_NET["agent_id"],
        100,                    # value
        0,                      # valueDecimals
        "backtest-service",     # tag1
        tag2,                   # tag2: strategy
        "https://alphaterminal.live/api/backtest",
        f"ipfs://{cid}",        # feedbackURI — the verifiable proof
        b"\x00" * 32,           # feedbackHash: optional for IPFS (CID is content-addressed)
    ).build_transaction({
        "from":     account.address,
        "nonce":    w3.eth.get_transaction_count(account.address),
        "gasPrice": w3.eth.gas_price,
        "chainId":  REP_NET["chain_id"],
    })
    # Mantle's gas model needs estimation; build_transaction estimates, add 20% margin
    tx["gas"] = int(tx["gas"] * 1.2)

    signed  = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    tx_hex  = tx_hash.hex()
    if not tx_hex.startswith("0x"):
        tx_hex = "0x" + tx_hex

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=90)
    if receipt.status != 1:
        print("      Feedback transaction reverted!")
        sys.exit(1)
    print(f"      TX: {tx_hex}  (block {receipt.blockNumber})")
    print(f"      Explorer: {REP_NET['explorer']}{tx_hex}")
    return tx_hex


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    t0 = time.time()
    mode = "TESTNET" if IS_TESTNET else "MAINNET"
    print("═" * 64)
    print(f"  Alpha Terminal — Verifiable AI Agent Cycle  [{mode}]")
    print(f"  request → payment → result → IPFS proof → on-chain feedback")
    print("═" * 64)

    request_hash          = step1_build_request()
    payment_tx, client    = step2_pay(request_hash)
    result, response_hash = step3_get_result(payment_tx)
    proof                 = step4_build_proof(client, payment_tx, request_hash, result, response_hash)
    cid                   = step5_upload_ipfs(proof)
    feedback_tx           = step6_give_feedback(cid, result["strategy"])

    elapsed = time.time() - t0
    print("═" * 64)
    print(f"  ✅ Full verifiable cycle completed in {elapsed:.1f} sec")
    print("═" * 64)
    print(f"  Client wallet : {client}")
    print(f"  Payment TX    : {payment_tx}")
    print(f"  Proof         : ipfs://{cid}")
    print(f"  Feedback TX   : {feedback_tx}")
    print(f"  Verify        : {REP_NET['explorer']}{feedback_tx}")
    print()


if __name__ == "__main__":
    main()
