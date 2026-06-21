from datetime import datetime, timezone
import numpy as np
from .base import Trade, calc_pnl, calc_metrics


def _bbands(closes: np.ndarray, period: int = 20, std_mult: float = 2.0):
    upper = np.full(len(closes), np.nan)
    middle = np.full(len(closes), np.nan)
    lower = np.full(len(closes), np.nan)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1 : i + 1]
        m = float(np.mean(window))
        s = float(np.std(window, ddof=0))
        middle[i] = m
        upper[i] = m + std_mult * s
        lower[i] = m - std_mult * s
    return upper, middle, lower


def run(
    candles: list[dict],
    period: int,
    std_mult: float,
    sl_pct: float,
    tp_pct: float,
    leverage: float,
    direction: str,
) -> dict:
    closes = np.array([c["close"] for c in candles])
    timestamps = [c["ts"] for c in candles]
    upper, middle, lower = _bbands(closes, period, std_mult)

    trades = []
    position = None

    for i in range(period, len(candles)):
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
                elif price >= middle[i]:
                    exit_reason = "SIGNAL"
            else:
                if price >= entry_p * (1 + sl_pct / 100):
                    exit_reason = "SL"
                elif price <= entry_p * (1 - tp_pct / 100):
                    exit_reason = "TP"
                elif price <= middle[i]:
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

        if position is None and not np.isnan(lower[i]):
            if closes[i] <= lower[i] and direction in ("LONG", "BOTH"):
                position = {"direction": "LONG", "entry_price": price, "entry_time": ts_str}
            elif closes[i] >= upper[i] and direction in ("SHORT", "BOTH"):
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
