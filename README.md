# Alpha Terminal — BacktestStrategyAgent

AI-powered backtesting platform for crypto trading strategies with on-chain payment on Mantle.

## Live Demo
**https://alphaterminal.live**

## What it does
Users select a trading strategy, configure parameters, pay **0.01 MNT** via MetaMask, and receive full backtest results with metrics and equity curve.

## Strategies (7)
| Strategy | Description |
|---|---|
| **MA Cross** | SMA/EMA crossover. Presets: 9/21, 9/50, 9/99, 20/50, 50/200, Custom |
| **EMA Cross** | Exponential MA crossover |
| **RSI** | Oversold/overbought reversal signals |
| **Bollinger Bands** | Mean-reversion on band breakouts |
| **MACD** | Configurable Fast/Slow/Signal EMA periods |
| **CVD** | Cumulative Volume Delta momentum |
| **Funding Rate** | Funding rate threshold entries |

## Parameters
- **Ticker** — any Bybit Futures pair (BTCUSDT, ETHUSDT, etc.)
- **Timeframe** — 5m, 15m, 1h, 4h, 1d
- **Leverage** — 1–50x
- **Deposit** — starting capital (USDT)
- **Margin per trade** — % of deposit per position
- **Stop Loss / Take Profit** — % from entry
- **Depth** — 1–180 days of history
- **Direction** — Long / Short / Both

## Backtest Metrics
- Total trades, Win Rate, Sharpe Ratio
- Net PnL (% of deposit + USDT)
- Max Drawdown (% + USDT)
- Final Balance (USDT)
- Equity Curve (Chart.js)
- Liquidation risk warning

## Tech Stack
| Layer | Technology |
|---|---|
| Frontend | React (CDN, no build step), Chart.js, HTML/CSS |
| Backend | Python 3.12, FastAPI, Bybit API v5 |
| Blockchain | Mantle Sepolia — ERC-8004 Agent Identity & Reputation Registry |
| Payment | x402 micropayment in MNT via MetaMask |
| Data | Bybit Futures klines, funding rate history |
| Infrastructure | VPS (Ubuntu 24.04), nginx, Let's Encrypt SSL, systemd |

## Smart Contract (Mantle Sepolia)
- **Contract**: `0xA05eb19EaeB861a70450108cA0bA4734f0996811`
- **Agent ID**: `0x3de0649cba34988b6b8455e7a890eacecb1fd001c52550dfec11440f93ed78a2`
- **Standard**: ERC-8004 (Agent Identity & Reputation)
- **Network**: Mantle Sepolia (Chain ID 5003)

## Agent Card
[https://alphaterminal.live/agent-card.json](https://alphaterminal.live/agent-card.json)

## Architecture
```
[User Browser]
     │
     ▼
alphaterminal.live (nginx + TLS)
     │
     ├── Frontend (React SPA)
     │       └── MetaMask → 0.01 MNT → Mantle Sepolia
     │
     └── /api/backtest (FastAPI)
             ├── Verify tx on-chain (web3.py)
             ├── Fetch klines (Bybit API v5)
             ├── Run strategy engine
             └── Return metrics + trades
```

## Payment Flow (x402)
1. User clicks **Run Backtest**
2. MetaMask prompts: send **0.01 MNT** to agent wallet
3. Frontend polls for transaction receipt (up to 60s)
4. Backend verifies tx on Mantle Sepolia via web3.py
5. Backtest executes and results are returned

## How to Run Locally
```bash
cd backend
pip install -r requirements.txt

# Copy and configure env
cp .env.example .env
# Set MANTLE_RPC, AGENT_WALLET, SKIP_PAYMENT=true (for local dev)

uvicorn main:app --port 8001 --reload
```

Then open `frontend/index.html` in a browser (or serve with any static server).

## Project Structure
```
backtest-agent/
├── backend/
│   ├── main.py                  # FastAPI app entry
│   ├── bybit_client.py          # Bybit API wrapper
│   ├── payment.py               # x402 tx verification
│   ├── routers/
│   │   ├── backtest.py          # POST /api/backtest
│   │   └── validate.py          # POST /api/validate-ticker
│   └── strategies/
│       ├── base.py              # Trade dataclass, metrics
│       ├── ma_cross.py          # MA/EMA Cross
│       ├── rsi.py               # RSI
│       ├── bollinger.py         # Bollinger Bands
│       ├── macd.py              # MACD
│       ├── cvd.py               # CVD
│       └── funding_rate.py      # Funding Rate
├── frontend/
│   └── index.html               # Single-file React SPA
├── contracts/
│   └── BacktestAgentRegistry.sol  # ERC-8004 contract
└── deploy/
    ├── setup_vps.sh             # VPS bootstrap script
    └── deploy_contract.js       # Hardhat deployment
```

## Hackathon
**Mantle Turing Test Hackathon 2026**
- Track: AI Trading & Strategy / AI Alpha & Data
- Deadline: June 15, 2026
- Demo Day: July 2–3, 2026

## Team
**Oleg Isaev** — Entrepreneur, developer, crypto trader since 2014

## License
MIT
