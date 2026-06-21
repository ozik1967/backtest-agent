"""
/api/validate — full pre-payment validation.
Must mirror every check in /api/backtest (except payment and kline fetch).
If validate passes, backtest must not reject for a parameter reason.
"""
from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing import Optional
from bybit_client import validate_ticker, get_max_leverage, CANDLES_PER_DAY

router = APIRouter()


class ValidateRequest(BaseModel):
    ticker: str
    strategy: str
    timeframe: str
    depth_days: int = Field(ge=1, le=180)
    deposit: float = Field(default=1000, ge=10, le=1_000_000)
    margin_pct: float = Field(default=10, ge=1, le=100)
    leverage: float = Field(ge=1, le=50)
    sl_pct: float = Field(gt=0, le=100)
    tp_pct: float = Field(gt=0)
    direction: str = "BOTH"
    # MA/EMA params
    fast_period: Optional[int] = None
    slow_period: Optional[int] = None
    # RSI params
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    # Bollinger params
    bb_period: int = 20
    bb_std: float = 2.0
    # CVD params
    cvd_smooth: int = 5
    cvd_threshold_pct: float = 5.0
    # MACD params
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    # Funding Rate params
    funding_threshold: float = 0.00005


@router.post("/validate")
async def validate_params(req: ValidateRequest):
    warnings = []
    ticker = req.ticker.upper()

    # 1. Ticker exists on Bybit Futures
    ticker_info = await validate_ticker(ticker)
    if not ticker_info["valid"]:
        return {"status": "error", "code": "INVALID_TICKER",
                "message": f"Тикер {ticker} не найден на Bybit Futures"}

    # 2. Leverage within allowed range for this ticker
    max_lev = await get_max_leverage(ticker)
    if max_lev and req.leverage > max_lev:
        return {"status": "error", "code": "LEVERAGE_TOO_HIGH",
                "message": f"Максимальное плечо для {ticker}: {max_lev}x"}

    # 3. Enough candles for requested depth + timeframe
    if req.timeframe not in CANDLES_PER_DAY:
        return {"status": "error", "code": "INVALID_TIMEFRAME",
                "message": f"Неверный таймфрейм: {req.timeframe}"}
    candles_count = CANDLES_PER_DAY[req.timeframe] * req.depth_days
    if candles_count < 50:
        return {"status": "error", "code": "INSUFFICIENT_DATA",
                "message": f"Недостаточно свечей ({candles_count}). Увеличьте глубину или уменьшите таймфрейм."}

    # 4. SL / TP positive
    if req.sl_pct <= 0 or req.tp_pct <= 0:
        return {"status": "error", "code": "INVALID_SL_TP",
                "message": "SL и TP должны быть > 0"}

    # 5. Liquidation risk warning (same formula as backtest.py)
    if (req.margin_pct / 100) * req.leverage * (req.sl_pct / 100) >= 1:
        warnings.append(
            f"⚠ Одна сделка может ликвидировать весь депозит "
            f"(margin {req.margin_pct}% × {req.leverage}x × SL {req.sl_pct}% = "
            f"{req.margin_pct * req.leverage * req.sl_pct / 10000 * 100:.0f}% от депозита)"
        )

    # 6. Strategy-specific params
    if req.strategy in ("MA_CROSS", "EMA_CROSS"):
        if not req.fast_period or not req.slow_period:
            return {"status": "error", "code": "MISSING_PARAMS",
                    "message": "Укажите fast_period и slow_period"}
        if req.fast_period >= req.slow_period:
            return {"status": "error", "code": "INVALID_MA_PERIODS",
                    "message": "fast_period должен быть < slow_period"}

    if req.strategy == "MACD":
        if req.macd_fast >= req.macd_slow:
            return {"status": "error", "code": "INVALID_MACD_PERIODS",
                    "message": "MACD Fast EMA должен быть меньше Slow EMA"}

    return {"status": "ok", "warnings": warnings}
