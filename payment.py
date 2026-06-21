"""
x402 payment verification for Mantle network.
Checks that a tx_hash represents a valid MNT transfer to our agent wallet.
"""
import os
from web3 import Web3

MANTLE_RPC = os.getenv("MANTLE_RPC", "https://rpc.mantle.xyz")
AGENT_WALLET = os.getenv("AGENT_WALLET", "").lower()
MIN_PAYMENT_WEI = int(os.getenv("MIN_PAYMENT_WEI", str(int(0.01 * 1e18))))  # 0.01 MNT

_w3 = None


def _get_w3() -> Web3:
    global _w3
    if _w3 is None:
        _w3 = Web3(Web3.HTTPProvider(MANTLE_RPC))
    return _w3


async def verify_payment(tx_hash: str | None) -> bool:
    if os.getenv("SKIP_PAYMENT", "false").lower() == "true":
        return True
    if not tx_hash or not AGENT_WALLET:
        return False
    try:
        w3 = _get_w3()
        tx = w3.eth.get_transaction(tx_hash)
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        if receipt is None or receipt.status != 1:
            return False
        if tx["to"] and tx["to"].lower() != AGENT_WALLET:
            return False
        if tx["value"] < MIN_PAYMENT_WEI:
            return False
        return True
    except Exception:
        return False
