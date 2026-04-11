from __future__ import annotations

import numpy as np
import pandas as pd

from alpha.shock import build_train_matrix, fit_ridge_signed_classifier, build_feature_frame, predict_score
from backtest.metrics import calc_equity_metrics, combine_equity, link_equity, year_table
from backtest.simulators import simulate_v2xa, simulate_shockscore
from data.loader import DataSpec, load_universe


def _score_for_search(trades: pd.DataFrame, equity: pd.DataFrame) -> float | None:
    m = calc_equity_metrics(equity)
    if not m:
        return None
    shr = float(m.get("Sharpe Ratio", 0.0))
    tot = float(m.get("Total Return", 0.0))
    mdd = float(m.get("MDD", 0.0))
    tr_cnt = int(len(trades)) if trades is not None else 0
    if tr_cnt < 50:
        return None
    score = shr
    if tot <= 0:
        score -= 0.75
    score += max(-0.3, mdd) / 10.0
    return float(score)


def _simulate_v2xa_years(
    df_dict: dict[str, pd.DataFrame],
    years: list[int],
    *,
    fund_params: dict,
    avoid_th: float,
    exit_on_flip: bool,
    taker_fee_rate: float,
    maker_fee_rate: float,
    slip_bps: float,
    sl_pct: float,
    size_k: float,
    min_mult: float,
    max_mult: float,
    exec_mode: str,
    portfolio_slots: int,
    risk_per_trade: float,
    leverage_mult: float,
    notional_cap: float,
    enable_vol_targeting: bool,
    vol_ratio_floor: float,
    vol_ratio_cap: float,
    vol_ratio_power: float,
    dd_threshold_1: float,
    dd_threshold_2: float,
    dd_scale_1: float,
    dd_scale_2: float,
    initial_capital: float = 100000.0,
    record_equity_every_bar: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    trades_all = []
    eq_all = []
    last = float(initial_capital)
    for y in [int(x) for x in years]:
        tr, eq = simulate_v2xa(
            df_dict,
            year=int(y),
            fund_params=fund_params,
            avoid_th=float(avoid_th),
            exit_on_flip=bool(exit_on_flip),
            taker_fee_rate=float(taker_fee_rate),
            maker_fee_rate=float(maker_fee_rate),
            slip_bps=float(slip_bps),
            sl_pct=float(sl_pct),
            size_k=float(size_k),
            min_mult=float(min_mult),
            max_mult=float(max_mult),
            exec_mode=str(exec_mode),
            portfolio_slots=int(portfolio_slots),
            risk_per_trade=float(risk_per_trade),
            leverage_mult=float(leverage_mult),
            notional_cap=float(notional_cap),
            enable_vol_targeting=bool(enable_vol_targeting),
            vol_ratio_floor=float(vol_ratio_floor),
            vol_ratio_cap=float(vol_ratio_cap),
            vol_ratio_power=float(vol_ratio_power),
            dd_threshold_1=float(dd_threshold_1),
            dd_threshold_2=float(dd_threshold_2),
            dd_scale_1=float(dd_scale_1),
            dd_scale_2=float(dd_scale_2),
            initial_capital=float(initial_capital),
            record_equity_every_bar=bool(record_equity_every_bar),
        )
        if tr is not None and not tr.empty:
            trades_all.append(tr)
        if eq is not None and not eq.empty:
            eq, last = link_equity(eq, last, base_cap=float(initial_capital))
            eq_all.append(eq)
    return (pd.concat(trades_all) if trades_all else pd.DataFrame(), pd.concat(eq_all) if eq_all else pd.DataFrame())


def _simulate_shock_years(
    df_dict: dict[str, pd.DataFrame],
    years: list[int],
    *,
    entry_th: float,
    max_hold: int,
    sl_pct: float,
    taker_fee_rate: float,
    maker_fee_rate: float,
    slip_bps: float,
    size_pow: float,
    max_mult: float,
    exec_mode: str,
    portfolio_slots: int,
    risk_per_trade: float,
    leverage_mult: float,
    notional_cap: float,
    enable_vol_targeting: bool,
    vol_ratio_floor: float,
    vol_ratio_cap: float,
    vol_ratio_power: float,
    dd_threshold_1: float,
    dd_threshold_2: float,
    dd_scale_1: float,
    dd_scale_2: float,
    initial_capital: float = 100000.0,
    record_equity_every_bar: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    trades_all = []
    eq_all = []
    last = float(initial_capital)
    for y in [int(x) for x in years]:
        tr, eq = simulate_shockscore(
            df_dict,
            year=int(y),
            entry_th=float(entry_th),
            max_hold=int(max_hold),
            sl_pct=float(sl_pct),
            taker_fee_rate=float(taker_fee_rate),
            maker_fee_rate=float(maker_fee_rate),
            slip_bps=float(slip_bps),
            size_pow=float(size_pow),
            max_mult=float(max_mult),
            exec_mode=str(exec_mode),
            portfolio_slots=int(portfolio_slots),
            risk_per_trade=float(risk_per_trade),
            leverage_mult=float(leverage_mult),
            notional_cap=float(notional_cap),
            enable_vol_targeting=bool(enable_vol_targeting),
            vol_ratio_floor=float(vol_ratio_floor),
            vol_ratio_cap=float(vol_ratio_cap),
            vol_ratio_power=float(vol_ratio_power),
            dd_threshold_1=float(dd_threshold_1),
            dd_threshold_2=float(dd_threshold_2),
            dd_scale_1=float(dd_scale_1),
            dd_scale_2=float(dd_scale_2),
            initial_capital=float(initial_capital),
            record_equity_every_bar=bool(record_equity_every_bar),
        )
        if tr is not None and not tr.empty:
            trades_all.append(tr)
        if eq is not None and not eq.empty:
            eq, last = link_equity(eq, last, base_cap=float(initial_capital))
            eq_all.append(eq)
    return (pd.concat(trades_all) if trades_all else pd.DataFrame(), pd.concat(eq_all) if eq_all else pd.DataFrame())


def run_wfo_fast(cfg: dict) -> dict[str, object]:
    data = cfg["data"]
    exec_cfg = cfg["execution"]
    wf = cfg["walk_forward"]
    shock = cfg["shock_model"]
    risk = cfg["risk"]
    prop = cfg.get("prop", {})

    spec = DataSpec(
        backtest_cache_dir=str(data["backtest_cache_dir"]),
        regime_cache_dir=str(data["regime_cache_dir"]),
        timeframe=str(data["timeframe"]),
    )
    symbols = list(data["symbols"])
    df_dict = load_universe(spec, symbols)

    years_all = [int(x) for x in wf["years"]]
    splits = []
    for i, test_year in enumerate(years_all[1:], start=1):
        splits.append({"train": years_all[:i], "test": test_year})

    weights = [float(x) for x in wf["weights_grid"]]
    n_iter_v2 = int(wf.get("v2_param_samples", 20))

    taker_fee_rate = float(exec_cfg["taker_fee_rate"])
    maker_fee_rate = float(exec_cfg["maker_fee_rate"])
    slip_bps = float(exec_cfg["slippage_bps"])
    exec_mode = str(exec_cfg["exec_mode"])

    enable_vol_targeting = bool(risk.get("enable_vol_targeting", False))
    vol_ratio_floor = float(risk.get("vol_ratio_floor", 0.8))
    vol_ratio_cap = float(risk.get("vol_ratio_cap", 1.6))
    vol_ratio_power = float(risk.get("vol_ratio_power", 1.0))
    dd_threshold_1 = float(risk.get("dd_threshold_1", 0.05))
    dd_threshold_2 = float(risk.get("dd_threshold_2", 0.10))
    dd_scale_1 = float(risk.get("dd_scale_1", 0.7))
    dd_scale_2 = float(risk.get("dd_scale_2", 0.4))
    leverage_mult = float(risk.get("leverage_mult", 1.0))
    notional_cap = float(risk.get("notional_cap", 0.0))
    initial_capital = float(prop.get("initial_capital", 100000.0))
    record_equity_every_bar = bool(prop.get("record_equity_every_bar", False))

    eq_ab = []
    eq_ab_taker = []
    last_ab = float(initial_capital)
    last_ab_t = float(initial_capital)
    split_rows = []
    trades_ab = []
    trades_ab_taker = []

    for si, sp in enumerate(splits, start=1):
        train_years = sp["train"]
        test_year = sp["test"]

        xz, y, mu, sig = build_train_matrix(
            df_dict,
            train_years,
            horizon=int(shock["horizon_bars"]),
            thr=float(shock["label_threshold"]),
            neg_ratio=float(shock["neg_ratio"]),
        )
        if xz is None:
            continue
        model = fit_ridge_signed_classifier(xz, y, l2=float(shock["ridge_l2"]))
        for sym, df in df_dict.items():
            x_full = build_feature_frame(df)
            xz_full = (x_full - mu) / sig
            df["shock_score"] = predict_score(model, xz_full)

        fund_abs_max = [0.00010, 0.00015, 0.00020]
        fund_z_max = [0.8, 1.0]
        pyr = [0.015, 0.02]
        rng = np.random.default_rng(9000 + int(si))
        train_eval_years = [int(train_years[-1])]

        def pick_best_v2xa(size_k_space, n_iter):
            best = None
            best_cfg = None
            for _ in range(int(n_iter)):
                cfg_v = {
                    "fund_abs_max": float(rng.choice(fund_abs_max)),
                    "fund_z_max": float(rng.choice(fund_z_max)),
                    "pyr_trig": float(rng.choice(pyr)),
                    "avoid_th": float(rng.choice([0.08, 0.10, 0.12])),
                    "adx_min": float(rng.choice([0.0, 12.0, 15.0, 18.0])),
                    "exit_on_flip": True,
                    "size_k": float(rng.choice(size_k_space)),
                }
                tr, eq = _simulate_v2xa_years(
                    df_dict,
                    train_eval_years,
                    fund_params=cfg_v,
                    avoid_th=float(cfg_v["avoid_th"]),
                    exit_on_flip=bool(cfg_v["exit_on_flip"]),
                    taker_fee_rate=taker_fee_rate,
                    maker_fee_rate=maker_fee_rate,
                    slip_bps=slip_bps,
                    sl_pct=float(risk["stop_loss_pct_trend"]),
                    size_k=float(cfg_v["size_k"]),
                    min_mult=0.2,
                    max_mult=1.2,
                    exec_mode=exec_mode,
                    portfolio_slots=int(risk["portfolio_slots"]),
                    risk_per_trade=float(risk["risk_per_trade"]),
                    leverage_mult=leverage_mult,
                    notional_cap=notional_cap,
                    enable_vol_targeting=enable_vol_targeting,
                    vol_ratio_floor=vol_ratio_floor,
                    vol_ratio_cap=vol_ratio_cap,
                    vol_ratio_power=vol_ratio_power,
                    dd_threshold_1=dd_threshold_1,
                    dd_threshold_2=dd_threshold_2,
                    dd_scale_1=dd_scale_1,
                    dd_scale_2=dd_scale_2,
                )
                s = _score_for_search(tr, eq)
                if s is None:
                    continue
                if best is None or s > best:
                    best = s
                    best_cfg = cfg_v
            return best_cfg

        cfg_v2xa_b = pick_best_v2xa([0.2, 0.3, 0.4], n_iter=n_iter_v2) or {
            "fund_abs_max": 0.00015,
            "fund_z_max": 1.0,
            "pyr_trig": 0.015,
            "avoid_th": 0.10,
            "adx_min": 12.0,
            "exit_on_flip": True,
            "size_k": 0.25,
        }

        shock_cfg = {
            "entry_th": 0.12,
            "max_hold": 3,
            "sl_pct": float(risk["stop_loss_pct_shock"]),
        }

        tr_b_in, eq_b_in = _simulate_v2xa_years(
            df_dict,
            train_eval_years,
            fund_params=cfg_v2xa_b,
            avoid_th=float(cfg_v2xa_b["avoid_th"]),
            exit_on_flip=bool(cfg_v2xa_b["exit_on_flip"]),
            taker_fee_rate=taker_fee_rate,
            maker_fee_rate=maker_fee_rate,
            slip_bps=slip_bps,
            sl_pct=float(risk["stop_loss_pct_trend"]),
            size_k=float(cfg_v2xa_b["size_k"]),
            min_mult=0.2,
            max_mult=1.2,
            exec_mode=exec_mode,
            portfolio_slots=int(risk["portfolio_slots"]),
            risk_per_trade=float(risk["risk_per_trade"]),
            leverage_mult=leverage_mult,
            notional_cap=notional_cap,
            enable_vol_targeting=enable_vol_targeting,
            vol_ratio_floor=vol_ratio_floor,
            vol_ratio_cap=vol_ratio_cap,
            vol_ratio_power=vol_ratio_power,
            dd_threshold_1=dd_threshold_1,
            dd_threshold_2=dd_threshold_2,
            dd_scale_1=dd_scale_1,
            dd_scale_2=dd_scale_2,
            initial_capital=initial_capital,
            record_equity_every_bar=record_equity_every_bar,
        )
        tr_s_in, eq_s_in = _simulate_shock_years(
            df_dict,
            train_eval_years,
            entry_th=float(shock_cfg["entry_th"]),
            max_hold=int(shock_cfg["max_hold"]),
            sl_pct=float(shock_cfg["sl_pct"]),
            taker_fee_rate=taker_fee_rate,
            maker_fee_rate=maker_fee_rate,
            slip_bps=slip_bps,
            size_pow=1.0,
            max_mult=1.5,
            exec_mode=exec_mode,
            portfolio_slots=int(risk["portfolio_slots"]),
            risk_per_trade=float(risk["risk_per_trade"]),
            leverage_mult=leverage_mult,
            notional_cap=notional_cap,
            enable_vol_targeting=enable_vol_targeting,
            vol_ratio_floor=vol_ratio_floor,
            vol_ratio_cap=vol_ratio_cap,
            vol_ratio_power=vol_ratio_power,
            dd_threshold_1=dd_threshold_1,
            dd_threshold_2=dd_threshold_2,
            dd_scale_1=dd_scale_1,
            dd_scale_2=dd_scale_2,
            initial_capital=initial_capital,
            record_equity_every_bar=record_equity_every_bar,
        )

        best_w = float(weights[0])
        best_w_score = None
        if eq_b_in is not None and not eq_b_in.empty and eq_s_in is not None and not eq_s_in.empty:
            for w in weights:
                eq_combo_in = combine_equity(eq_b_in, eq_s_in, float(w))
                m = calc_equity_metrics(eq_combo_in)
                if not m:
                    continue
                shr = float(m["Sharpe Ratio"])
                if best_w_score is None or shr > best_w_score:
                    best_w_score = shr
                    best_w = float(w)

        tr_b, eq_b = simulate_v2xa(
            df_dict,
            year=int(test_year),
            fund_params=cfg_v2xa_b,
            avoid_th=float(cfg_v2xa_b["avoid_th"]),
            exit_on_flip=bool(cfg_v2xa_b["exit_on_flip"]),
            taker_fee_rate=taker_fee_rate,
            maker_fee_rate=maker_fee_rate,
            slip_bps=slip_bps,
            sl_pct=float(risk["stop_loss_pct_trend"]),
            size_k=float(cfg_v2xa_b["size_k"]),
            min_mult=0.2,
            max_mult=1.2,
            exec_mode=exec_mode,
            portfolio_slots=int(risk["portfolio_slots"]),
            risk_per_trade=float(risk["risk_per_trade"]),
            leverage_mult=leverage_mult,
            notional_cap=notional_cap,
            enable_vol_targeting=enable_vol_targeting,
            vol_ratio_floor=vol_ratio_floor,
            vol_ratio_cap=vol_ratio_cap,
            vol_ratio_power=vol_ratio_power,
            dd_threshold_1=dd_threshold_1,
            dd_threshold_2=dd_threshold_2,
            dd_scale_1=dd_scale_1,
            dd_scale_2=dd_scale_2,
            initial_capital=initial_capital,
            record_equity_every_bar=record_equity_every_bar,
        )
        tr_s, eq_s = simulate_shockscore(
            df_dict,
            year=int(test_year),
            entry_th=float(shock_cfg["entry_th"]),
            max_hold=int(shock_cfg["max_hold"]),
            sl_pct=float(shock_cfg["sl_pct"]),
            taker_fee_rate=taker_fee_rate,
            maker_fee_rate=maker_fee_rate,
            slip_bps=slip_bps,
            size_pow=1.0,
            max_mult=1.5,
            exec_mode=exec_mode,
            portfolio_slots=int(risk["portfolio_slots"]),
            risk_per_trade=float(risk["risk_per_trade"]),
            leverage_mult=leverage_mult,
            notional_cap=notional_cap,
            enable_vol_targeting=enable_vol_targeting,
            vol_ratio_floor=vol_ratio_floor,
            vol_ratio_cap=vol_ratio_cap,
            vol_ratio_power=vol_ratio_power,
            dd_threshold_1=dd_threshold_1,
            dd_threshold_2=dd_threshold_2,
            dd_scale_1=dd_scale_1,
            dd_scale_2=dd_scale_2,
            initial_capital=initial_capital,
            record_equity_every_bar=record_equity_every_bar,
        )

        eq_combo_ab = combine_equity(eq_b, eq_s, best_w)
        eq_combo_ab, last_ab = link_equity(eq_combo_ab, last_ab, base_cap=float(initial_capital))
        eq_ab.append(eq_combo_ab)
        if tr_b is not None and not tr_b.empty:
            x = tr_b.copy()
            x["component"] = "trend"
            x["split"] = int(si)
            x["test_year"] = int(test_year)
            trades_ab.append(x)
        if tr_s is not None and not tr_s.empty:
            x = tr_s.copy()
            x["component"] = "shock"
            x["split"] = int(si)
            x["test_year"] = int(test_year)
            trades_ab.append(x)

        tr_b_t, eq_b_t = simulate_v2xa(
            df_dict,
            year=int(test_year),
            fund_params=cfg_v2xa_b,
            avoid_th=float(cfg_v2xa_b["avoid_th"]),
            exit_on_flip=bool(cfg_v2xa_b["exit_on_flip"]),
            taker_fee_rate=taker_fee_rate,
            maker_fee_rate=maker_fee_rate,
            slip_bps=slip_bps,
            sl_pct=float(risk["stop_loss_pct_trend"]),
            size_k=float(cfg_v2xa_b["size_k"]),
            min_mult=0.2,
            max_mult=1.2,
            exec_mode="taker",
            portfolio_slots=int(risk["portfolio_slots"]),
            risk_per_trade=float(risk["risk_per_trade"]),
            leverage_mult=leverage_mult,
            notional_cap=notional_cap,
            enable_vol_targeting=enable_vol_targeting,
            vol_ratio_floor=vol_ratio_floor,
            vol_ratio_cap=vol_ratio_cap,
            vol_ratio_power=vol_ratio_power,
            dd_threshold_1=dd_threshold_1,
            dd_threshold_2=dd_threshold_2,
            dd_scale_1=dd_scale_1,
            dd_scale_2=dd_scale_2,
            initial_capital=initial_capital,
            record_equity_every_bar=record_equity_every_bar,
        )
        tr_s_t, eq_s_t = simulate_shockscore(
            df_dict,
            year=int(test_year),
            entry_th=float(shock_cfg["entry_th"]),
            max_hold=int(shock_cfg["max_hold"]),
            sl_pct=float(shock_cfg["sl_pct"]),
            taker_fee_rate=taker_fee_rate,
            maker_fee_rate=maker_fee_rate,
            slip_bps=slip_bps,
            size_pow=1.0,
            max_mult=1.5,
            exec_mode="taker",
            portfolio_slots=int(risk["portfolio_slots"]),
            risk_per_trade=float(risk["risk_per_trade"]),
            leverage_mult=leverage_mult,
            notional_cap=notional_cap,
            enable_vol_targeting=enable_vol_targeting,
            vol_ratio_floor=vol_ratio_floor,
            vol_ratio_cap=vol_ratio_cap,
            vol_ratio_power=vol_ratio_power,
            dd_threshold_1=dd_threshold_1,
            dd_threshold_2=dd_threshold_2,
            dd_scale_1=dd_scale_1,
            dd_scale_2=dd_scale_2,
            initial_capital=initial_capital,
            record_equity_every_bar=record_equity_every_bar,
        )
        eq_combo_ab_t = combine_equity(eq_b_t, eq_s_t, best_w)
        eq_combo_ab_t, last_ab_t = link_equity(eq_combo_ab_t, last_ab_t, base_cap=float(initial_capital))
        eq_ab_taker.append(eq_combo_ab_t)
        if tr_b_t is not None and not tr_b_t.empty:
            x = tr_b_t.copy()
            x["component"] = "trend"
            x["split"] = int(si)
            x["test_year"] = int(test_year)
            trades_ab_taker.append(x)
        if tr_s_t is not None and not tr_s_t.empty:
            x = tr_s_t.copy()
            x["component"] = "shock"
            x["split"] = int(si)
            x["test_year"] = int(test_year)
            trades_ab_taker.append(x)

        m_ab = calc_equity_metrics(eq_combo_ab)
        m_ab_t = calc_equity_metrics(eq_combo_ab_t)
        split_rows.append(
            {
                "split": int(si),
                "train": "-".join([str(x) for x in train_years]),
                "test": int(test_year),
                "best_w": float(best_w),
                "AB_sharpe": float(m_ab.get("Sharpe Ratio", np.nan)) if m_ab else np.nan,
                "AB_taker_sharpe": float(m_ab_t.get("Sharpe Ratio", np.nan)) if m_ab_t else np.nan,
            }
        )

    eq_ab_all = pd.concat(eq_ab) if eq_ab else pd.DataFrame()
    eq_ab_t_all = pd.concat(eq_ab_taker) if eq_ab_taker else pd.DataFrame()
    tr_ab_all = pd.concat(trades_ab) if trades_ab else pd.DataFrame()
    tr_ab_t_all = pd.concat(trades_ab_taker) if trades_ab_taker else pd.DataFrame()

    return {
        "splits": pd.DataFrame(split_rows),
        "oos_AB": calc_equity_metrics(eq_ab_all),
        "oos_AB_taker": calc_equity_metrics(eq_ab_t_all),
        "year_AB": year_table(eq_ab_all),
        "year_AB_taker": year_table(eq_ab_t_all),
        "equity_AB": eq_ab_all,
        "equity_AB_taker": eq_ab_t_all,
        "trades_AB": tr_ab_all,
        "trades_AB_taker": tr_ab_t_all,
    }
