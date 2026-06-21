"""
MACD (Moving Average Convergence/Divergence) strategy.

MACD Line  = EMA(close, fast) - EMA(close, slow)
Signal Line = EMA(MACD, signal_period)
Histogram   = MACD - Signal

Entry:
  LONG:  MACD crosses Signal from below  (macd[i-1] <= signal[i-1] and macd[i] > signal[i])
  SHORT: MACD crosses Signal from above  (macd[i-1] >= signal[i-1] and macd[i] < signal[i])

Exit:
  SL / TP  — price-based stops
  SIGNAL   — reverse crossover
"""
from datetime import datetime, timezone
import numpy as np
from .base import Trade, calc_pnl, calc_metrics


def _ema(prices: np.ndarray, period: int) -> np.ndarray:
    result = np.full(len(prices), np.nan)
    k = 2.0 / (period + 1)
    for i in range(period - 1, len(prices)):
        if i == period - 1:
            result[i] = float(np.mean(prices[i - period + 1 : i + 1]))
        else:
            result[i] = prices[i] * k + result[i - 1] * (1 - k)
    return result


def _macd(closes: np.ndarray, fast: int, slow: int, signal: int):
    fast_ema = _ema(closes, fast)
    slow_ema = _ema(closes, slow)
    macd_line = fast_ema - slow_ema  # nan until index slow-1

    # Signal = EMA of MACD starting from the first valid MACD value
    first_valid = slow - 1          # first index where macd_line is defined
    signal_line = np.full(len(closes), np.nan)
    k_sig = 2.0 / (signal + 1)

    # Seed: SMA of the first `signal` MACD values
    seed_end = first_valid + signal  # exclusive
    if seed_end <= len(closes):
        signal_line[seed_end - 1] = float(np.mean(macd_line[first_valid:seed_end]))
        for i in range(seed_end, len(closes)):
            signal_line[i] = macd_line[i] * k_sig + signal_line[i - 1] * (1 - k_sig)

    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def run(
    candles: list[dict],
    fast_period: int,
    slow_period: int,
    signal_period: int,
    sl_pct: float,
    tp_pct: float,
    leverage: float,
    direction: str,
) -> dict:
    closes = np.array([c["close"] for c in candles])
    timestamps = [c["ts"] for c in candles]

    macd_line, signal_line, _ = _macd(closes, fast_period, slow_period, signal_period)

    # First bar where both current and previous macd & signal are valid
    warmup = slow_period + signal_period  # conservative; actual is slow-1 + signal-1 + 1

    trades: list[Trade] = []
    position: dict | None = None

    for i in range(warmup, len(candles)):
        if np.isnan(macd_line[i]) or np.isnan(signal_line[i]):
            continue
        if np.isnan(macd_line[i - 1]) or np.isnan(signal_line[i - 1]):
            continue

        price = closes[i]
        ts_str = datetime.fromtimestamp(timestamps[i] / 1000, tz=timezone.utc).isoformat()

        crossed_up   = macd_line[i] > signal_line[i] and macd_line[i - 1] <= signal_line[i - 1]
        crossed_down = macd_line[i] < signal_line[i] and macd_line[i - 1] >= signal_line[i - 1]

        # ── Handle open position ──────────────────────────────────────────
        if position is not None:
            entry_p = position["entry_price"]
            dir_ = position["direction"]
            exit_reason = None

            if dir_ == "LONG":
                if price <= entry_p * (1 - sl_pct / 100):
                    exit_reason = "SL"
                elif price >= entry_p * (1 + tp_pct / 100):
                    exit_reason = "TP"
                elif crossed_down:
                    exit_reason = "SIGNAL"
            else:  # SHORT
                if price >= entry_p * (1 + sl_pct / 100):
                    exit_reason = "SL"
                elif price <= entry_p * (1 - tp_pct / 100):
                    exit_reason = "TP"
                elif crossed_up:
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

        # ── Check entry ───────────────────────────────────────────────────
        if position is None:
            if crossed_up and direction in ("LONG", "BOTH"):
                position = {"direction": "LONG", "entry_price": price, "entry_time": ts_str}
            elif crossed_down and direction in ("SHORT", "BOTH"):
                position = {"direction": "SHORT", "entry_price": price, "entry_time": ts_str}

    # Close any open position at the last candle
    if position is not None:
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
