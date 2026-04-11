import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from utils.config import Config


def _to_dt(s: pd.Series) -> pd.Series:
    x = pd.to_datetime(s, errors="coerce", utc=True)
    if x.dt.tz is None:
        x = x.dt.tz_localize("UTC")
    return x


def validate(*, cfg_path: str, out_dir: str) -> dict:
    cfg = Config.load(cfg_path).raw
    prop = cfg.get("prop", {})
    initial_capital = float(prop.get("initial_capital", 25000.0))
    daily_dd_pct = float(prop.get("daily_dd_pct", 0.05))
    max_loss_pct = float(prop.get("max_loss_pct", 0.10))

    outp = Path(out_dir)
    tr = pd.read_csv(outp / "trades_ab.csv")
    eq = pd.read_csv(outp / "equity_ab.csv")

    tr["exit_time"] = _to_dt(tr["exit_time"])
    tr["day"] = tr["exit_time"].dt.floor("D")

    min_trade_value = 0.05 * initial_capital
    tr["trade_value"] = pd.to_numeric(tr.get("trade_value"), errors="coerce")
    tr["pnl_pct"] = pd.to_numeric(tr.get("pnl_pct"), errors="coerce")
    tr["risk_to_sl"] = pd.to_numeric(tr.get("risk_to_sl"), errors="coerce")
    tr["pnl"] = pd.to_numeric(tr.get("pnl"), errors="coerce")
    tr["pnl_pos"] = tr["pnl"].where(tr["pnl"] > 0, 0.0)

    q = tr[(tr["trade_value"] >= float(min_trade_value)) & (tr["pnl_pct"].abs() >= 0.01)]
    valid_days = sorted(q["day"].dropna().unique().tolist())

    pos_total = float(tr["pnl_pos"].sum())
    daily_pos = tr.groupby("day", dropna=True)["pnl_pos"].sum().sort_index()
    daily_pos_max = float(daily_pos.max()) if len(daily_pos) else 0.0
    profit_dist_ok = True
    profit_dist_ratio = np.nan
    if pos_total > 0:
        profit_dist_ratio = float(daily_pos_max / pos_total)
        profit_dist_ok = profit_dist_ratio <= 0.40 + 1e-12

    risk_cap = 0.03 * initial_capital
    risk_viol = tr[(tr["risk_to_sl"].abs() > float(risk_cap)) & np.isfinite(tr["risk_to_sl"])]

    eq["time"] = _to_dt(eq["time"])
    eq = eq.dropna(subset=["time"]).sort_values("time")
    eq["equity"] = pd.to_numeric(eq.get("equity", np.nan), errors="coerce")
    eq = eq.dropna(subset=["equity"])
    eq["day"] = eq["time"].dt.floor("D")

    dd_rows = []
    for d, g in eq.groupby("day"):
        g = g.sort_values("time")
        start_eq = float(g["equity"].iloc[0])
        floor = float(start_eq) - float(initial_capital) * float(daily_dd_pct)
        min_eq = float(g["equity"].min())
        dd_rows.append({"day": str(d.date()), "start_equity": start_eq, "floor": floor, "min_equity": min_eq, "ok": bool(min_eq > floor)})
    dd_ok = all(bool(r["ok"]) for r in dd_rows) if dd_rows else True

    max_loss_floor = float(initial_capital) * (1.0 - float(max_loss_pct))
    min_eq_all = float(eq["equity"].min()) if len(eq) else float("nan")
    max_loss_ok = bool(min_eq_all > max_loss_floor) if np.isfinite(min_eq_all) else True

    return {
        "initial_capital": initial_capital,
        "min_trade_value": float(min_trade_value),
        "valid_trading_days_count": int(len(valid_days)),
        "valid_trading_days": [str(pd.Timestamp(x).date()) for x in valid_days],
        "profit_distribution": {"total_positive_profit": pos_total, "max_daily_positive_profit": daily_pos_max, "max_ratio": profit_dist_ratio, "ok": bool(profit_dist_ok)},
        "max_risk_per_position": {"cap": float(risk_cap), "violations": int(len(risk_viol))},
        "swing_daily_dd": {"daily_dd_pct": daily_dd_pct, "days_checked": int(len(dd_rows)), "ok": bool(dd_ok), "detail": dd_rows[:31]},
        "max_loss": {"max_loss_pct": max_loss_pct, "floor": float(max_loss_floor), "min_equity": min_eq_all, "ok": bool(max_loss_ok)},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, type=str)
    ap.add_argument("--out", required=True, type=str)
    args = ap.parse_args()
    rep = validate(cfg_path=args.config, out_dir=args.out)
    p = Path(args.out) / "hyro_rules_report.json"
    p.write_text(json.dumps(rep, indent=2), encoding="utf-8")
    print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
