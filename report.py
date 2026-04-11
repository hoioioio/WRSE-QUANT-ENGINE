import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from utils.config import Config
from backtest.walkforward import run_wfo_fast
from data.loader import DataSpec, load_universe


@dataclass(frozen=True)
class ReportResult:
    ok: bool
    detail: str


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_json(p: Path, obj: object) -> None:
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def _export_equity_json(out_dir: Path, eq_df, *, public: bool, name: str) -> None:
    if eq_df is None or len(eq_df) == 0:
        return
    d = eq_df.copy()
    if "time" not in d.columns:
        d = d.reset_index().rename(columns={"index": "time"})
    d = d.dropna(subset=["time", "capital"])[["time", "capital"]].copy()
    if len(d) < 2:
        return
    d["time"] = pd.to_datetime(d["time"]).dt.strftime("%Y-%m-%d")
    d["capital"] = d["capital"].astype(float)
    if public:
        base = float(d["capital"].iloc[0])
        if base != 0:
            d["capital"] = d["capital"] / base
    _write_json(out_dir / name, d.to_dict(orient="records"))


def _export_table_json(out_dir: Path, df, *, name: str) -> None:
    if df is None or getattr(df, "empty", True):
        return
    _write_json(out_dir / name, df.to_dict(orient="records"))


def run_report(
    *,
    config_path: str,
    out_dir: str,
    public: bool,
    no_plots: bool,
    no_benchmark: bool,
) -> ReportResult:
    cfg = Config.load(config_path).raw
    res = run_wfo_fast(cfg)

    out_path = Path(out_dir)
    _ensure_dir(out_path)

    eq_ab = res.get("equity_AB")
    eq_ab_t = res.get("equity_AB_taker")

    bench = None
    if not no_plots and not no_benchmark:
        data = cfg.get("data", {})
        spec = DataSpec(
            backtest_cache_dir=str(data.get("backtest_cache_dir", r"c:\backtest_cache")),
            regime_cache_dir=str(data.get("regime_cache_dir", r"c:\alpha_cache")),
            timeframe=str(data.get("timeframe", "15m")),
        )
        symbols = list(data.get("symbols", []))
        df_dict = load_universe(spec, symbols)
        btc = df_dict.get("BTC_USDT")
        bench = btc[["close"]].rename(columns={"close": "btc_close"}) if btc is not None and not btc.empty else None

    def _prep_series(eq_df):
        if eq_df is None or len(eq_df) == 0:
            return None
        s = eq_df.copy()
        if "time" in s.columns:
            s = s.set_index("time")
        s = s.sort_index()["capital"].astype(float)
        s = s.replace([np.inf, -np.inf], np.nan).dropna()
        if len(s) < 2:
            return None
        if public:
            s = s / float(s.iloc[0])
        return s

    def _prep_btc(bench_df, idx):
        if bench_df is None or bench_df.empty:
            return None
        s = bench_df["btc_close"].astype(float).replace([np.inf, -np.inf], np.nan).dropna()
        s = s.reindex(idx).ffill().bfill()
        if public:
            s = s / float(s.iloc[0])
        return s

    splits = res.get("splits")
    if splits is not None and not splits.empty:
        _export_table_json(out_path, splits, name="wfo_splits.json")
        if not no_plots:
            fig = plt.figure(figsize=(10, 3.2))
            ax = fig.add_subplot(111)
            x = splits["test"].astype(int).tolist()
            ax.plot(x, splits["AB_sharpe"].astype(float).tolist(), marker="o", label="AB (exec-aware)")
            ax.plot(x, splits["AB_taker_sharpe"].astype(float).tolist(), marker="o", label="AB (taker-only)")
            ax.axhline(0.0, color="black", linewidth=1)
            ax.set_title("Walk-forward OOS Sharpe by test year")
            ax.set_xlabel("Test year")
            ax.set_ylabel("Sharpe")
            ax.grid(True, alpha=0.3)
            ax.legend(loc="best")
            fig.tight_layout()
            fig.savefig(out_path / "wfo_oos_sharpe.png", dpi=160)
            plt.close(fig)

    s_ab = _prep_series(eq_ab)
    s_ab_t = _prep_series(eq_ab_t)
    _export_equity_json(out_path, eq_ab, public=bool(public), name="equity_ab.json")
    _export_equity_json(out_path, eq_ab_t, public=bool(public), name="equity_ab_taker.json")
    if not no_plots and s_ab is not None:
        fig = plt.figure(figsize=(10, 3.8))
        ax = fig.add_subplot(111)
        ax.plot(s_ab.index, s_ab.values, label="Strategy (exec-aware)")
        if s_ab_t is not None:
            ax.plot(s_ab_t.index, s_ab_t.values, label="Strategy (taker-only)")
        if bench is not None:
            s_btc = _prep_btc(bench, s_ab.index)
            if s_btc is not None:
                ax.plot(s_btc.index, s_btc.values, label="BTC Buy & Hold")
        ax.set_yscale("log")
        ax.set_title("Strategy Equity vs BTC Benchmark")
        ax.set_xlabel("Date")
        ax.set_ylabel("Equity (normalized, log)" if public else "Equity ($, log)")
        ax.grid(True, alpha=0.25)
        ax.legend(loc="best")
        if public:
            ax.tick_params(axis="y", which="both", labelleft=False)
        fig.tight_layout()
        fig.savefig(out_path / "equity_vs_btc_log.png", dpi=160)
        plt.close(fig)

    y_ab = res.get("year_AB")
    y_t = res.get("year_AB_taker")
    if y_ab is not None and not y_ab.empty:
        _export_table_json(out_path, y_ab, name="yearly_ab.json")
        _export_table_json(out_path, y_t, name="yearly_ab_taker.json")
        if not no_plots:
            fig = plt.figure(figsize=(10, 3.2))
            ax = fig.add_subplot(111)
            x = y_ab["year"].astype(int).tolist()
            ax.bar([v - 0.15 for v in x], y_ab["total_return_pct"].astype(float).tolist(), width=0.3, label="AB (exec-aware)")
            if y_t is not None and not y_t.empty:
                ax.bar([v + 0.15 for v in x], y_t["total_return_pct"].astype(float).tolist(), width=0.3, label="AB (taker-only)")
            ax.set_title("Yearly total return (%)")
            ax.set_xlabel("Year")
            ax.set_ylabel("Total return (%)")
            ax.grid(True, axis="y", alpha=0.3)
            ax.legend(loc="best")
            fig.tight_layout()
            fig.savefig(out_path / "yearly_returns.png", dpi=160)
            plt.close(fig)

    if not no_plots and y_ab is not None and not y_ab.empty:
        fig = plt.figure(figsize=(10, 3.2))
        ax = fig.add_subplot(111)
        x = y_ab["year"].astype(int).tolist()
        ax.plot(x, y_ab["mdd_pct"].astype(float).tolist(), marker="o", label="AB (exec-aware)")
        if y_t is not None and not y_t.empty:
            ax.plot(x, y_t["mdd_pct"].astype(float).tolist(), marker="o", label="AB (taker-only)")
        ax.set_title("Yearly max drawdown (%)")
        ax.set_xlabel("Year")
        ax.set_ylabel("MDD (%)")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best")
        fig.tight_layout()
        fig.savefig(out_path / "yearly_mdd.png", dpi=160)
        plt.close(fig)

    return ReportResult(ok=True, detail=str(out_path))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=str, required=True)
    ap.add_argument("--out_dir", type=str, default=str(Path("docs") / "assets_public"))
    ap.add_argument("--public", action="store_true")
    ap.add_argument("--no_plots", action="store_true")
    ap.add_argument("--no_benchmark", action="store_true")
    args = ap.parse_args()
    rr = run_report(
        config_path=args.config,
        out_dir=args.out_dir,
        public=bool(args.public),
        no_plots=bool(args.no_plots),
        no_benchmark=bool(args.no_benchmark),
    )
    print(f"Wrote report images to: {rr.detail}")
    return 0 if rr.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
