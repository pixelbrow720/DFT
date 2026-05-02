import duckdb
import numpy as np
import pandas as pd
from scipy.stats import norm
from scipy.optimize import brentq

DB_PATH = r"C:\Users\ollama\Documents\DFT\dft-lite\dft.duckdb"

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

def compute_gamma(S, K, T, r, q, sigma):
    if T <= 0 or sigma <= 0: return 0.0
    d1 = (np.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    return np.exp(-q*T) * norm.pdf(d1) / (S * sigma * np.sqrt(T))

# ── Load EOD snapshot (pakai data terakhir hari itu) ───────
TARGET_DATE = '2026-04-08'
print(f"Computing GEX levels for {TARGET_DATE}...")

con = duckdb.connect(DB_PATH)

# Ambil OI dari statistics
df_oi = con.execute(f"""
    SELECT
        o.instrument_id,
        o.quantity AS open_interest
    FROM option_chain_eod o
    WHERE o.date = '{TARGET_DATE}'
      AND o.stat_type = 9
      AND o.quantity > 0
""").df()
print(f"OI rows: {len(df_oi):,}")

# Tambah debug sebelum query df_eod
print("Cek sample ts_event di cbbo_1m_raw:")
debug = con.execute(f"""
    SELECT 
        MIN(ts_event) AS min_ts,
        MAX(ts_event) AS max_ts,
        COUNT(*) AS n
    FROM cbbo_1m_raw c
    JOIN instrument_def d USING (instrument_id)
    WHERE c.ts_event::DATE = '{TARGET_DATE}'
""").df()
print(debug)

# Ganti query df_eod dengan ini
df_eod = con.execute(f"""
    SELECT
        c.instrument_id,
        AVG(c.mid_px) AS mid_px,
        d.strike_price AS K,
        d.option_type,
        d.expiration,
        d.parent_symbol,
        AVG(s.spot) AS S
    FROM cbbo_1m_raw c
    JOIN instrument_def d USING (instrument_id)
    JOIN spot_price s
      ON date_trunc('minute', c.ts_event) = date_trunc('minute', s.ts)
    WHERE c.ts_event::DATE = '{TARGET_DATE}'
      AND c.mid_px > 0.1
    GROUP BY c.instrument_id, d.strike_price, d.option_type,
             d.expiration, d.parent_symbol
""").df()
con.close()

print(f"EOD price rows: {len(df_eod):,}")

# Merge dengan OI
df = df_eod.merge(df_oi, on='instrument_id', how='inner')
print(f"After OI merge: {len(df):,}")

# ── Compute gamma per row ──────────────────────────────────
r, q, multiplier = 0.045, 0.015, 100
spot_eod = df['S'].mean()
print(f"Spot EOD: {spot_eod:.2f}")

gex_rows = []
for _, row in df.iterrows():
    S  = float(row['S'])
    K  = float(row['K'])
    oi = float(row['open_interest'])
    exp = pd.Timestamp(row['expiration'])
    exp = exp.tz_localize('UTC') if exp.tzinfo is None else exp.tz_convert('UTC')
    T   = max((exp - pd.Timestamp(TARGET_DATE, tz='UTC')).total_seconds() / (365.25*86400), 1/365)

    iv  = solve_iv(S, K, T, r, q, float(row['mid_px']), row['option_type'])
    if np.isnan(iv) or iv < 0.01 or iv > 3.0:
        continue

    gamma = compute_gamma(S, K, T, r, q, iv)

    # GEX: calls = +, puts = -
    sign  = 1 if row['option_type'] == 'C' else -1
    gex   = sign * gamma * oi * multiplier * S**2

    gex_rows.append({
        'strike'      : K,
        'option_type' : row['option_type'],
        'parent_symbol': row['parent_symbol'],
        'expiration'  : row['expiration'],
        'gamma'       : gamma,
        'oi'          : oi,
        'iv'          : iv,
        'gex'         : gex
    })

df_gex = pd.DataFrame(gex_rows)
print(f"GEX rows computed: {len(df_gex):,}")

# ── Aggregate per strike ───────────────────────────────────
df_strike = (df_gex.groupby('strike')['gex']
             .sum()
             .reset_index()
             .sort_values('strike'))

# ── Compute Levels ─────────────────────────────────────────
df_strike['cum_gex'] = df_strike['gex'].cumsum()

# Call Wall = strike dengan max positive GEX
pos = df_strike[df_strike['gex'] > 0]
call_wall = pos.loc[pos['gex'].idxmax(), 'strike'] if len(pos) > 0 else None

# Put Wall = strike dengan min negative GEX
neg = df_strike[df_strike['gex'] < 0]
put_wall = neg.loc[neg['gex'].idxmin(), 'strike'] if len(neg) > 0 else None

# Zero Gamma = interpolasi crossing point
sign_change = np.sign(df_strike['cum_gex']).diff().abs() > 0
zero_gamma = None
if sign_change.any():
    idx = sign_change[sign_change].index[0]
    if idx > 0:
        x1 = df_strike.loc[idx-1, 'strike']
        y1 = df_strike.loc[idx-1, 'cum_gex']
        x2 = df_strike.loc[idx,   'strike']
        y2 = df_strike.loc[idx,   'cum_gex']
        zero_gamma = x1 - y1 * (x2-x1) / (y2-y1)

print(f"\n{'='*40}")
print(f"DATE        : {TARGET_DATE}")
print(f"SPOT (EOD)  : {spot_eod:.2f}")
print(f"CALL WALL   : {call_wall}")
print(f"PUT WALL    : {put_wall}")
print(f"ZERO GAMMA  : {zero_gamma:.2f}" if zero_gamma else "ZERO GAMMA  : None")
print(f"TOTAL GEX   : ${df_strike['gex'].sum():,.0f}")
print(f"{'='*40}")

print("\nTop strikes by GEX:")
print(df_strike.nlargest(10, 'gex')[['strike','gex','cum_gex']].to_string())
print("\nBottom strikes by GEX:")
print(df_strike.nsmallest(10, 'gex')[['strike','gex','cum_gex']].to_string())

# Simpan ke DuckDB
con = duckdb.connect(DB_PATH)
con.execute("DROP TABLE IF EXISTS gex_per_strike")
con.execute("CREATE TABLE gex_per_strike AS SELECT * FROM df_strike")
con.close()
print("\nSaved to gex_per_strike!")