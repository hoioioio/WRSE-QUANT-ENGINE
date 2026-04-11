import argparse
import os
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class LiveCfg:
    category: str
    symbols: list[str]
    tf_signal: str
    tf_entry: str
    ohlcv_limit: int
    initial_capital: float
    daily_dd_pct: float
    max_loss_pct: float
    max_risk_per_position_pct: float
    internal_daily_stop_pct: float
    risk_per_trade_pct: float
    notional_cap: float
    leverage: int
    stop_loss_pct_trend: float
    loop_sleep_sec: int
    bar_close_buffer_sec: int


def _load_toml(path: str) -> dict:
    import tomllib

    p = Path(path)
    return tomllib.loads(p.read_text(encoding="utf-8"))


def _load_cfg(path: str) -> LiveCfg:
    raw = _load_toml(path)
    bybit = raw.get("bybit", {})
    uni = raw.get("universe", {})
    risk = raw.get("risk", {})
    engine = raw.get("engine", {})
    return LiveCfg(
        category=str(bybit.get("category", "linear")),
        symbols=list(uni.get("symbols", [])),
        tf_signal=str(uni.get("signal_timeframe", "4h")),
        tf_entry=str(uni.get("entry_timeframe", "15m")),
        ohlcv_limit=int(uni.get("ohlcv_limit", 1500)),
        initial_capital=float(risk.get("initial_capital", 25000.0)),
        daily_dd_pct=float(risk.get("daily_dd_pct", 0.05)),
        max_loss_pct=float(risk.get("max_loss_pct", 0.10)),
        max_risk_per_position_pct=float(risk.get("max_risk_per_position_pct", 0.03)),
        internal_daily_stop_pct=float(risk.get("internal_daily_stop_pct", 0.025)),
        risk_per_trade_pct=float(risk.get("risk_per_trade_pct", 0.0075)),
        notional_cap=float(risk.get("notional_cap", 3000.0)),
        leverage=int(risk.get("leverage", 1)),
        stop_loss_pct_trend=float(risk.get("stop_loss_pct_trend", 0.02)),
        loop_sleep_sec=int(engine.get("loop_sleep_sec", 10)),
        bar_close_buffer_sec=int(engine.get("bar_close_buffer_sec", 30)),
    )


def _utc_ts() -> pd.Timestamp:
    return pd.Timestamp.utcnow().tz_localize("UTC")


def _state_dir() -> Path:
    p = Path(__file__).resolve().parent / "_state"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _state_path(name: str) -> Path:
    return _state_dir() / name


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: object) -> None:
    import json

    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def _ohlcv_to_df(rows: list[list[float]]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["ts"].astype("int64"), unit="ms", utc=True).dt.tz_convert(None)
    df = df.drop(columns=["ts"]).set_index("time").sort_index()
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype("float64")
    return df


def _calc_awma(series: pd.Series, length: int, fast_end: int = 2, slow_end: int = 30) -> pd.Series:
    change = series.diff(length).abs()
    volatility = series.diff().abs().rolling(window=length).sum()
    er = (change / volatility).fillna(0)
    fast_sc = 2 / (fast_end + 1)
    slow_sc = 2 / (slow_end + 1)
    sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
    ama = np.full(len(series), np.nan, dtype=float)
    if length < len(series):
        ama[length - 1] = float(np.mean(series.iloc[:length]))
        for i in range(length, len(series)):
            c = float(sc.iloc[i]) if np.isfinite(float(sc.iloc[i])) else 0.0
            ama[i] = ama[i - 1] + c * (float(series.iloc[i]) - ama[i - 1])
    return pd.Series(ama, index=series.index)


def _calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _calc_adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / length, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / length, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / length, adjust=False).mean() / atr)
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).replace([np.inf, -np.inf], np.nan)
    return dx.ewm(alpha=1 / length, adjust=False).mean()


def _build_4h(df_15m: pd.DataFrame) -> pd.DataFrame:
    df = (
        df_15m.resample("4h")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
        .sort_index()
    )
    df["fast_awma"] = _calc_awma(df["close"], 1)
    df["slow_awma"] = _calc_awma(df["close"], 16)
    df["exit_line"] = df["close"].rolling(140).mean()
    df["rev_ma"] = df["close"].rolling(3).mean()
    df["rsi"] = _calc_rsi(df["close"], 14)
    df["adx"] = _calc_adx(df["high"], df["low"], df["close"], 14)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - df["close"].shift(1)).abs()
    tr3 = (df["low"] - df["close"].shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()
    df["atr_sma"] = df["atr"].rolling(20).mean()
    df["vol_ratio"] = np.where(df["atr_sma"] != 0, df["atr"] / df["atr_sma"], 0.0)
    return df.dropna()


def _signal_from_4h(df4: pd.DataFrame) -> str | None:
    if df4 is None or len(df4) < 145:
        return None
    prev = df4.iloc[-2]
    last = df4.iloc[-1]
    prev2 = df4.iloc[-3]
    is_golden = (prev2["fast_awma"] < prev2["slow_awma"]) and (prev["fast_awma"] > prev["slow_awma"])
    is_dead = (prev2["fast_awma"] > prev2["slow_awma"]) and (prev["fast_awma"] < prev["slow_awma"])
    if not np.isfinite(float(prev["exit_line"])):
        return None
    if is_golden and float(prev["close"]) > float(prev["exit_line"]):
        return "buy"
    if is_dead and float(prev["close"]) < float(prev["exit_line"]):
        return "sell"
    return None


def _resolve_symbol(ex, sym: str) -> str:
    if sym in ex.markets:
        return sym
    if sym.replace(":USDT", "") in ex.markets:
        return sym.replace(":USDT", "")
    s2 = sym.replace("/", "")
    for k in ex.markets:
        if ex.market(k).get("id") == s2:
            return k
    raise KeyError(sym)


def _market_id(ex, sym: str) -> str:
    m = ex.market(sym)
    return str(m.get("id") or m.get("symbol") or sym).replace("/", "")


def _max_risk_cap(cfg: LiveCfg) -> float:
    return float(cfg.initial_capital) * float(cfg.max_risk_per_position_pct)


def _compute_order(
    *,
    cfg: LiveCfg,
    side: str,
    price: float,
) -> tuple[float, float]:
    risk_usd = float(cfg.initial_capital) * float(cfg.risk_per_trade_pct)
    sl_pct = float(cfg.stop_loss_pct_trend)
    notional = float(min(float(cfg.notional_cap), float(risk_usd) / float(sl_pct)))
    qty = float(notional) / float(price)
    sl = float(price) * (1.0 - sl_pct) if side == "buy" else float(price) * (1.0 + sl_pct)
    risk_to_sl = abs(float(price) - float(sl)) * float(qty)
    if risk_to_sl > _max_risk_cap(cfg):
        scale = float(_max_risk_cap(cfg)) / float(risk_to_sl)
        qty = float(qty) * float(scale)
        risk_to_sl = abs(float(price) - float(sl)) * float(qty)
    return float(qty), float(sl)


def _set_sl_bybit_v5(ex, *, cfg: LiveCfg, sym: str, sl_px: float) -> None:
    ex.privatePostV5PositionTradingStop(
        {
            "category": str(cfg.category),
            "symbol": _market_id(ex, sym),
            "stopLoss": str(float(sl_px)),
        }
    )


def _close_reduce_only(ex, *, sym: str, side: str, qty: float) -> None:
    close_side = "sell" if side == "buy" else "buy"
    ex.create_market_order(sym, close_side, float(qty), params={"reduceOnly": True})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, type=str)
    args = ap.parse_args()

    cfg = _load_cfg(args.config)

    live_mode = str(os.getenv("LIVE_MODE", "")).strip() == "1"
    api_key = str(os.getenv("BYBIT_API_KEY", "")).strip()
    api_secret = str(os.getenv("BYBIT_API_SECRET", "")).strip()

    import ccxt

    ex = ccxt.bybit(
        {
            "enableRateLimit": True,
            "apiKey": api_key,
            "secret": api_secret,
            "options": {"defaultType": "swap"},
        }
    )
    ex.load_markets()

    sym_list = [_resolve_symbol(ex, s) for s in cfg.symbols]

    st_path = _state_path("positions.json")
    positions = _read_json(st_path)

    if live_mode and (not api_key or not api_secret):
        raise SystemExit("LIVE_MODE=1 but BYBIT_API_KEY/BYBIT_API_SECRET is missing")

    while True:
        now = _utc_ts()
        day_key = now.floor("D").strftime("%Y-%m-%d")
        daily_path = _state_path("daily.json")
        daily = _read_json(daily_path)
        if daily.get("day") != day_key:
            daily = {"day": day_key, "start_equity": float(cfg.initial_capital), "min_equity": float(cfg.initial_capital), "disabled": False}
        if bool(daily.get("disabled", False)):
            _write_json(daily_path, daily)
            time.sleep(int(cfg.loop_sleep_sec))
            continue

        for sym in sym_list:
            rows = ex.fetch_ohlcv(sym, timeframe=str(cfg.tf_entry), limit=int(cfg.ohlcv_limit))
            df15 = _ohlcv_to_df(rows)
            df4 = _build_4h(df15)
            sig = _signal_from_4h(df4)

            px = float(df15["close"].iloc[-1])
            pos = positions.get(sym)
            if pos is None and sig in ("buy", "sell"):
                qty, sl = _compute_order(cfg=cfg, side=str(sig), price=float(px))
                if not np.isfinite(qty) or qty <= 0:
                    continue

                if not live_mode:
                    positions[sym] = {"side": str(sig), "qty": float(qty), "entry_px": float(px), "sl_px": float(sl), "ts": str(now)}
                    continue

                ex.set_leverage(int(cfg.leverage), sym)
                ex.set_position_mode(hedged=False, symbol=sym)
                order = ex.create_market_order(sym, str(sig), float(qty))
                filled = float(order.get("filled") or qty)
                avg = float(order.get("average") or px)
                sl = float(avg) * (1.0 - float(cfg.stop_loss_pct_trend)) if str(sig) == "buy" else float(avg) * (1.0 + float(cfg.stop_loss_pct_trend))
                try:
                    _set_sl_bybit_v5(ex, cfg=cfg, sym=sym, sl_px=float(sl))
                except Exception:
                    _close_reduce_only(ex, sym=sym, side=str(sig), qty=float(filled))
                    continue
                positions[sym] = {"side": str(sig), "qty": float(filled), "entry_px": float(avg), "sl_px": float(sl), "ts": str(now)}

            if pos is not None:
                sl_px = float(pos.get("sl_px", np.nan))
                if np.isfinite(sl_px):
                    if (pos.get("side") == "buy" and px <= sl_px) or (pos.get("side") == "sell" and px >= sl_px):
                        if live_mode:
                            _close_reduce_only(ex, sym=sym, side=str(pos.get("side")), qty=float(pos.get("qty", 0.0)))
                        positions.pop(sym, None)

        _write_json(st_path, positions)
        _write_json(daily_path, daily)
        time.sleep(int(cfg.loop_sleep_sec))


if __name__ == "__main__":
    raise SystemExit(main())

