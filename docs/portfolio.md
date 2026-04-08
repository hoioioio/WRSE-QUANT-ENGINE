# Remote Crypto Quant / Trader Portfolio (WRSE)

This document follows a submission-style structure. It is intended to be exported to PDF if needed.

Links:
- Dashboard: https://hoioioio.github.io/WRSE-QUANT-ENGINE/
- Data schema / reproducibility: [reproducibility.md](reproducibility.md)
- Repository: this GitHub repo

## 1. Introduction

WRSE is a systematic crypto futures research/backtesting engine for Binance-style perpetuals.
The public artifacts focus on walk-forward out-of-sample (OOS) evaluation and execution-aware simulation assumptions.

Scope:
- Market: crypto futures (perps)
- Instruments: multi-asset universe configured via TOML
- Validation: walk-forward OOS splits (train -> lock params/weights -> test)

Non-scope (public repo):
- Raw market data (size/licensing)
- Private trade-level logs and live API keys

## 2. Trading System Architecture

High-level pipeline:

```text
Market Data (OHLCV / funding / L2 summaries)
  -> Cache Storage
  -> Feature/Signal (Trend + ShockScore)
  -> Walk-forward (train -> lock params/weights -> OOS test)
  -> Simulator (fees/slippage/funding + maker->taker fallback)
  -> Metrics + Report (figures + docs/assets_public/*.json)
  -> Dashboard (docs/index.html)
```

Key modules:
- Signals/features: [../alpha/shock.py](../alpha/shock.py)
- Walk-forward engine: [../backtest/walkforward.py](../backtest/walkforward.py)
- Simulator: [../backtest/simulators.py](../backtest/simulators.py)
- Execution model: [../execution/models.py](../execution/models.py)
- Reporting: [../report.py](../report.py)

## 3. Market Research

Public report focuses on event-style stress slices and distribution-style summaries computed from OOS equity.

Stress slices (examples):
- LUNA deleveraging (2022-05)
- FTX bankruptcy shock (2022-11)

Distribution slice:
- rolling 6-month return distribution computed from daily equity

Supporting artifacts:
- Equity vs BTC (log scale): [assets_public/equity_vs_btc_log.png](assets_public/equity_vs_btc_log.png)
- WFO OOS Sharpe by year: [assets_public/wfo_oos_sharpe.png](assets_public/wfo_oos_sharpe.png)

## 4. Strategy Research

Strategy components are separated and then combined via walk-forward weight selection.

### 4.1 Trend component

Summary:
- Uses higher timeframe bars internally (resampled to 4h from cache timeframe).
- Enters when short/mid-term reversal aligns with a longer-term baseline direction.
- Uses filters (volatility/ADX/funding/shock) to control participation.

### 4.2 Shock component (ShockScore)

Summary:
- Labels jump events and trains a Ridge-based signed classifier on the train window.
- On the test window, it only infers `shock_score` (no re-training).
- Used for entry avoidance, de-risking, and execution conservatism.

### 4.3 Ensemble (Trend + Shock)

Summary:
- Searches `weights_grid` on the train window.
- Locks the selected weight for the subsequent test year.

## 5. Backtesting Framework

Backtest is designed to include common sources of live-trading performance decay:
- Fees (maker/taker)
- Slippage
- Funding rates (if cache exists; otherwise assumed 0)
- Unfilled limit orders via maker→taker fallback execution model
- Multi-asset portfolio simulation

Key implementations:
- Simulator: [../backtest/simulators.py](../backtest/simulators.py)
- WFO runner: [../backtest/walkforward.py](../backtest/walkforward.py)
- Config: [../config/strategy_params.example.toml](../config/strategy_params.example.toml)

## 6. Portfolio Construction

Universe and portfolio rules are specified in TOML:
- Symbols: `[data].symbols`
- Max concurrent positions: `[risk].portfolio_slots`
- Trend/Shock allocation: `[walk_forward].weights_grid` (selected on train, locked on test)

Reference:
- Example config: [../config/strategy_params.example.toml](../config/strategy_params.example.toml)

## 7. Risk Management

Public configuration and logic cover:
- Risk-per-trade sizing (`risk_per_trade`)
- Stop-loss parameters for components (`stop_loss_pct_trend`, `stop_loss_pct_shock`)
- Portfolio slots (concentration control)
- Drawdown-based scaling (risk reduction under drawdown states)
- Funding risk suppression (if funding cache exists)

Reference:
- Config: [../config/strategy_params.example.toml](../config/strategy_params.example.toml)
- Walk-forward logic: [../backtest/walkforward.py](../backtest/walkforward.py)

## 8. Execution System

Execution model is explicitly simulated as part of backtesting:
- Maker attempts with L2 summary features if available
- Fallback to taker if unfilled (costlier fill assumption)
- Slippage and fees applied according to mode

Reference:
- Execution model: [../execution/models.py](../execution/models.py)
- Data schema (L2 summaries): [reproducibility.md](reproducibility.md)

## 9. Walk-forward & Validation

Validation rules:
- OOS-only accumulation (reporting focuses on test windows)
- Parameters and ensemble weights are derived from train windows only
- Split-by-year testing over the configured years

Artifacts:
- WFO splits table: [assets_public/wfo_splits.json](assets_public/wfo_splits.json)
- WFO OOS Sharpe plot: [assets_public/wfo_oos_sharpe.png](assets_public/wfo_oos_sharpe.png)

## 10. Live Trading / Paper Trading

This repository does not include live API keys or complete order logs.

Operational principles used in predecessor live systems:
- Exchange ledger as source of truth
- Reconciliation cycle for positions and open orders
- Use of idempotent order keys

## 11. Performance Analysis

### 11.1 WFO OOS summary (2021–2024)

| Metric | AB Hybrid (exec-aware) | Taker-only (stress) |
| :--- | :---: | :---: |
| Cumulative Return | +55.74% | +43.10% |
| CAGR | 11.74% | 9.39% |
| MDD | -11.99% | -12.73% |
| Sharpe | 0.78 | 0.64 |
| Trading Days | 1,457 | 1,457 |

Equity curves:
- [assets_public/equity_ab.json](assets_public/equity_ab.json)
- [assets_public/equity_ab_taker.json](assets_public/equity_ab_taker.json)

Figure:
- [assets_public/equity_vs_btc_log.png](assets_public/equity_vs_btc_log.png)

### 11.2 Stress tests

Representative OOS event slices:
- LUNA deleveraging: 2022-05-07 ~ 2022-06-30
- FTX bankruptcy shock: 2022-11-06 ~ 2022-12-31

### 11.3 Notes on public metrics

- Trade-level logs are not included in the public repo.
- A public run reproduces the dashboard artifacts when the same cache data is provided.

## 12. Conclusion

The public deliverables demonstrate:
- Walk-forward OOS evaluation with locked parameters/weights per split
- Execution-aware simulation assumptions (fees/slippage/funding + maker→taker fallback)
- Reproducible reporting artifacts used by a static dashboard

Limitations:
- Raw market data not included
- No live keys / complete order logs in repository

## 13. GitHub Repository

Entry points:
- Run evaluation: [../cli.py](../cli.py)
- Generate dashboard artifacts: [../report.py](../report.py)
- Validate published equity summaries: [../verify_portfolio.py](../verify_portfolio.py)

How to reproduce:
- Follow [reproducibility.md](reproducibility.md) to prepare cache inputs
- Run the commands listed in README
