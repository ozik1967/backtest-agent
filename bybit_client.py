import httpx
import time
from typing import Optional

BYBIT_BASE = "https://api.bybit.com"

TIMEFRAME_MAP = {
    "5m": "5",
    "15m": "15",
    "1h": "60",
    "4h": "240",
    "1d": "D",
}

CANDLES_PER_DAY = {
    "5m": 288,
    "15m": 96,
    "1h": 24,
    "4h": 6,
    "1d": 1,
}


async def get_klines(ticker: str, timeframe: str, depth_days: int) -> list[dict]:
    interval = TIMEFRAME_MAP[timeframe]
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - depth_days * 86400 * 1000
    limit = 1000
    all_candles = []

    async with httpx.AsyncClient(timeout=30) as client:
        cursor_end = end_ms
        while cursor_end > start_ms:
            resp = await client.get(
                f"{BYBIT_BASE}/v5/market/kline",
                params={
                    "category": "linear",
                    "symbol": ticker,
                    "interval": interval,
                    "end": cursor_end,
                    "limit": limit,
                },
            )
            data = resp.json()
            if data.get("retCode") != 0:
                raise ValueError(f"Bybit API error: {data.get('retMsg')}")
            candles = data["result"]["list"]
            if not candles:
                break
            all_candles.extend(candles)
            oldest_ts = int(candles[-1][0])
            if oldest_ts <= start_ms:
                break
            cursor_end = oldest_ts - 1

    # candles: [ts, open, high, low, close, volume, turnover]
    result = []
    for c in all_candles:
        ts = int(c[0])
        if ts < start_ms:
            continue
        result.append({
            "ts": ts,
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5]),
        })

    result.sort(key=lambda x: x["ts"])
    return result


async def validate_ticker(ticker: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{BYBIT_BASE}/v5/market/instruments-info",
            params={"category": "linear", "symbol": ticker},
        )
        data = resp.json()
        if data.get("retCode") != 0 or not data["result"]["list"]:
            return {"valid": False}
        info = data["result"]["list"][0]
        return {"valid": True, "info": info}


async def get_max_leverage(ticker: str) -> Optional[float]:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{BYBIT_BASE}/v5/market/instruments-info",
            params={"category": "linear", "symbol": ticker},
        )
        data = resp.json()
        if data.get("retCode") != 0 or not data["result"]["list"]:
            return None
        info = data["result"]["list"][0]
        lev = info.get("leverageFilter", {})
        max_lev = lev.get("maxLeverage")
        return float(max_lev) if max_lev else None


async def get_funding_history(ticker: str, depth_days: int) -> list[dict]:
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - depth_days * 86400 * 1000
    all_rates = []

    async with httpx.AsyncClient(timeout=30) as client:
        cursor_end = end_ms
        while cursor_end > start_ms:
            resp = await client.get(
                f"{BYBIT_BASE}/v5/market/funding/history",
                params={
                    "category": "linear",
                    "symbol": ticker,
                    "endTime": cursor_end,
                    "limit": 200,
                },
            )
            data = resp.json()
            if data.get("retCode") != 0:
                break
            rates = data["result"]["list"]
            if not rates:
                break
            all_rates.extend(rates)
            oldest_ts = int(rates[-1]["fundingRateTimestamp"])
            if oldest_ts <= start_ms:
                break
            cursor_end = oldest_ts - 1

    result = []
    for r in all_rates:
        ts = int(r["fundingRateTimestamp"])
        if ts < start_ms:
            continue
        result.append({"ts": ts, "rate": float(r["fundingRate"])})

    result.sort(key=lambda x: x["ts"])
    return result


