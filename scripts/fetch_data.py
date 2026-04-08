from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


def _parse_ymd(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _sym_to_binance(symbol: str) -> str:
    return symbol.replace("_", "")


def _http_get_json(url: str, *, timeout: int = 30) -> Any:
    req = Request(url, headers={"User-Agent": "wrse-fetch/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def _iter_fapi_klines(
    *,
    symbol: str,
    interval: str,
    start_ms: int,
    end_ms: int,
    limit: int = 1500,
    sleep_sec: float = 0.2,
) -> list[list[Any]]:
    out: list[list[Any]] = []
    cur = int(start_ms)
    while cur < int(end_ms):
        qs = urlencode(
            {
                "symbol": symbol,
                "interval": interval,
                "startTime": cur,
                "endTime": end_ms,
                "limit": limit,
            }
        )
        url = f"https://fapi.binance.com/fapi/v1/klines?{qs}"
        rows = _http_get_json(url)
        if not isinstance(rows, list) or len(rows) == 0:
            break
        out.extend(rows)
        last_open = int(rows[-1][0])
        nxt = last_open + 1
        if nxt <= cur:
            break
        cur = nxt
        time.sleep(float(sleep_sec))
    return out


def _iter_fapi_funding(
    *,
    symbol: str,
    start_ms: int,
    end_ms: int,
    limit: int = 1000,
    sleep_sec: float = 0.2,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    cur = int(start_ms)
    while cur < int(end_ms):
        qs = urlencode(
            {
                "symbol": symbol,
                "startTime": cur,
                "endTime": end_ms,
                "limit": limit,
            }
        )
        url = f"https://fapi.binance.com/fapi/v1/fundingRate?{qs}"
        rows = _http_get_json(url)
        if not isinstance(rows, list) or len(rows) == 0:
            break
        out.extend(rows)
        last_t = int(rows[-1]["fundingTime"])
        nxt = last_t + 1
        if nxt <= cur:
            break
        cur = nxt
        time.sleep(float(sleep_sec))
    return out


def _klines_to_df(rows: list[list[Any]]) -> pd.DataFrame:
    cols = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_asset_volume",
        "number_of_trades",
        "taker_buy_base",
        "taker_buy_quote",
        "ignore",
    ]
    df = pd.DataFrame(rows, columns=cols)
    df["time"] = pd.to_datetime(df["open_time"].astype("int64"), unit="ms", utc=True).dt.tz_convert(None)
    df = df.set_index("time", drop=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype("float64")
    return df[["open", "high", "low", "close", "volume"]].sort_index()


def _funding_to_df(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if len(rows) == 0:
        return pd.DataFrame(columns=["fundingTime", "fundingRate"])
    df = pd.DataFrame(rows)
    df["fundingTime"] = pd.to_datetime(df["fundingTime"].astype("int64"), unit="ms", utc=True).dt.tz_convert(None)
    df["fundingRate"] = df["fundingRate"].astype("float64")
    return df[["fundingTime", "fundingRate"]].sort_values("fundingTime").reset_index(drop=True)


@dataclass(frozen=True)
class FetchSpec:
    backtest_cache_dir: str
    regime_cache_dir: str
    timeframe: str
    symbols: list[str]


def _load_config(path: str) -> FetchSpec:
    import tomllib

    p = Path(path)
    raw = tomllib.loads(p.read_text(encoding="utf-8"))
    data = raw.get("data", {})
    return FetchSpec(
        backtest_cache_dir=str(data.get("backtest_cache_dir", r"c:\backtest_cache")),
        regime_cache_dir=str(data.get("regime_cache_dir", r"c:\alpha_cache")),
        timeframe=str(data.get("timeframe", "15m")),
        symbols=list(data.get("symbols", [])),
    )


def main() -> int:
    ap = argparse.ArgumentParser(prog="wrse-fetch-data")
    ap.add_argument("--config", type=str, required=True)
    ap.add_argument("--start", type=str, required=True, help="YYYY-MM-DD (UTC)")
    ap.add_argument("--end", type=str, required=True, help="YYYY-MM-DD (UTC, inclusive)")
    ap.add_argument("--symbols", type=str, default="", help="Comma-separated override, e.g. BTC_USDT,ETH_USDT")
    ap.add_argument("--timeframe", type=str, default="", help="Override, e.g. 15m")
    ap.add_argument("--backtest_cache_dir", type=str, default="", help="Override backtest cache dir")
    ap.add_argument("--regime_cache_dir", type=str, default="", help="Override regime cache dir")
    ap.add_argument("--no_funding", action="store_true", help="Skip funding download")
    ap.add_argument("--sleep_sec", type=float, default=0.2)
    args = ap.parse_args()

    spec = _load_config(args.config)
    symbols = spec.symbols
    if args.symbols:
        symbols = [s.strip() for s in str(args.symbols).split(",") if s.strip()]
    timeframe = str(args.timeframe).strip() or spec.timeframe
    bt_dir = str(args.backtest_cache_dir).strip() or spec.backtest_cache_dir
    rg_dir = str(args.regime_cache_dir).strip() or spec.regime_cache_dir

    start_dt = _parse_ymd(args.start)
    end_dt = _parse_ymd(args.end)
    end_ms = _to_ms(end_dt) + 24 * 60 * 60 * 1000 - 1

    Path(bt_dir).mkdir(parents=True, exist_ok=True)
    Path(rg_dir).mkdir(parents=True, exist_ok=True)

    for sym in symbols:
        b_sym = _sym_to_binance(sym)
        print("FETCH_OHLCV", sym, "->", b_sym, "tf", timeframe)
        rows = _iter_fapi_klines(
            symbol=b_sym,
            interval=timeframe,
            start_ms=_to_ms(start_dt),
            end_ms=end_ms,
            sleep_sec=float(args.sleep_sec),
        )
        df = _klines_to_df(rows)
        out_p = Path(bt_dir) / f"bt_{sym}_{timeframe}.pkl"
        df.to_pickle(out_p)
        print("WROTE", str(out_p), "rows", int(len(df)))

        if not bool(args.no_funding):
            print("FETCH_FUNDING", sym, "->", b_sym)
            frows = _iter_fapi_funding(
                symbol=b_sym,
                start_ms=_to_ms(start_dt),
                end_ms=end_ms,
                sleep_sec=float(args.sleep_sec),
            )
            fdf = _funding_to_df(frows)
            f_p = Path(rg_dir) / f"funding_{sym}.pkl"
            fdf.to_pickle(f_p)
            print("WROTE", str(f_p), "rows", int(len(fdf)))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

