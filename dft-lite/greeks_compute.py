import duckdb
import numpy as np
import pandas as pd
from scipy.stats import norm
from scipy.optimize import brentq

DB_PATH     = r"C:\Users\ollama\Documents\DFT\dft-lite\dft.duckdb"
PARQUET_DIR = r"C:\Users\ollama\Documents\DFT\parquet"

# ── BSM functions ──────────────────────────────────────────
def bsm_price(S, K, T, r, q, sigma, opt_type):
    if T <= 0 or sigma <= 0: return 0.0
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    if opt_type == 'C':
        return S*np.exp(-q*T)*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2)
    else:
        return K*np.exp(-r*T)*norm.cdf(-d2) - S*np.exp(-q*T)*norm.cdf(-d1)

def solve_iv(S, K, T, r, q, market_price, opt_type):
    if T <= 0 or market_price <= 0: return np.nan
    try:
        intrinsic = max(0, S-K) if opt_type == 'C' else max(0, K-S)
        if market_price <= intrinsic * 1.0001: return np.nan
        return brentq(
            lambda s: bsm_price(S, K, T, r, q, s, opt_type) - market_price,
            1e-4, 5.0, xtol=1e-6, maxiter=100
        )
    except:
        return np.nan

def compute_greeks(S, K, T, r, q, sigma, opt_type):
    if T <= 0 or sigma <= 0:
        return dict(delta=np.nan, gamma=np.nan, vega=np.nan,
                    theta=np.nan, vanna=np.nan, charm=np.nan)
    d1   = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2   = d1 - sigma*np.sqrt(T)
    pdf  = norm.pdf(d1)
    sqT  = np.sqrt(T)
    expq = np.exp(-q*T)
    expr = np.exp(-r*T)

    gamma = expq * pdf / (S * sigma * sqT)
    vega  = S * expq * pdf * sqT / 100          # per 1% IV

    if opt_type == 'C':
        delta = expq * norm.cdf(d1)
        theta = (-S*pdf*sigma*expq/(2*sqT)
                 - r*K*expr*norm.cdf(d2)
                 + q*S*expq*norm.cdf(d1)) / 365
    else:
        delta = -expq * norm.cdf(-d1)
        theta = (-S*pdf*sigma*expq/(2*sqT)
                 + r*K*expr*norm.cdf(-d2)
                 - q*S*expq*norm.cdf(-d1)) / 365

    vanna = -expq * pdf * d2 / sigma / 100
    charm = (-expq * pdf * (
        2*(r-q)*T - d2*sigma*sqT) / (2*T*sigma*sqT)) / 365

    return dict(delta=delta, gamma=gamma, vega=vega,
                theta=theta, vanna=vanna, charm=charm)

# ── Load 1 hari data ───────────────────────────────────────
print("Loading sample data (2026-04-08, SPXW 0DTE)...")
con = duckdb.connect(DB_PATH)

df = con.execute("""
    SELECT
        c.ts_event,
        c.mid_px,
        d.strike_price      AS K,
        d.option_type,
        d.expiration,
        d.parent_symbol,
        d.instrument_id,
        s.spot              AS S
    FROM cbbo_1m_raw c
    JOIN instrument_def d USING (instrument_id)
    JOIN spot_price s
      ON date_trunc('minute', c.ts_event) = date_trunc('minute', s.ts)
    WHERE c.ts_event::DATE = '2026-04-08'
      AND d.expiration::DATE = '2026-04-08'
      AND d.parent_symbol = 'SPXW'
      AND c.mid_px > 0.5
    ORDER BY c.ts_event, d.strike_price
    LIMIT 5000
""").df()
con.close()

print(f"Rows loaded: {len(df):,}")

# ── Compute IV + Greeks ────────────────────────────────────
r, q = 0.045, 0.015
results = []

for _, row in df.iterrows():
    S  = float(row['S'])
    K  = float(row['K'])
    exp = pd.Timestamp(row['expiration'])
    exp = exp.tz_localize('UTC') if exp.tzinfo is None else exp.tz_convert('UTC')
    ts  = pd.Timestamp(row['ts_event']).tz_convert('UTC')
    T   = max((exp - ts).total_seconds() / (365.25*86400), 1e-6)

    iv = solve_iv(S, K, T, r, q, float(row['mid_px']), row['option_type'])
    if np.isnan(iv) or iv < 0.01 or iv > 3.0:
        continue

    g = compute_greeks(S, K, T, r, q, iv, row['option_type'])
    results.append({
        'ts_event'    : row['ts_event'],
        'instrument_id': row['instrument_id'],
        'parent_symbol': row['parent_symbol'],
        'strike_price' : K,
        'option_type'  : row['option_type'],
        'expiration'   : row['expiration'],
        'S'            : S,
        'mid_px'       : float(row['mid_px']),
        'iv'           : iv,
        **g
    })

df_greeks = pd.DataFrame(results)
print(f"\nGreeks computed: {len(df_greeks):,} rows")
print(df_greeks[['ts_event','strike_price','option_type','iv',
                  'delta','gamma','vega','theta']].head(10).to_string())

# Simpan ke DuckDB
con = duckdb.connect(DB_PATH)
con.execute("DROP TABLE IF EXISTS greeks_sample")
con.execute("CREATE TABLE greeks_sample AS SELECT * FROM df_greeks")
print(f"\nSaved to greeks_sample table")
con.close()