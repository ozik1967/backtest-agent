from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import backtest, validate, reputation

app = FastAPI(title="BacktestStrategyAgent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(backtest.router,    prefix="/api")
app.include_router(validate.router,    prefix="/api")
app.include_router(reputation.router,  prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "agent": "BacktestStrategyAgent"}
