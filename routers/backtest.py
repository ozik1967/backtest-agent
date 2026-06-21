from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Literal, Optional
from dataclasses import asdict
import os

import bybit_client
from payment import verify_payment, AGENT_WALLET, MIN_PAYMENT_WEI
import strategies.ma_cross as ma_cross
import strategies.rsi as rsi_strat
import strategies.bollinger as bollinger
import strategies.cvd as cvd_strat
import strategies.macd as macd_strat
import strategies.funding_rate as funding_strat

router = APIRouter()


def _is_viable(total_trades, win_rate, net_pnl_pct, max_drawdown_pct, sharpe_ratio):
    if total_trades < 5:
        return False
    if sharpe_ratio < 0:
        return False
    if net_pnl_pct < 0:
        return False
    if max_drawdown_pct > 50:
        return False
    return True

STRATEGY_NAMES = Literal[
    "MA_CROSS", "EMA_CROSS",
    "RSI", "BOLLINGER",
    "CVD", "MACD", "FUNDING_RATE"
]

DIRECTION = Literal["LONG", "SHORT", "BOTH"]
TIMEFRAME = Literal["5m", "15m", "1h", "4h", "1d"]
MA_TYPE = Literal["SMA", "EMA"]


class BacktestRequest(BaseModel):
    ticker: str
    strategy: STRATEGY_NAMES
    timeframe: TIMEFRAME
    depth_days: int = Field(ge=1, le=180)
    deposit: float = Field(default=1000, ge=10, le=1_000_000)
    margin_pct: float = Field(default=10, ge=1, le=100)
    leverage: float = Field(ge=1, le=50)
    sl_pct: float = Field(gt=0, le=100)
    tp_pct: float = Field(gt=0)
    direction: DIRECTION = "BOTH"
    fast_period: Optional[int] = None
    slow_period: Optional[int] = None
    ma_type: MA_TYPE = "EMA"
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    bb_period: int = 20
    bb_std: float = 2.0
    cvd_smooth: int = 5
    cvd_threshold_pct: float = 5.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    funding_threshold: float = 0.00005
    tx_hash: Optional[str] = None


def _build_402_body(reason):
    return {
        "x402_version": 1,
        "payment": {
            "network": "mantle",
            "chainId": 5000,
            "to": AGENT_WALLET,
            "amount": str(MIN_PAYMENT_WEI),
            "currency": "MNT",
            "reason": reason,
        },
    }


@router.post("/backtest")
async def run_backtest(
    req: BacktestRequest,
    x_payment: Optional[str] = Header(None, alias="X-Payment"),
):
    ticker = req.ticker.upper()

    payment_source = req.tx_hash or x_payment
    if not payment_source and os.getenv("SKIP_PAYMENT", "false").lower() != "true":
        reason = f"Backtest: {ticker} {req.strategy} {req.timeframe} {req.depth_days}d {req.leverage}x"
        return JSONResponse(status_code=402, content=_build_402_body(reason))

    ticker_info = await bybit_client.validate_ticker(ticker)
    if not ticker_info["valid"]:
        return {"status": "error", "code": "INVALID_TICKER",
                "message": f"Ticker {ticker} not found on Bybit Futures"}

    max_lev = await bybit_client.get_max_leverage(ticker)
    if max_lev and req.leverage > max_lev:
        return {"status": "error", "code": "LEVERAGE_TOO_HIGH",
                "message": f"Max leverage for {ticker}: {max_lev}x"}

    candles_count = bybit_client.CANDLES_PER_DAY.get(req.timeframe, 0) * req.depth_days
    if candles_count < 50:
        return {"status": "error", "code": "INSUFFICIENT_DATA",
                "message": f"Not enough candles ({candles_count}). Increase depth or lower timeframe."}

    if req.sl_pct <= 0 or req.tp_pct <= 0:
        return {"status": "error", "code": "INVALID_SL_TP", "message": "SL and TP must be > 0"}

    warnings = []
    if (req.margin_pct / 100) * req.leverage * (req.sl_pct / 100) >= 1:
        warnings.append(
            f"One trade can liquidate the entire deposit "
            f"(margin {req.margin_pct}% x {req.leverage}x x SL {req.sl_pct}% = "
            f"{req.margin_pct * req.leverage * req.sl_pct / 10000 * 100:.0f}% of deposit)"
        )

    if req.strategy in ("MA_CROSS", "EMA_CROSS"):
        if not req.fast_period or not req.slow_period:
            return {"status": "error", "code": "MISSING_PARAMS",
                    "message": "fast_period and slow_period required"}
        if req.fast_period >= req.slow_period:
            return {"status": "error", "code": "INVALID_MA_PERIODS",
                    "message": "fast_period must be < slow_period"}

    payment_ok = await verify_payment(payment_source)
    if not payment_ok:
        reason = f"Backtest: {ticker} {req.strategy} {req.timeframe} {req.depth_days}d {req.leverage}x"
        return JSONResponse(status_code=402, content=_build_402_body(reason))

    candles = await bybit_client.get_klines(ticker, req.timeframe, req.depth_days)
    if len(candles) == 0:
        return {"status": "error", "code": "INVALID_TICKER",
                "message": f"Ticker {ticker} not found on Bybit Futures"}
    if len(candles) < 50:
        return {"status": "error", "code": "INSUFFICIENT_DATA",
                "message": f"Only {len(candles)} candles available for {ticker}."}

    ma_type = req.ma_type if req.strategy == "MA_CROSS" else "EMA"

    if req.strategy in ("MA_CROSS", "EMA_CROSS"):
        result = ma_cross.run(
            candles, req.fast_period, req.slow_period, ma_type,
            req.sl_pct, req.tp_pct, req.leverage, req.direction)
    elif req.strategy == "RSI":
        result = rsi_strat.run(
            candles, req.rsi_period, req.rsi_oversold, req.rsi_overbought,
            req.sl_pct, req.tp_pct, req.leverage, req.direction)
    elif req.strategy == "BOLLINGER":
        result = bollinger.run(
            candles, req.bb_period, req.bb_std,
            req.sl_pct, req.tp_pct, req.leverage, req.direction)
    elif req.strategy == "CVD":
        result = cvd_strat.run(
            candles, req.cvd_smooth, req.cvd_threshold_pct,
            req.sl_pct, req.tp_pct, req.leverage, req.direction)
    elif req.strategy == "MACD":
        if req.macd_fast >= req.macd_slow:
            return {"status": "error", "code": "INVALID_MACD_PERIODS",
                    "message": "MACD Fast EMA must be < Slow EMA"}
        result = macd_strat.run(
            candles, req.macd_fast, req.macd_slow, req.macd_signal,
            req.sl_pct, req.tp_pct, req.leverage, req.direction)
    elif req.strategy == "FUNDING_RATE":
        funding_rates = await bybit_client.get_funding_history(ticker, req.depth_days)
        result = funding_strat.run(
            candles, funding_rates, req.funding_threshold,
            req.sl_pct, req.tp_pct, req.leverage, req.direction)

    strategy_label = req.strategy
    if req.strategy in ("MA_CROSS", "EMA_CROSS") and req.fast_period and req.slow_period:
        strategy_label = f"{req.strategy}_{req.fast_period}_{req.slow_period}"

    margin_usdt = req.deposit * req.margin_pct / 100
    trades = result["trades"]
    pnl_usdts = [t.pnl / 100 * margin_usdt for t in trades]

    net_pnl_usdt = round(sum(pnl_usdts), 2)
    net_pnl_deposit_pct = round(net_pnl_usdt / req.deposit * 100, 2)
    final_balance = round(req.deposit + net_pnl_usdt, 2)

    balance = req.deposit
    peak = balance
    max_dd_usdt = 0.0
    for p in pnl_usdts:
        balance += p
        if balance > peak:
            peak = balance
        dd = peak - balance
        if dd > max_dd_usdt:
            max_dd_usdt = dd
    max_dd_usdt = round(max_dd_usdt, 2)

    viable = _is_viable(len(trades), result["win_rate"], net_pnl_deposit_pct,
                         result["max_drawdown_pct"], result["sharpe_ratio"])
    if not viable:
        warnings.append("Strategy is not viable with current parameters: negative returns, "
                        "high drawdown, or insufficient trades.")

    return {
        "status": "ok",
        "exchange": "bybit",
        "ticker": ticker,
        "strategy": strategy_label,
        "timeframe": req.timeframe,
        "depth_days": req.depth_days,
        "deposit": req.deposit,
        "margin_pct": req.margin_pct,
        "leverage": req.leverage,
        "total_trades": len(trades),
        "win_rate": result["win_rate"],
        "net_pnl": net_pnl_deposit_pct,
        "net_pnl_usdt": net_pnl_usdt,
        "final_balance": final_balance,
        "max_drawdown_pct": result["max_drawdown_pct"],
        "max_drawdown_usdt": max_dd_usdt,
        "sharpe_ratio": result["sharpe_ratio"],
        "viable": viable,
        "warnings": warnings,
        "trades": [asdict(t) for t in trades],
    }
