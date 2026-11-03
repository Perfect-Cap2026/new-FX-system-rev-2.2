# FIP — Financial Intelligence Platform

A local, single-trader analysis desk that runs eight analysis engines over every instrument on your watchlist, combines them with your weights (25/20/20/15/10/10), and gates the result through prop-firm risk rules.

> Research tool, not investment advice. Scores are model outputs from free, delayed data and documented heuristics.

## What you get

| Area | In this MVP |
|---|---|
| **Desk** (`/`) | Executive summary, risk panel, ranked watchlist with every module's score, trade opportunities, conviction-weighted portfolio suggestion (de-duplicates correlated positions), sector rotation, central-bank table, geopolitical headline flags |
| **Asset page** (`/asset/EURUSD=X`) | Conviction strip (every module on one −100…+100 axis), investment thesis, TradingView chart, trade setup with entry/stop/3 targets and R:R, A+ risk gate, levels map, SMC structure/FVG/order blocks/liquidity/sweeps, probability matrix, bull/base/bear scenarios, multi-timeframe table, scored news |
| **Macro** | Inflation direction, growth momentum, rates & curve, recession probability (curve probit + Sahm + HY spreads), Fed net liquidity, data-surprise score, TradingView economic calendar |
| **Intermarket** | 60-day correlation matrix (DXY, gold, silver, oil, US10Y, VIX, S&P, Nasdaq, BTC), lead/lag, drivers, PC1, risk-on/off regime |
| **Screener & heatmap**, **News & calendar** | Official TradingView widgets |
| **Journal & risk** | Position-size calculator with prop-firm checks, trade journal with R-multiples and win rate, price alerts |
| **Platform** | JWT auth (bcrypt), PostgreSQL/SQLite, Redis/in-memory cache, JSON logs with request ids, Prometheus `/metrics`, OpenAPI at `/docs`, 45 tests, Docker, CI, K8s starter |

Full design: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — architecture, data flow, module specs, schema, API, agent workflow, security, roadmap.

## Run it

**Docker (recommended)**
```bash
cp .env.example .env          # set JWT_SECRET: openssl rand -hex 32
docker compose up --build     # → http://localhost:3000, create an account
```

**Without Docker** (Python 3.12+, Node 22+)
```bash
cd backend && pip install -r requirements-dev.txt && cd ..
cd frontend && npm install && cd ..
make dev-api     # terminal 1 — live Yahoo + FRED data
make dev-web     # terminal 2 — http://localhost:3000
```
No internet or just want to look around? `make demo` runs the API on synthetic prices (clearly fake values).

**Tests:** `make test`

## Data sources

| Source | Used for | Key |
|---|---|---|
| Yahoo Finance (`yfinance`) | OHLCV (1h/1d/1wk), stock fundamentals, analyst ratings, headlines | none |
| FRED | CPI, PCE, PPI, payrolls, retail sales, IP, inventories, yields, breakevens, HY spreads, Fed balance sheet/TGA/RRP, Sahm | optional (`FRED_API_KEY`) |
| TradingView widgets | Charts, economic calendar, heatmap, screener, news timeline | none |
| `backend/app/data/central_banks.yaml` | Non-US policy rates and bias for FX | edit after each meeting |
| Claude API | Investment thesis prose (written only from the computed signals) | optional (`ANTHROPIC_API_KEY`) |

**About TradingView data:** TradingView has no public data API for apps. Your TradingView connection in Claude lets *me* read it, but this app can't. The app therefore embeds TradingView's official widgets for charts/calendar/heatmap and runs its analysis on Yahoo + FRED. Polygon, AlphaVantage, NewsAPI or a broker feed slot in behind `app/providers/base.py` without touching the engines.

Symbols use Yahoo format: `EURUSD=X`, `GC=F` (gold), `CL=F` (oil), `^GSPC`, `^NDX`, `BTC-USD`, `AAPL`.

## Honest limits

- **Institutional/SMC** is detected from OHLCV price signatures (structure, FVGs, order blocks, sweeps, A/D divergence). Real order flow needs tick/L2 data; CFTC COT is the next free addition.
- **Weights are a prior, not a validated model.** Phase 2 of the roadmap is a walk-forward backtest; until then treat the composite as a structured checklist.
- **Central-bank table** was filled from public trackers on 31 Oct 2026; verify it, and update AUD after today's RBA decision.
- **Yahoo data is delayed** and unofficial — fine for swing analysis, not for execution.
- **Alerts** are evaluated when you open the Journal page; background push alerts are Phase 4.

## Layout
```
backend/app/
  engines/      macro · micro · fundamental · smc · technical · sentiment · intermarket · risk · decision
  providers/    yahoo · fred · synthetic  (behind one interface)
  api/routes.py services.py (orchestrator) · core/ (config, auth, cache, logging/metrics)
frontend/app/   desk · asset/[symbol] · macro · intermarket · markets · news · journal · login
docs/ARCHITECTURE.md   deploy/k8s/   .github/workflows/ci.yml   docker-compose.yml
```

Tune everything (weights, risk rules, watchlist) in `.env`.
