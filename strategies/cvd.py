"""
CVD (Cumulative Volume Delta) strategy adapted for historical candle data.
Since per-trade data isn't available from Bybit klines, we approximate:
  CVD delta per candle = volume * sign(close - open)
Entry: CVD crosses above threshold (long) or below -threshold (short).
Exit: SL/TP or CVD reversal signal.
"""
from datetime import datetime, timezone
import numpy as np
from .base import Trade, calc_pnl, calc_metrics


def _cvd(candles: list[dict], smooth: int = 5) -> np.ndarray:
    deltas = np.array([
        c["volume"] if c["close"] >= c["open"] else -c["volume"]
        for c in candles
    ])
    cvd = np.cumsum(deltas)
    # Smooth with rolling mean
    smoothed = np.full(len(cvd), np.nan)
    for i in range(smooth - 1, len(cvd)):
        smoothed[i] = float(np.mean(cvd[i - smooth + 1 : i + 1]))
    return smoothed


def run(
    candles: list[dict],
    smooth_period: int,
    threshold_pct: float,
    sl_pct: float,
    tp_pct: float,
    leverage: float,
    direction: str,
) -> dict:
    closes = np.array([c["close"] for c in candles])
    timestamps = [c["ts"] for c in candles]
    cvd = _cvd(candles, smooth_period)

    trades = []
    position = None
    lookback = smooth_period + 1

    for i in range(lookback, len(candles)):
        if np.isnan(cvd[i]) or np.isnan(cvd[i - 1]):
            continue

        price = closes[i]
        ts_str = datetime.fromtimestamp(timestamps[i] / 1000, tz=timezone.utc).isoformat()

        if position:
            entry_p = position["entry_price"]
            dir_ = position["direction"]
            exit_reason = None

            if dir_ == "LONG":
                if price <= entry_p * (1 - sl_pct / 100):
                    exit_reason = "SL"
                elif price >= entry_p * (1 + tp_pct / 100):
                    exit_reason = "TP"
                elif cvd[i] < cvd[i - 1] * (1 - threshold_pct / 100):
                    exit_reason = "SIGNAL"
            else:
                if price >= entry_p * (1 + sl_pct / 100):
                    exit_reason = "SL"
                elif price <= entry_p * (1 - tp_pct / 100):
                    exit_reason = "TP"
                elif cvd[i] > cvd[i - 1] * (1 - threshold_pct / 100):
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
            delta_pct = (cvd[i] - cvd[i - 1]) / (abs(cvd[i - 1]) + 1e-9) * 100
            if delta_pct >= threshold_pct and direction in ("LONG", "BOTH"):
                position = {"direction": "LONG", "entry_price": price, "entry_time": ts_str}
            elif delta_pct <= -threshold_pct and direction in ("SHORT", "BOTH"):
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
