"""
Compute the per-minute, per-strike GEX heatmap matrix and persist it to
DuckDB so the API endpoint /api/v1/gex/heatmap/{parent} can serve it
in <500ms (Blueprint v1.2 §L1.5).

Inputs (already produced by the existing pipeline):
  - cbbo_1m_raw       (1-minute mid prices per option)
  - instrument_def    (strike / expiry / parent_symbol per instrument)
  - option_chain_eod  (EOD open interest, stat_type=9)
  - spot_price        (1-minute interpolated SPX spot)

Output:
  - exposure_per_strike_minute(parent_symbol, ts, strike, gex_dollar)

Run:
  python gex_heatmap_compute.py            # all SPX trading days
  python gex_heatmap_compute.py 2026-04-08 # one specific date
"""
from __future__ import annotations

import sys
from typing import Optional

import duckdb
import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm

DB_PATH = r"C:\Users\ollama\Documents\DFT\dft-lite\dft.duckdb"

# Standard BSM constants used elsewhere in the project.
RISK_FREE = 0.045
DIVIDEND_Y = 0.015
MULTIPLIER = 100


# ── BSM helpers (kept inline to avoid cross-module deps) ──────────────────
def _bsm_price(S: float, K: float, T: float, r: float, q: float, sigma: float, ot: str) -> float:
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if ot == "C":
        return S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)


def _solve_iv(S: float, K: float, T: float, r: float, q: float, mp: float, ot: str) -> float:
    if T <= 0 or mp <= 0:
        return float("nan")
    intrinsic = max(0.0, S - K) if ot == "C" else max(0.0, K - S)
    if mp <= intrinsic * 1.0001:
        return float("nan")
    try:
        return brentq(
            lambda s: _bsm_price(S, K, T, r, q, s, ot) - mp,
            1e-4,
            5.0,
            xtol=1e-6,
            maxiter=100,
        )
    except (ValueError, RuntimeError):
        return float("nan")


def _gamma(S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return float(np.exp(-q * T) * norm.pdf(d1) / (S * sigma * np.sqrt(T)))


# ── Per-minute per-strike GEX computation ────────────────────────────────
def compute_heatmap_for_date(con: duckdb.DuckDBPyConnection, date_str: str) -> pd.DataFrame:
    """
    Returns a long-format DataFrame:
        [parent_symbol, ts, strike, gex_dollar]
    one row per (minute × strike) for SPX *and* SPXW.
    """
    df_oi = con.execute(
        """
        SELECT instrument_id, quantity AS open_interest
        FROM option_chain_eod
        WHERE date = ?
          AND stat_type = 9
          AND quantity > 0
        """,
        [date_str],
    ).df()
    if len(df_oi) == 0:
        return pd.DataFrame(columns=["parent_symbol", "ts", "strike", "gex_dollar"])

    df_min = con.execute(
        """
        SELECT
            date_trunc('minute', c.ts_event) AS ts,
            c.instrument_id,
            c.mid_px,
            d.strike_price          AS K,
            d.option_type,
            d.expiration,
            d.parent_symbol,
            s.spot                  AS S
        FROM cbbo_1m_raw c
        JOIN instrument_def d USING (instrument_id)
        JOIN spot_price    s
          ON date_trunc('minute', c.ts_event) = date_trunc('minute', s.ts)
        WHERE c.ts_event::DATE = ?
          AND c.mid_px > 0.1
        """,
        [date_str],
    ).df()
    if len(df_min) == 0:
        return pd.DataFrame(columns=["parent_symbol", "ts", "strike", "gex_dollar"])

    df = df_min.merge(df_oi, on="instrument_id", how="inner")
    if len(df) == 0:
        return pd.DataFrame(columns=["parent_symbol", "ts", "strike", "gex_dollar"])

    # Vectorised T calculation.
    exp = pd.to_datetime(df["expiration"], utc=True)
    ts = pd.to_datetime(df["ts"], utc=True)
    df["T"] = ((exp - ts).dt.total_seconds() / (365.25 * 86400)).clip(lower=1 / (365 * 24 * 60))

    rows = []
    for tup in df.itertuples(index=False):
        iv = _solve_iv(
            tup.S,
            tup.K,
            tup.T,
            RISK_FREE,
            DIVIDEND_Y,
            float(tup.mid_px),
            tup.option_type,
        )
        if not np.isfinite(iv) or iv < 0.01 or iv > 3.0:
            continue
        g = _gamma(tup.S, tup.K, tup.T, RISK_FREE, DIVIDEND_Y, iv)
        sign = 1.0 if tup.option_type == "C" else -1.0
        gex = sign * g * float(tup.open_interest) * MULTIPLIER * (tup.S ** 2)
        rows.append(
            {
                "parent_symbol": tup.parent_symbol,
                "ts": tup.ts,
                "strike": float(tup.K),
                "gex_contrib": gex,
            }
        )

    if not rows:
        return pd.DataFrame(columns=["parent_symbol", "ts", "strike", "gex_dollar"])

    df_long = pd.DataFrame(rows)
    out = (
        df_long.groupby(["parent_symbol", "ts", "strike"], as_index=False)["gex_contrib"]
        .sum()
        .rename(columns={"gex_contrib": "gex_dollar"})
        .sort_values(["parent_symbol", "ts", "strike"])
    )
    return out


def _ensure_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS exposure_per_strike_minute (
            parent_symbol VARCHAR,
            ts            TIMESTAMP,
            strike        DOUBLE,
            gex_dollar    DOUBLE
        )
        """
    )


def run(date: Optional[str] = None) -> None:
    con = duckdb.connect(DB_PATH)
    _ensure_table(con)

    if date:
        dates = [date]
    else:
        df_dates = con.execute(
            """
            SELECT DISTINCT ts_event::DATE AS d
            FROM cbbo_1m_raw
            ORDER BY d
            """
        ).df()
        dates = [str(d) for d in df_dates["d"].tolist() if pd.notna(d)]

    print(f"Computing heatmap for {len(dates)} day(s)...")

    for ds in dates:
        print(f"  • {ds}", end=" ", flush=True)
        df = compute_heatmap_for_date(con, ds)
        if len(df) == 0:
            print("(no data)")
            continue
        # Replace existing rows for that day to make this idempotent.
        con.execute("DELETE FROM exposure_per_strike_minute WHERE ts::DATE = ?", [ds])
        con.register("df_heatmap", df)
        con.execute(
            """
            INSERT INTO exposure_per_strike_minute
            SELECT parent_symbol, ts, strike, gex_dollar FROM df_heatmap
            """
        )
        con.unregister("df_heatmap")
        print(f"({len(df):,} rows)")

    n = con.execute("SELECT COUNT(*) FROM exposure_per_strike_minute").fetchone()[0]
    print(f"\nDone. exposure_per_strike_minute: {n:,} total rows.")
    con.close()


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(arg)
