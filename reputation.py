"""
ERC-8004 ReputationRegistry — read-only integration (Mantle Mainnet).

Reputation is written by AI agent CLIENTS via demo_agent.py:
  request → x402 payment → result → IPFS proof → giveFeedback(feedbackURI=ipfs://CID)

This module reads it back for GET /api/reputation:
  - getClients() + getSummary() for aggregate numbers
  - NewFeedback event logs for per-feedback details (feedbackURI lives ONLY
    in the event, not in readAllFeedback), including the feedback tx hash.
"""
import json
import logging
import os
import threading
from eth_abi import decode as abi_decode
from web3 import Web3

logger = logging.getLogger(__name__)

MANTLE_RPC          = "https://rpc.mantle.xyz"
REPUTATION_REGISTRY = "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63"
AGENT_ID            = 113

# Agent 113 was registered at this block (tx 0xca7cfb8b...) — feedbacks can
# only exist after it. Public RPC caps eth_getLogs at 10k blocks per call,
# so we scan incrementally and persist progress to a cache file.
AGENT_REGISTERED_BLOCK = 96_449_397
LOG_CHUNK              = 10_000
MAX_CHUNKS_PER_REQUEST = 30          # cap per request; remainder picked up next call
CACHE_FILE             = os.path.join(os.path.dirname(__file__), "feedback_cache.json")
_cache_lock            = threading.Lock()

ABI = [
    {
        "name": "getClients",
        "type": "function",
        "stateMutability": "view",
        "inputs":  [{"name": "agentId", "type": "uint256"}],
        "outputs": [{"name": "", "type": "address[]"}],
    },
    {
        "name": "getSummary",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "agentId",         "type": "uint256"},
            {"name": "clientAddresses", "type": "address[]"},
            {"name": "tag1",            "type": "string"},
            {"name": "tag2",            "type": "string"},
        ],
        "outputs": [
            {"name": "count",                "type": "uint64"},
            {"name": "summaryValue",         "type": "int128"},
            {"name": "summaryValueDecimals", "type": "uint8"},
        ],
    },
]

# NewFeedback(uint256 indexed agentId, address indexed clientAddress,
#             uint64 feedbackIndex, int128 value, uint8 valueDecimals,
#             string indexed indexedTag1, string tag1, string tag2,
#             string endpoint, string feedbackURI, bytes32 feedbackHash)
NEWFEEDBACK_TOPIC = Web3.keccak(
    text="NewFeedback(uint256,address,uint64,int128,uint8,string,string,string,string,string,bytes32)"
).hex()
NEWFEEDBACK_DATA_TYPES = [
    "uint64", "int128", "uint8", "string", "string", "string", "string", "bytes32"
]


def _hex(h) -> str:
    s = h.hex() if hasattr(h, "hex") else str(h)
    return s if s.startswith("0x") else "0x" + s


def _decode_log(log) -> dict | None:
    try:
        client = Web3.to_checksum_address("0x" + _hex(log["topics"][2])[-40:])
        data   = bytes(log["data"]) if not isinstance(log["data"], bytes) else log["data"]
        (feedback_index, value, value_decimals,
         tag1, tag2, endpoint, feedback_uri, _fb_hash) = abi_decode(NEWFEEDBACK_DATA_TYPES, data)

        divisor = 10 ** value_decimals if value_decimals > 0 else 1
        return {
            "client":        client,
            "feedbackIndex": int(feedback_index),
            "value":         value / divisor if value_decimals > 0 else int(value),
            "tag1":          tag1,
            "tag2":          tag2,
            "proofURI":      feedback_uri,
            "feedbackTx":    _hex(log["transactionHash"]),
            "block":         log["blockNumber"],
        }
    except Exception as exc:
        logger.warning(f"Failed to decode NewFeedback log: {exc}")
        return None


def _load_cache() -> dict:
    try:
        with open(CACHE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"last_block": AGENT_REGISTERED_BLOCK - 1, "feedbacks": []}


def _save_cache(cache: dict) -> None:
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except Exception as exc:
        logger.warning(f"Cache save failed: {exc}")


def _fetch_feedback_events(w3: Web3) -> list[dict]:
    """
    Incrementally scan NewFeedback events for AGENT_ID.
    Public RPC limits getLogs to 10k blocks — we chunk from the last scanned
    block (persisted in CACHE_FILE) and cap at MAX_CHUNKS_PER_REQUEST per call.
    """
    topic0      = NEWFEEDBACK_TOPIC if NEWFEEDBACK_TOPIC.startswith("0x") else "0x" + NEWFEEDBACK_TOPIC
    agent_topic = "0x" + hex(AGENT_ID)[2:].zfill(64)

    with _cache_lock:
        cache  = _load_cache()
        latest = w3.eth.block_number
        start  = cache["last_block"] + 1

        chunks = 0
        while start <= latest and chunks < MAX_CHUNKS_PER_REQUEST:
            end = min(start + LOG_CHUNK - 1, latest)
            logs = w3.eth.get_logs({
                "address":   Web3.to_checksum_address(REPUTATION_REGISTRY),
                "topics":    [topic0, agent_topic],
                "fromBlock": start,
                "toBlock":   end,
            })
            for log in logs:
                decoded = _decode_log(log)
                if decoded and not any(
                    f["feedbackTx"] == decoded["feedbackTx"] and
                    f["feedbackIndex"] == decoded["feedbackIndex"]
                    for f in cache["feedbacks"]
                ):
                    cache["feedbacks"].append(decoded)
            cache["last_block"] = end
            start  = end + 1
            chunks += 1

        _save_cache(cache)
        return cache["feedbacks"]


def get_reputation_sync() -> dict:
    """Read on-chain reputation. Called by GET /api/reputation."""
    base = {
        "agentId":        AGENT_ID,
        "totalFeedbacks": 0,
        "feedbacks":      [],
        "registry":       REPUTATION_REGISTRY,
        "chain":          "mantle-mainnet",
        "explorer":       f"https://explorer.mantle.xyz/address/{REPUTATION_REGISTRY}",
    }
    try:
        w3       = Web3(Web3.HTTPProvider(MANTLE_RPC))
        registry = w3.eth.contract(
            address=Web3.to_checksum_address(REPUTATION_REGISTRY),
            abi=ABI,
        )

        clients = registry.functions.getClients(AGENT_ID).call()
        if not clients:
            return base

        count, summary_value, value_decimals = registry.functions.getSummary(
            AGENT_ID, clients, "", "",
        ).call()
        divisor   = 10 ** value_decimals if value_decimals > 0 else 1
        avg_score = round(summary_value / divisor / count, 1) if count > 0 else None

        # Per-feedback details from event logs (feedbackURI + tx hash)
        try:
            feedbacks = _fetch_feedback_events(w3)
        except Exception as exc:
            logger.warning(f"Event log fetch failed, returning summary only: {exc}")
            feedbacks = []

        return {
            **base,
            "totalFeedbacks": int(count),
            "averageScore":   avg_score,
            "totalClients":   len(clients),
            "feedbacks":      feedbacks,
        }

    except Exception as exc:
        logger.error(f"Reputation read error: {exc}")
        return {**base, "error": str(exc)}
