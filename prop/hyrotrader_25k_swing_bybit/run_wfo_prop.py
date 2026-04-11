import argparse
from pathlib import Path

from backtest.walkforward import run_wfo_fast
from utils.config import Config


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, type=str)
    ap.add_argument("--out", required=True, type=str)
    args = ap.parse_args()

    cfg = Config.load(args.config).raw
    res = run_wfo_fast(cfg)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    splits = res.get("splits")
    if splits is not None and not splits.empty:
        splits.to_csv(out_dir / "wfo_splits.csv", index=False)

    for k, fn in [
        ("equity_AB", "equity_ab.csv"),
        ("equity_AB_taker", "equity_ab_taker.csv"),
        ("trades_AB", "trades_ab.csv"),
        ("trades_AB_taker", "trades_ab_taker.csv"),
        ("year_AB", "yearly_ab.csv"),
        ("year_AB_taker", "yearly_ab_taker.csv"),
    ]:
        df = res.get(k)
        if df is not None and hasattr(df, "empty") and not df.empty:
            df.to_csv(out_dir / fn, index=False)

    from prop.hyrotrader_25k_swing_bybit.validate_hyro_rules import validate

    rep = validate(cfg_path=args.config, out_dir=str(out_dir))
    (out_dir / "hyro_rules_report.json").write_text(__import__("json").dumps(rep, indent=2), encoding="utf-8")
    print(out_dir / "hyro_rules_report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
