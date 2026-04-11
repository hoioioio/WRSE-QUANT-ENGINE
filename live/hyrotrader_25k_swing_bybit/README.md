## HyroTrader Live (25k, Swing DD) - Bybit Runner

This folder is intentionally separated from research/backtest code. It is designed to:
- run in DRY_RUN by default
- enforce Hyro-style risk constraints at the order layer (stop-loss required, risk cap checks)

### Required environment variables

- `BYBIT_API_KEY`
- `BYBIT_API_SECRET`

Optional:
- `LIVE_MODE=1` to enable real orders (default is dry-run)

### Run (dry-run)

From repository root:

```bash
python -m live.hyrotrader_25k_swing_bybit.bot --config live/hyrotrader_25k_swing_bybit/live_config.toml
```

### Run (live)

```bash
set LIVE_MODE=1
python -m live.hyrotrader_25k_swing_bybit.bot --config live/hyrotrader_25k_swing_bybit/live_config.toml
```

Outputs are written under `live/hyrotrader_25k_swing_bybit/_state/` (not for git).
