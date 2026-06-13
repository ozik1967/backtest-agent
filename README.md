# BacktestStrategyScanner

**Backtesting-as-a-service for humans and AI agents — ERC-8004 identity, verifiable on-chain reputation, x402 payments on Mantle.**

Built for the [Mantle Turing Test Hackathon 2026](https://dorahacks.io/hackathon/mantleturingtesthackathon2026) — Track 01: AI Trading & Strategy.

🔗 **Live demo:** https://alphaterminal.live
🤖 **Agent ID:** [113](https://explorer.mantle.xyz/tx/0xca7cfb8bb6ee99112b2c28360967d97d27a9c36c5acb3327792fbe396e62dcd2) in the official ERC-8004 Identity Registry on Mantle Mainnet
📇 **Agent Card:** [IPFS](https://lime-electronic-quelea-518.mypinata.cloud/ipfs/bafkreicpgq7euvxn7brwuob7mqw36xjbblzgnj72iif7s5mjkmnp5rgkj4)

---

## What it does

BacktestStrategyScanner lets **anyone — human or AI agent — validate a trading strategy against real market data before risking capital**.

Pick a strategy, set the parameters (ticker, timeframe, leverage, stop-loss/take-profit, depth), pay 0.01 MNT — and get a full backtest report: net PnL, win rate, Sharpe ratio, max drawdown, equity curve, and a complete trade log. Data is sourced live from the Bybit Futures API.

The key idea: **AI trading agents need infrastructure too.** Imagine an autonomous agent that came up with a trading hypothesis — but deploying untested strategies means risking real capital. It needs historical evidence first. The agent queries the ERC-8004 registry, finds BacktestStrategyScanner whose Agent Card matches its needs, pays 0.01 MNT via x402, and within seconds receives a full backtest report on real market data. Now the decision is data-driven, not blind. The service delivered — so the agent leaves verifiable on-chain feedback, strengthening the reputation that future agents will rely on. No human in the loop, at any step.

## Why it matters for the agentic economy

> "Not just humans trading assets, but autonomous agents creating verifiable, on-chain value."

BacktestStrategyScanner implements the full trust cycle that ERC-8004 was designed for:

1. **Discovery** — the agent is registered in the official ERC-8004 Identity Registry (agentId 113); its Agent Card on IPFS describes endpoints, capabilities, and pricing
2. **Payment** — machine-native x402 flow: HTTP 402 → pay MNT → retry with payment proof
3. **Service** — deterministic backtest computation over real Bybit market data
4. **Reputation** — the client agent submits feedback to the official ERC-8004 Reputation Registry, with a cryptographic proof chain linking the feedback to the actual paid request

## Architecture: dual-mode

```
┌─────────────── HUMAN PATH ───────────────┐
Browser → alphaterminal.live → pick strategy
  → POST /api/validate (free pre-check)
  → MetaMask: pay 0.01 MNT
  → POST /api/backtest + tx_hash
  → results: PnL, Sharpe, equity curve, trades

┌─────────────── AGENT PATH ───────────────┐
AI agent → reads Agent Card (ERC-8004 / IPFS)
  → POST /api/backtest
  → HTTP 402 Payment Required (x402 details)
  → pays 0.01 MNT programmatically
  → retry with X-Payment header
  → results (JSON)
  → submits verifiable feedback on-chain
```

**Validation before payment.** All parameters (ticker validity, max leverage, available data depth, minimum candle count) are checked via a free `/api/validate` call *before* any payment. If the request can't be fulfilled, the user gets an informative message and pays nothing. Once paid, execution is guaranteed.

## ERC-8004 integration

### Identity
Registered in the official Mantle Mainnet singleton:

| | |
|---|---|
| IdentityRegistry | `0x8004A169FB4a3325136EB29fA0ceB6D2e539a432` |
| agentId | **113** |
| Registration TX | [`0xca7cfb...dcd2`](https://explorer.mantle.xyz/tx/0xca7cfb8bb6ee99112b2c28360967d97d27a9c36c5acb3327792fbe396e62dcd2) |
| Agent Card | `ipfs://bafkreicpgq7euvxn7brwuob7mqw36xjbblzgnj72iif7s5mjkmnp5rgkj4` |
| Well-known | https://alphaterminal.live/.well-known/agent-card.json |

### Verifiable Reputation
Client agents rate the service in the official Reputation Registry (`0x8004BAa17C55a88189AE136b182e5fdA19dE9b63`). What makes our feedback different: **every feedback entry carries a cryptographic proof chain.**

The `feedbackURI` field points to an IPFS document containing:
- the full backtest request JSON + its keccak256 hash
- the payment transaction hash (same wallet that submits the feedback)
- the response summary + its keccak256 hash
- timestamps

Anyone can verify: the feedback author actually paid for and received the service. The payment TX and the feedback TX come from the same address, in the correct block order, linked through content-addressed IPFS storage. Feedback is not just a claim — it's evidence.

Self-feedback is impossible by design: the registry contract rejects feedback from the agent's owner or operators.

**Live example on mainnet** — a full verifiable cycle (~12–15 sec end-to-end):

| | |
|---|---|
| Payment TX (with request hash in data) | [`0x68a23d...0c9b`](https://explorer.mantle.xyz/tx/0x68a23d68e58627b45750b26b929d3abfa35e132a6be93fca4a44832e2dc50c9b) |
| Proof on IPFS | [`QmTe6R28...SLuu`](https://gateway.pinata.cloud/ipfs/QmTe6R28t9PGibwE5kMWsMttfNGYhYVKSwCGsGbAG1SLuu) |
| Feedback TX | [`0x537c40...2d79`](https://explorer.mantle.xyz/tx/0x537c40568c36d122748f429b5c1b54ca3a5aa78b84b8e3e0f0d9afa84a3f2d79) |

## x402 payment flow

```
POST /api/backtest          → 402 Payment Required
                              { x402_version, payTo, amount: 0.01 MNT, ... }
<agent pays on Mantle>
POST /api/backtest          → 200 OK
  X-Payment: <tx proof>       { trades, win_rate, sharpe, pnl, equity_curve, ... }
```

## Strategies (7)

| Strategy | Signal logic |
|---|---|
| MA Cross | Moving average crossover |
| EMA Cross | Exponential MA crossover |
| RSI | Overbought/oversold reversal |
| Bollinger Bands | Volatility band breakout/reversion |
| MACD | Momentum crossover |
| CVD | Cumulative volume delta divergence |
| Funding Rate | Funding-driven contrarian entries |

**Parameters:** any Bybit Futures ticker · timeframes 5m/15m/1h/4h/1d · leverage 1–50x · deposit & margin % · SL/TP % · depth 1–180 days · direction Long/Short/Both. Liquidation warnings included.

## Tech stack

- **Backend:** Python, FastAPI — proprietary (not in this repo)
- **Market data:** Bybit Futures API v5 (klines, funding history)
- **Frontend:** React SPA, Chart.js
- **Chain:** Mantle Mainnet (chainId 5000)
- **Contracts:** official ERC-8004 singletons (Identity + Reputation)
- **Payments:** x402 protocol, native MNT
- **Storage:** IPFS (Pinata) for Agent Card and feedback proofs

## Try it as an agent

```bash
# Full verifiable cycle: request → 402 → pay → result → on-chain feedback
CLIENT_PRIVATE_KEY=0x<your_key> python3 demo_agent.py
```

The demo prints each step with hashes, TX links, and total cycle time.

## Repository layout

```
frontend/          React SPA + agent-card.json
deploy/            registration & feedback scripts (ethers.js)
demo_agent.py      full agent-path demo: x402 + verifiable feedback
```

The backtesting backend is proprietary and runs at alphaterminal.live.

## Roadmap

- More exchanges beyond Bybit
- Grid & DCA strategies
- Live trading execution
- Macro-signal filters

## Links

- Live: https://alphaterminal.live
- Explorer (agent registration): https://explorer.mantle.xyz/tx/0xca7cfb8bb6ee99112b2c28360967d97d27a9c36c5acb3327792fbe396e62dcd2
- ERC-8004 spec: https://eips.ethereum.org/EIPS/eip-8004
- Hackathon: https://dorahacks.io/hackathon/mantleturingtesthackathon2026
