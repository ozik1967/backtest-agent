from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Trade:
    entry_time: str
    exit_time: str
    direction: Literal["LONG", "SHORT"]
    entry_price: float
    exit_price: float
    pnl: float
    exit_reason: Literal["TP", "SL", "SIGNAL", "END"]


@dataclass
class BacktestResult:
    status: str
    ticker: str
    strategy: str
    timeframe: str
    depth_days: int
    leverage: float
    total_trades: int
    win_rate: float
    net_pnl: float
    max_drawdown_pct: float
    sharpe_ratio: float
    trades: list[Trade] = field(default_factory=list)


def calc_pnl(direction: str, entry: float, exit_: float, leverage: float) -> float:
    if direction == "LONG":
        return (exit_ - entry) / entry * 100 * leverage
    else:
        return (entry - exit_) / entry * 100 * leverage


def calc_metrics(trades: list[Trade], leverage: float) -> dict:
    if not trades:
        return {"win_rate": 0.0, "net_pnl": 0.0, "max_drawdown_pct": 0.0, "sharpe_ratio": 0.0}

    pnls = [t.pnl for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    win_rate = wins / len(pnls) * 100

    equity = 100.0
    equity_curve = [equity]
    peak = equity
    max_dd = 0.0
    for p in pnls:
        equity = equity * (1 + p / 100)
        equity_curve.append(equity)
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak * 100
        if dd > max_dd:
            max_dd = dd

    net_pnl = equity - 100.0

    import numpy as np
    arr = np.array(pnls)
    if arr.std() > 0:
        sharpe = float(arr.mean() / arr.std() * (252 ** 0.5))
    else:
        sharpe = 0.0

    metrics = {
        "win_rate": round(win_rate, 2),
        "net_pnl": round(net_pnl, 4),
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 4),
    }
    metrics["viable"] = is_viable(metrics, len(trades))
    return metrics


def is_viable(metrics: dict, total_trades: int) -> bool:
    if total_trades < 5:
        return False
    if metrics.get("sharpe_ratio", 0) < 0:
        return False
    if metrics.get("net_pnl", 0) < 0:
        return False
    if metrics.get("max_drawdown_pct", 100) > 50:
        return False
    return True
