import duckdb
import numpy as np
import pandas as pd
from scipy.stats import norm
from scipy.optimize import brentq

DB_PATH = r"C:\Users\ollama\Documents\DFT\dft-lite\dft.duckdb"

def bsm_price(S, K, T, r, q, sigma, opt_type):
    if T <= 0 or sigma <= 0: return 0.0
    d1 = (np.log(S/K) + (r-q+0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    d2 = d1 - sigma*np.sqrt(T)
    if opt_type == 'C':
        return S*np.exp(-q*T)*norm.cdf(d1) - K*np.exp(-r*T)*norm.cdf(d2)
    else:
        return K*np.exp(-r*T)*norm.cdf(-d2) - S*np.exp(-q*T)*norm.cdf(-d1)

def solve_iv(S, K, T, r, q, mp, ot):
    if T <= 0 or mp <= 0: return np.nan
    try:
        intr = max(0, S-K) if ot=='C' else max(0, K-S)
        if mp <= intr*1.0001: return np.nan
        return brentq(lambda s: bsm_price(S,K,T,r,q,s,ot)-mp,
                      1e-4, 5.0, xtol=1e-6, maxiter=100)
    except: return np.nan

def compute_gamma(S, K, T, r, q, sigma):
    if T <= 0 or sigma <= 0: return 0.0
    d1 = (np.log(S/K) + (r-q+0.5*sigma**2)*T) / (sigma*np.sqrt(T))
    return np.exp(-q*T) * norm.pdf(d1) / (S * sigma * np.sqrt(T))

def compute_levels_for_date(con, date_str, r=0.045, q=0.015, multiplier=100):
    # OI
    df_oi = con.execute(f"""
        SELECT instrument_id, quantity AS open_interest
        FROM option_chain_eod
        WHERE date = '{date_str}' AND stat_type = 9 AND quantity > 0
    """).df()
    if len(df_oi) == 0:
        return None, None

    # EOD prices + spot
    df_eod = con.execute(f"""
        SELECT
            c.instrument_id,
            AVG(c.mid_px)      AS mid_px,
            d.strike_price     AS K,
            d.option_type,
            d.expiration,
            d.parent_symbol,
            AVG(s.spot)        AS S
        FROM cbbo_1m_raw c
        JOIN instrument_def d USING (instrument_id)
        JOIN spot_price s
          ON date_trunc('minute', c.ts_event) = date_trunc('minute', s.ts)
        WHERE c.ts_event::DATE = '{date_str}'
          AND c.mid_px > 0.1
        GROUP BY c.instrument_id, d.strike_price, d.option_type,
                 d.expiration, d.parent_symbol
    """).df()
    if len(df_eod) == 0:
        return None, None

    df = df_eod.merge(df_oi, on='instrument_id', how='inner')
    if len(df) == 0:
        return None, None

    spot = df['S'].mean()
    gex_rows = []

    for _, row in df.iterrows():
        S  = float(row['S'])
        K  = float(row['K'])
        oi = float(row['open_interest'])
        exp = pd.Timestamp(row['expiration'])
        exp = exp.tz_localize('UTC') if exp.tzinfo is None else exp.tz_convert('UTC')
        T   = max((exp - pd.Timestamp(date_str, tz='UTC')).total_seconds()/(365.25*86400), 1/365)

        iv = solve_iv(S, K, T, r, q, float(row['mid_px']), row['option_type'])
        if np.isnan(iv) or iv < 0.01 or iv > 3.0: continue

        gamma = compute_gamma(S, K, T, r, q, iv)
        sign  = 1 if row['option_type'] == 'C' else -1
        gex   = sign * gamma * oi * multiplier * S**2

        gex_rows.append({'strike': K, 'gex': gex,
                          'parent': row['parent_symbol']})

    if not gex_rows:
        return None, None

    df_gex = pd.DataFrame(gex_rows)
    df_strike = (df_gex.groupby('strike')['gex']
                 .sum().reset_index().sort_values('strike').reset_index(drop=True))
    df_strike['cum_gex'] = df_strike['gex'].cumsum()

    # Levels
    pos = df_strike[df_strike['gex'] > 0]
    neg = df_strike[df_strike['gex'] < 0]
    call_wall = float(pos.loc[pos['gex'].idxmax(), 'strike']) if len(pos) else None
    put_wall  = float(neg.loc[neg['gex'].idxmin(), 'strike']) if len(neg) else None

    zero_gamma = None
    sc = np.sign(df_strike['cum_gex']).diff().abs() > 0
    if sc.any():
        idx = sc[sc].index[0]
        if idx > 0:
            x1,y1 = df_strike.loc[idx-1,['strike','cum_gex']]
            x2,y2 = df_strike.loc[idx,  ['strike','cum_gex']]
            if (y2-y1) != 0:
                zero_gamma = float(x1 - y1*(x2-x1)/(y2-y1))

    level = {
        'date'       : date_str,
        'spot'       : round(spot, 2),
        'call_wall'  : call_wall,
        'put_wall'   : put_wall,
        'zero_gamma' : round(zero_gamma, 2) if zero_gamma else None,
        'total_gex'  : round(df_strike['gex'].sum(), 0)
    }
    return level, df_strike

# ── Run untuk semua trading days ──────────────────────────
con = duckdb.connect(DB_PATH)

trading_days = con.execute("""
    SELECT DISTINCT ts_event::DATE AS date
    FROM cbbo_1m_raw
    ORDER BY date
""").df()['date'].tolist()

print(f"Trading days: {len(trading_days)}")
print(trading_days)

all_levels = []
for date in trading_days:
    # Skip NaT dan weekend
    if pd.isna(date):
        continue
    date_str = str(date.date())
    print(f"Computing {date_str}...", end=" ", flush=True)
    level, _ = compute_levels_for_date(con, date_str)
    if level:
        all_levels.append(level)
        print(f"CW={level['call_wall']} PW={level['put_wall']} "
              f"ZG={level['zero_gamma']} spot={level['spot']}")
    else:
        print("skip")

con.close()

df_levels = pd.DataFrame(all_levels)
print(f"\n{'='*60}")
print("DAILY LEVELS SUMMARY:")
print(df_levels.to_string())

# Simpan
con = duckdb.connect(DB_PATH)
con.execute("DROP TABLE IF EXISTS levels_daily")
con.execute("CREATE TABLE levels_daily AS SELECT * FROM df_levels")
con.close()
print("\nSaved to levels_daily!")