from __future__ import annotations

import numpy as np
import pandas as pd


def calc_equity_metrics(equity_df: pd.DataFrame) -> dict:
    if equity_df is None or equity_df.empty:
        return {}
    eq = equity_df.copy()
    if "time" in eq.columns:
        eq = eq.set_index("time")
    eq = eq.dropna(subset=["capital"])
    if len(eq) < 2:
        return {}
    rets = eq["capital"].pct_change().dropna()
    total_ret = (eq["capital"].iloc[-1] / eq["capital"].iloc[0]) - 1
    annual_ret = total_ret / (len(eq) / 365) if len(eq) > 0 else 0.0
    cum_max = eq["capital"].cummax()
    drawdown = (eq["capital"] - cum_max) / cum_max
    mdd = float(drawdown.min())
    sharpe = float(np.sqrt(365) * rets.mean() / rets.std()) if rets.std() != 0 else 0.0
    return {
        "Total Return": float(total_ret),
        "Annual Return": float(annual_ret),
        "MDD": float(mdd),
        "Sharpe Ratio": float(sharpe),
        "Days": int(len(eq)),
    }


def calc_equity_metrics_ext(equity_df: pd.DataFrame, *, periods_per_year: int = 365) -> dict:
    if equity_df is None or equity_df.empty:
        return {}
    eq = equity_df.copy()
    if "time" in eq.columns:
        eq = eq.set_index("time")
    eq = eq.dropna(subset=["capital"]).sort_index()
    if len(eq) < 2:
        return {}

    cap = eq["capital"].astype(float)
    rets = cap.pct_change().dropna()
    if len(rets) < 2:
        return {}

    total_ret = float((cap.iloc[-1] / cap.iloc[0]) - 1)
    days = int(len(eq))
    years = float(days) / float(periods_per_year) if days > 0 else 0.0
    cagr = float((cap.iloc[-1] / cap.iloc[0]) ** (1.0 / years) - 1.0) if years > 0 else 0.0

    cum_max = cap.cummax()
    drawdown = (cap - cum_max) / cum_max
    mdd = float(drawdown.min())

    avg = float(rets.mean())
    vol = float(rets.std(ddof=1))
    ann_vol = float(vol * np.sqrt(periods_per_year)) if vol > 0 else 0.0
    sharpe = float((avg / vol) * np.sqrt(periods_per_year)) if vol > 0 else 0.0

    down = rets[rets < 0]
    down_std = float(down.std(ddof=1)) if len(down) > 1 else 0.0
    sortino = float((avg / down_std) * np.sqrt(periods_per_year)) if down_std > 0 else 0.0

    calmar = float(cagr / abs(mdd)) if mdd < 0 else 0.0
    win_rate = float((rets > 0).mean())

    peak_flag = cap == cum_max
    last_peak_i = -1
    max_dd_dur = 0
    for i, is_peak in enumerate(peak_flag.to_numpy()):
        if bool(is_peak):
            if last_peak_i >= 0:
                max_dd_dur = max(max_dd_dur, i - last_peak_i)
            last_peak_i = i
    if last_peak_i >= 0:
        max_dd_dur = max(max_dd_dur, (len(cap) - 1) - last_peak_i)

    return {
        "Total Return": float(total_ret),
        "CAGR": float(cagr),
        "MDD": float(mdd),
        "Sharpe Ratio": float(sharpe),
        "Sortino Ratio": float(sortino),
        "Volatility": float(ann_vol),
        "Calmar Ratio": float(calmar),
        "Win Rate": float(win_rate),
        "DD Duration (days)": int(max_dd_dur),
        "Days": int(days),
    }


def link_equity(eq: pd.DataFrame, last_cap: float, *, base_cap: float = 100000.0) -> tuple[pd.DataFrame, float]:
    if eq is None or eq.empty:
        return eq, float(last_cap)
    out = eq.copy()
    shift = float(last_cap) - float(base_cap)
    out["capital"] = out["capital"] + shift
    if "equity" in out.columns:
        out["equity"] = out["equity"] + shift
    last = float(out["capital"].iloc[-1])
    return out, last


def combine_equity(eq_a: pd.DataFrame, eq_b: pd.DataFrame, w_a: float) -> pd.DataFrame:
    if eq_a is None or eq_a.empty or eq_b is None or eq_b.empty:
        return pd.DataFrame()
    a = eq_a.set_index("time").sort_index()
    b = eq_b.set_index("time").sort_index()
    s1 = a["capital"]
    s2 = b["capital"]
    idx = s1.index.union(s2.index).sort_values()
    s1 = s1.reindex(idx).ffill().bfill()
    s2 = s2.reindex(idx).ffill().bfill()
    combo = (s1 * float(w_a)) + (s2 * (1.0 - float(w_a)))
    out = combo.reset_index()
    out.columns = ["time", "capital"]

    if "equity" in a.columns and "equity" in b.columns:
        e1 = a["equity"].reindex(idx).ffill().bfill()
        e2 = b["equity"].reindex(idx).ffill().bfill()
        out["equity"] = ((e1 * float(w_a)) + (e2 * (1.0 - float(w_a)))).to_numpy()

    return out


def year_table(eq: pd.DataFrame) -> pd.DataFrame:
    if eq is None or eq.empty:
        return pd.DataFrame()
    d = eq.copy().set_index("time").sort_index()
    rows = []
    for y, g in d.groupby(d.index.year):
        m = calc_equity_metrics_ext(g.reset_index())
        if not m:
            continue
        rows.append(
            {
                "year": int(y),
                "total_return_pct": float(m.get("Total Return", 0.0)) * 100.0,
                "cagr_pct": float(m.get("CAGR", 0.0)) * 100.0,
                "mdd_pct": float(m.get("MDD", 0.0)) * 100.0,
                "sharpe": float(m.get("Sharpe Ratio", 0.0)),
                "sortino": float(m.get("Sortino Ratio", 0.0)),
                "calmar": float(m.get("Calmar Ratio", 0.0)),
                "volatility_pct": float(m.get("Volatility", 0.0)) * 100.0,
                "win_rate_pct": float(m.get("Win Rate", 0.0)) * 100.0,
                "dd_duration_days": int(m.get("DD Duration (days)", 0)),
                "days": int(m.get("Days", 0)),
            }
        )
    return pd.DataFrame(rows)
