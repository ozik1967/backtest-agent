from datetime import datetime, timezone
import numpy as np
from .base import Trade, calc_pnl, calc_metrics


def _rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    delta = np.diff(closes)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    avg_gain = np.full(len(closes), np.nan)
    avg_loss = np.full(len(closes), np.nan)

    avg_gain[period] = np.mean(gain[:period])
    avg_loss[period] = np.mean(loss[:period])

    for i in range(period + 1, len(closes)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i - 1]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i - 1]) / period

    rs = np.where(avg_loss == 0, np.inf, avg_gain / avg_loss)
    rsi = 100 - 100 / (1 + rs)
    rsi[:period] = np.nan
    return rsi


def run(
    candles: list[dict],
    period: int,
    oversold: float,
    overbought: float,
    sl_pct: float,
    tp_pct: float,
    leverage: float,
    direction: str,
) -> dict:
    closes = np.array([c["close"] for c in candles])
    timestamps = [c["ts"] for c in candles]
    rsi = _rsi(closes, period)

    trades = []
    position = None

    for i in range(period + 1, len(candles)):
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
                elif rsi[i] >= overbought:
                    exit_reason = "SIGNAL"
            else:
                if price >= entry_p * (1 + sl_pct / 100):
                    exit_reason = "SL"
                elif price <= entry_p * (1 - tp_pct / 100):
                    exit_reason = "TP"
                elif rsi[i] <= oversold:
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
            if not np.isnan(rsi[i]):
                if rsi[i] < oversold and direction in ("LONG", "BOTH"):
                    position = {"direction": "LONG", "entry_price": price, "entry_time": ts_str}
                elif rsi[i] > overbought and direction in ("SHORT", "BOTH"):
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
