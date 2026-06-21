from datetime import datetime, timezone
import numpy as np
from .base import Trade, calc_pnl, calc_metrics


def _ma(prices: np.ndarray, period: int, ma_type: str) -> np.ndarray:
    result = np.full(len(prices), np.nan)
    if ma_type.upper() == "EMA":
        k = 2.0 / (period + 1)
        for i in range(period - 1, len(prices)):
            if i == period - 1:
                result[i] = float(np.mean(prices[i - period + 1 : i + 1]))
            else:
                result[i] = prices[i] * k + result[i - 1] * (1 - k)
    else:  # SMA
        for i in range(period - 1, len(prices)):
            result[i] = float(np.mean(prices[i - period + 1 : i + 1]))
    return result


def run(
    candles: list[dict],
    fast_period: int,
    slow_period: int,
    ma_type: str,
    sl_pct: float,
    tp_pct: float,
    leverage: float,
    direction: str,
) -> dict:
    closes = np.array([c["close"] for c in candles])
    timestamps = [c["ts"] for c in candles]

    fast = _ma(closes, fast_period, ma_type)
    slow = _ma(closes, slow_period, ma_type)

    trades = []
    position = None

    for i in range(slow_period, len(candles)):
        price = closes[i]
        ts_str = datetime.fromtimestamp(timestamps[i] / 1000, tz=timezone.utc).isoformat()

        if position:
            entry_p = position["entry_price"]
            dir_ = position["direction"]
            pnl = calc_pnl(dir_, entry_p, price, leverage)
            exit_reason = None

            if dir_ == "LONG":
                if price <= entry_p * (1 - sl_pct / 100):
                    exit_reason = "SL"
                elif price >= entry_p * (1 + tp_pct / 100):
                    exit_reason = "TP"
                elif fast[i] < slow[i] and fast[i - 1] >= slow[i - 1]:
                    exit_reason = "SIGNAL"
            else:
                if price >= entry_p * (1 + sl_pct / 100):
                    exit_reason = "SL"
                elif price <= entry_p * (1 - tp_pct / 100):
                    exit_reason = "TP"
                elif fast[i] > slow[i] and fast[i - 1] <= slow[i - 1]:
                    exit_reason = "SIGNAL"

            if exit_reason:
                trades.append(Trade(
                    entry_time=position["entry_time"],
                    exit_time=ts_str,
                    direction=dir_,
                    entry_price=entry_p,
                    exit_price=price,
                    pnl=round(calc_pnl(dir_, entry_p, price, leverage), 4),
                    exit_reason=exit_reason,
                ))
                position = None

        if position is None:
            crossed_up = fast[i] > slow[i] and fast[i - 1] <= slow[i - 1]
            crossed_down = fast[i] < slow[i] and fast[i - 1] >= slow[i - 1]

            if crossed_up and direction in ("LONG", "BOTH"):
                position = {"direction": "LONG", "entry_price": price, "entry_time": ts_str}
            elif crossed_down and direction in ("SHORT", "BOTH"):
                position = {"direction": "SHORT", "entry_price": price, "entry_time": ts_str}

    if position:
        price = closes[-1]
        ts_str = datetime.fromtimestamp(timestamps[-1] / 1000, tz=timezone.utc).isoformat()
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
