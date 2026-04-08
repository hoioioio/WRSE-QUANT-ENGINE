# WRSE Quant Engine

Systematic crypto futures research/backtesting engine with walk-forward OOS evaluation and execution-aware simulation.

- Dashboard: [Interactive Backtest Dashboard](https://hoioioio.github.io/WRSE-QUANT-ENGINE/)
- Full portfolio report (1–13 structure): [docs/portfolio.md](docs/portfolio.md)
- Data schema / reproducibility: [docs/reproducibility.md](docs/reproducibility.md)
- Korean README: [README_KOR.md](README_KOR.md)

Notes:
- Raw market data is not included (size/licensing). WRSE reads cached OHLCV (required) and optionally funding/L2 summaries.
- Python 3.11+ required (`tomllib`).

## Performance Snapshot (WFO OOS; 2021–2024)

All metrics are accumulated through walk-forward out-of-sample (OOS) splits. `AB Hybrid` applies an execution model (maker→taker fallback + fees/slippage/funding). `Taker-only` is a harsher stress mode.

| Metric | AB Hybrid | Taker-only |
| :--- | :---: | :---: |
| Total Return | +55.74% | +43.10% |
| CAGR | 11.74% | 9.39% |
| MDD | -11.99% | -12.73% |
| Sharpe | 0.78 | 0.64 |
| Trading Days | 1,457 | 1,457 |

![Equity vs BTC](docs/assets_public/equity_vs_btc_log.png)

## Architecture (High Level)

```text
Market Data (OHLCV / funding / L2 summaries)
  -> Cache Storage
  -> Feature/Signal (Trend + ShockScore)
  -> Walk-forward (train -> lock params/weights -> OOS test)
  -> Simulator (fees/slippage/funding + maker->taker fallback)
  -> Metrics + Report (figures + docs/assets_public/*.json)
```

## Repository Structure

- CLI runner: [cli.py](cli.py)
- Walk-forward engine: [backtest/walkforward.py](backtest/walkforward.py)
- Simulator (fees/slippage/funding): [backtest/simulators.py](backtest/simulators.py)
- Execution model (maker→taker): [execution/models.py](execution/models.py)
- Data loader (cache schema): [data/loader.py](data/loader.py)
- Report export (dashboard JSON): [report.py](report.py)
- Example config: [config/strategy_params.example.toml](config/strategy_params.example.toml)

## How to Run (Reproduce)

Re-running requires your own cache data. See [docs/reproducibility.md](docs/reproducibility.md) for the expected file patterns and columns.

```bash
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt

python scripts/fetch_data.py --config config/strategy_params.example.toml --start 2020-01-01 --end 2024-12-31
python cli.py wfo --config config/strategy_params.example.toml --write_csv ./outputs
python report.py --config config/strategy_params.example.toml --public
python verify_portfolio.py
```

Smoke run:

```bash
python scripts/fetch_data.py --config config/strategy_params.smoke.toml --start 2024-01-01 --end 2024-01-02
python cli.py wfo --config config/strategy_params.smoke.toml
```

If your cache paths differ, update `[data].backtest_cache_dir` / `[data].regime_cache_dir` in [config/strategy_params.example.toml](config/strategy_params.example.toml).
