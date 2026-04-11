import argparse

import numpy as np

from utils.config import Config
from backtest.walkforward import run_wfo_fast


def _fmt_pct(x):
    if x is None or not np.isfinite(float(x)):
        return "nan"
    return f"{float(x)*100:.2f}%"


def _fmt_f(x):
    if x is None or not np.isfinite(float(x)):
        return "nan"
    return f"{float(x):.2f}"


def cmd_wfo(args) -> int:
    cfg = Config.load(args.config).raw
    res = run_wfo_fast(cfg)

    print("WFO_FAST")
    splits = res.get("splits")
    if splits is not None and not splits.empty:
        print("SPLITS")
        print(splits.to_string(index=False))

    for k in ["oos_AB", "oos_AB_taker"]:
        m = res.get(k, {})
        if not m:
            continue
        print(
            k,
            {
                "Total Return": _fmt_pct(m.get("Total Return")),
                "Annual Return": _fmt_pct(m.get("Annual Return")),
                "MDD": _fmt_pct(m.get("MDD")),
                "Sharpe": _fmt_f(m.get("Sharpe Ratio")),
                "Days": int(m.get("Days", 0)),
            },
        )

    if args.write_csv:
        out_dir = Path(args.write_csv)
        out_dir.mkdir(parents=True, exist_ok=True)
        if splits is not None and not splits.empty:
            splits.to_csv(out_dir / "wfo_splits.csv", index=False)
        e1 = res.get("equity_AB")
        if e1 is not None and not e1.empty:
            e1.to_csv(out_dir / "equity_ab.csv", index=False)
        e2 = res.get("equity_AB_taker")
        if e2 is not None and not e2.empty:
            e2.to_csv(out_dir / "equity_ab_taker.csv", index=False)
        y1 = res.get("year_AB")
        if y1 is not None and not y1.empty:
            y1.to_csv(out_dir / "yearly_ab.csv", index=False)
        y2 = res.get("year_AB_taker")
        if y2 is not None and not y2.empty:
            y2.to_csv(out_dir / "yearly_ab_taker.csv", index=False)

    return 0


def cmd_compare(args) -> int:
    cfg = Config.load(args.config).raw
    try:
        from backtest.compare import run_compare
    except Exception:
        print("COMPARE_UNAVAILABLE: backtest.compare is not available in this repository snapshot.")
        return 2
    res = run_compare(cfg, leverage_mult_off=float(args.leverage_off), leverage_mult_on=float(args.leverage_on))
    tbl = res.get("table")
    if tbl is None or tbl.empty:
        print("COMPARE_EMPTY")
        return 1
    out = tbl.copy()
    for c in ["AB_total_return", "AB_annual_return", "AB_mdd", "T_total_return", "T_annual_return", "T_mdd"]:
        out[c] = out[c].apply(lambda x: _fmt_pct(x) if np.isfinite(float(x)) else "nan")
    for c in ["AB_sharpe", "T_sharpe"]:
        out[c] = out[c].apply(lambda x: _fmt_f(x) if np.isfinite(float(x)) else "nan")

    print("COMPARE_TABLE")
    print(out.to_string(index=False))

    if args.write_csv:
        out_dir = Path(args.write_csv)
        out_dir.mkdir(parents=True, exist_ok=True)
        tbl.to_csv(out_dir / "compare_table.csv", index=False)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="wrse")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_wfo = sub.add_parser("wfo", help="Run fast walk-forward evaluation")
    ap_wfo.add_argument("--config", type=str, required=True)
    ap_wfo.add_argument("--write_csv", type=str, default="")
    ap_wfo.set_defaults(func=cmd_wfo)

    ap_cmp = sub.add_parser("compare", help="Compare WFO vs FULLFIT, leverage on/off")
    ap_cmp.add_argument("--config", type=str, required=True)
    ap_cmp.add_argument("--leverage_off", type=float, default=1.0)
    ap_cmp.add_argument("--leverage_on", type=float, default=3.0)
    ap_cmp.add_argument("--write_csv", type=str, default="")
    ap_cmp.set_defaults(func=cmd_compare)

    args = ap.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
