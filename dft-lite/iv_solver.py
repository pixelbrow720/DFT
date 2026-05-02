import duckdb
import numpy as np
import pandas as pd
from scipy.stats import norm
from scipy.optimize import brentq

DB_PATH     = r"C:\Users\ollama\Documents\DFT\dft-lite\dft.duckdb"
PARQUET_DIR = r"C:\Users\ollama\Documents\DFT\parquet"

# ── BSM ────────────────────────────────────────────────────
def bsm_price(S, K, T, r, q, sigma, opt_type):
    if T <= 0 or sigma <= 0:
        return 0.0
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    if opt_type == 'C':
        return S*np.exp(-q*T)*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2)
    else:
        return K*np.exp(-r*T)*norm.cdf(-d2) - S*np.exp(-q*T)*norm.cdf(-d1)

def solve_iv(S, K, T, r, q, market_price, opt_type):
    if T <= 0 or market_price <= 0:
        return np.nan
    # Brent method — robust, tidak perlu initial guess
    try:
        intrinsic = max(0, S - K) if opt_type == 'C' else max(0, K - S)
        if market_price <= intrinsic * 1.0001:
            return np.nan
        iv = brentq(
            lambda sigma: bsm_price(S, K, T, r, q, sigma, opt_type) - market_price,
            1e-4, 5.0, xtol=1e-6, maxiter=100
        )
        return iv
    except:
        return np.nan

# ── Test IV solver dulu ────────────────────────────────────
print("Test IV solver:")
S, K, T, r, q = 6800.0, 6800.0, 30/365, 0.045, 0.015
sigma_true = 0.18
price = bsm_price(S, K, T, r, q, sigma_true, 'C')
iv_solved = solve_iv(S, K, T, r, q, price, 'C')
print(f"  True sigma : {sigma_true:.4f}")
print(f"  BSM price  : {price:.4f}")
print(f"  Solved IV  : {iv_solved:.4f}")
print(f"  Error      : {abs(iv_solved - sigma_true):.2e}")

# ── Sample IV compute dari data nyata ──────────────────────
print("\nComputing IV dari data nyata (sample 1 hari)...")
con = duckdb.connect(DB_PATH)

# Ambil sample: SPXW 0DTE tanggal 2026-04-08, strikes dekat ATM
df = con.execute("""
    SELECT
        c.ts_event,
        c.mid_px,
        d.strike_price  AS K,
        d.option_type,
        d.expiration,
        d.parent_symbol,
        s.spot          AS S
    FROM cbbo_1m_raw c
    JOIN instrument_def d USING (instrument_id)
    JOIN spot_price s
      ON date_trunc('minute', c.ts_event) = date_trunc('minute', s.ts)
    WHERE c.ts_event::DATE = '2026-04-08'
      AND d.expiration::DATE = '2026-04-08'
      AND d.parent_symbol = 'SPXW'
      AND d.strike_price BETWEEN 6700 AND 6900
      AND c.mid_px > 0.5
    ORDER BY c.ts_event, d.strike_price
    LIMIT 200
""").df()
con.close()

print(f"Sample rows: {len(df)}")
print(df[['ts_event','K','option_type','mid_px','S']].head(10).to_string())

# Compute IV per row
r, q = 0.045, 0.015
ivs = []
for _, row in df.iterrows():
    S  = float(row['S'])
    K  = float(row['K'])
    # Fix: expiration sudah tz-aware, pakai tz_convert bukan tz_localize
    exp = pd.Timestamp(row['expiration'])
    if exp.tzinfo is None:
        exp = exp.tz_localize('UTC')
    else:
        exp = exp.tz_convert('UTC')
    ts  = pd.Timestamp(row['ts_event']).tz_convert('UTC')
    T   = (exp - ts).total_seconds() / (365.25 * 86400)
    iv  = solve_iv(S, K, T, r, q, float(row['mid_px']), row['option_type'])
    ivs.append(iv)

df['iv'] = ivs
df_valid = df[df['iv'].notna() & (df['iv'] > 0.01) & (df['iv'] < 3.0)]
print(f"\nValid IV: {len(df_valid)}/{len(df)}")
print(df_valid[['ts_event','K','option_type','mid_px','S','iv']].head(20).to_string())