"""
Funding Rate strategy: enter when funding rate is extreme.
Positive extreme (> threshold) → short (longs paying too much, expect reversal).
Negative extreme (< -threshold) → long (shorts paying too much, expect reversal).
"""
from datetime import datetime, timezone
import numpy as np
from .base import Trade, calc_pnl, calc_metrics


def run(
    candles: list[dict],
    funding_rates: list[dict],
    threshold: float,
    sl_pct: float,
    tp_pct: float,
    leverage: float,
    direction: str,
) -> dict:
    if not funding_rates:
        return {"trades": [], "win_rate": 0.0, "net_pnl": 0.0, "max_drawdown_pct": 0.0, "sharpe_ratio": 0.0}

    # Map funding timestamps to closest candle index
    candle_ts = [c["ts"] for c in candles]
    closes = [c["close"] for c in candles]

    def find_candle_idx(ts: int) -> int:
        lo, hi = 0, len(candle_ts) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if candle_ts[mid] < ts:
                lo = mid + 1
            else:
                hi = mid
        return lo

    trades = []
    position = None

    events = [(r["ts"], r["rate"]) for r in funding_rates]
    events.sort(key=lambda x: x[0])

    for event_ts, rate in events:
        idx = find_candle_idx(event_ts)
        if idx >= len(candles) - 1:
            continue
        entry_idx = idx + 1
        entry_price = closes[entry_idx]
        entry_ts = candle_ts[entry_idx]
        ts_str = datetime.fromtimestamp(entry_ts / 1000, tz=timezone.utc).isoformat()

        if position:
            continue

        if rate > threshold and direction in ("SHORT", "BOTH"):
            position = {"direction": "SHORT", "entry_price": entry_price, "entry_time": ts_str, "entry_idx": entry_idx}
        elif rate < -threshold and direction in ("LONG", "BOTH"):
            position = {"direction": "LONG", "entry_price": entry_price, "entry_time": ts_str, "entry_idx": entry_idx}

        if position:
            entry_p = position["entry_price"]
            dir_ = position["direction"]
            for j in range(position["entry_idx"] + 1, len(candles)):
                price = closes[j]
                exit_ts = datetime.fromtimestamp(candle_ts[j] / 1000, tz=timezone.utc).isoformat()
                exit_reason = None

                if dir_ == "LONG":
                    if price <= entry_p * (1 - sl_pct / 100):
                        exit_reason = "SL"
                    elif price >= entry_p * (1 + tp_pct / 100):
                        exit_reason = "TP"
                else:
                    if price >= entry_p * (1 + sl_pct / 100):
                        exit_reason = "SL"
                    elif price <= entry_p * (1 - tp_pct / 100):
                        exit_reason = "TP"

                if exit_reason:
                    trades.append(Trade(
                        entry_time=position["entry_time"],
                        exit_time=exit_ts,
                        direction=dir_,
                        entry_price=entry_p,
                        exit_price=price,
                        pnl=round(calc_pnl(dir_, entry_p, price, leverage), 4),
                        exit_reason=exit_reason,
                    ))
                    position = None
                    break

    if position:
        price = closes[-1]
        ts_str = datetime.fromtimestamp(candle_ts[-1] / 1000, tz=timezone.utc).isoformat()
        dir_ = position["direction"]
        trades.append(Trade(
            entry_time=position["entry_time"],
            exit_time=ts_str,
            direction=dir_,
            entry_price=position["entry_price"],
            exit_price=price,
            pnl=round(calc_pnl(dir_, position["entry_price"], price, leverage), 4),
            exit_reason="END",
        ))

    metrics = calc_metrics(trades, leverage)
    return {"trades": trades, **metrics}
