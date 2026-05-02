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
from scipy.stats import norm

DB_PATH = r"C:\Users\ollama\Documents\DFT\dft-lite\dft.duckdb"

# Standard BSM constants used elsewhere in the project.
RISK_FREE = 0.045
DIVIDEND_Y = 0.015
MULTIPLIER = 100

# Vectorised Newton-Raphson IV solver tuning.
IV_INIT_GUESS = 0.30
IV_MAX_ITER = 25
IV_TOL = 1e-5
IV_MIN = 1e-3
IV_MAX = 5.0


# ── BSM helpers (vectorised over numpy arrays) ────────────────────────────
def _bsm_price_vec(
    S: np.ndarray,
    K: np.ndarray,
    T: np.ndarray,
    r: float,
    q: float,
    sigma: np.ndarray,
    is_call: np.ndarray,
) -> np.ndarray:
    sqrt_T = np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T
    disc_q = np.exp(-q * T)
    disc_r = np.exp(-r * T)
    call = S * disc_q * norm.cdf(d1) - K * disc_r * norm.cdf(d2)
    put = K * disc_r * norm.cdf(-d2) - S * disc_q * norm.cdf(-d1)
    return np.where(is_call, call, put)


def _bsm_vega_vec(
    S: np.ndarray,
    K: np.ndarray,
    T: np.ndarray,
    r: float,
    q: float,
    sigma: np.ndarray,
) -> np.ndarray:
    sqrt_T = np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    return S * np.exp(-q * T) * norm.pdf(d1) * sqrt_T


def _solve_iv_vec(
    S: np.ndarray,
    K: np.ndarray,
    T: np.ndarray,
    r: float,
    q: float,
    mp: np.ndarray,
    is_call: np.ndarray,
) -> np.ndarray:
    """Vectorised Newton-Raphson root-finder for implied volatility.

    Returns NaN for rows that fail to converge or stay outside
    [IV_MIN, IV_MAX]. Roughly 20-50x faster than scipy.optimize.brentq
    called row-by-row from a Python loop.
    """
    n = mp.shape[0]
    sigma = np.full(n, IV_INIT_GUESS, dtype=float)
    active = np.ones(n, dtype=bool)

    for _ in range(IV_MAX_ITER):
        if not active.any():
            break
        s_act = sigma[active]
        price = _bsm_price_vec(
            S[active], K[active], T[active], r, q, s_act, is_call[active]
        )
        diff = price - mp[active]
        vega = _bsm_vega_vec(S[active], K[active], T[active], r, q, s_act)
        # Avoid divide-by-zero / micro-vega blowups.
        safe = vega > 1e-8
        step = np.zeros_like(diff)
        step[safe] = diff[safe] / vega[safe]
        new_sigma = np.clip(s_act - step, IV_MIN, IV_MAX)
        # Mark rows that have converged (or have unusable vega) inactive.
        converged = (np.abs(step) < IV_TOL) | (~safe)
        sigma[active] = new_sigma
        # Update the active mask in-place: keep only still-non-converged rows.
        idx = np.flatnonzero(active)
        active[idx[converged]] = False

    # Drop rows that didn't converge cleanly (still pinned at the boundary).
    pinned = (sigma <= IV_MIN * 1.01) | (sigma >= IV_MAX * 0.99)
    sigma = np.where(pinned, np.nan, sigma)
    return sigma


def _gamma_vec(
    S: np.ndarray,
    K: np.ndarray,
    T: np.ndarray,
    r: float,
    q: float,
    sigma: np.ndarray,
) -> np.ndarray:
    sqrt_T = np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    return np.exp(-q * T) * norm.pdf(d1) / (S * sigma * sqrt_T)


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

    S = df["S"].to_numpy(dtype=float)
    K = df["K"].to_numpy(dtype=float)
    T = df["T"].to_numpy(dtype=float)
    mp = df["mid_px"].to_numpy(dtype=float)
    is_call = (df["option_type"].astype(str).str.upper() == "C").to_numpy()

    # Pre-filter: drop rows where mid price is at/below intrinsic value
    # (no positive time premium → no usable IV).
    intrinsic = np.where(is_call, np.maximum(0.0, S - K), np.maximum(0.0, K - S))
    valid = (mp > intrinsic * 1.0001) & (T > 0)
    if not valid.any():
        return pd.DataFrame(columns=["parent_symbol", "ts", "strike", "gex_dollar"])

    iv = np.full(S.shape, np.nan, dtype=float)
    iv[valid] = _solve_iv_vec(
        S[valid], K[valid], T[valid], RISK_FREE, DIVIDEND_Y, mp[valid], is_call[valid]
    )

    # Reasonableness filter on solved IV.
    ok = np.isfinite(iv) & (iv >= 0.01) & (iv <= 3.0)
    if not ok.any():
        return pd.DataFrame(columns=["parent_symbol", "ts", "strike", "gex_dollar"])

    gamma = np.zeros_like(S)
    gamma[ok] = _gamma_vec(S[ok], K[ok], T[ok], RISK_FREE, DIVIDEND_Y, iv[ok])

    sign = np.where(is_call, 1.0, -1.0)
    gex = sign * gamma * df["open_interest"].to_numpy(dtype=float) * MULTIPLIER * (S**2)

    # Build long-format DataFrame from valid rows only.
    df_long = pd.DataFrame(
        {
            "parent_symbol": df["parent_symbol"].to_numpy()[ok],
            "ts": df["ts"].to_numpy()[ok],
            "strike": K[ok],
            "gex_contrib": gex[ok],
        }
    )
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
        # Format as YYYY-MM-DD strings (drop the implicit 00:00:00 time).
        dates = [
            pd.Timestamp(d).strftime("%Y-%m-%d")
            for d in df_dates["d"].tolist()
            if pd.notna(d)
        ]

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
