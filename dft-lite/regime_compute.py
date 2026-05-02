import duckdb
import pandas as pd
import numpy as np

DB_PATH = r"C:\Users\ollama\Documents\DFT\dft-lite\dft.duckdb"

con = duckdb.connect(DB_PATH)

# Load levels_daily + spot
df_levels = con.execute("SELECT * FROM levels_daily ORDER BY date").df()

print("Computing regime per day...")
results = []

for _, row in df_levels.iterrows():
    spot = row['spot']
    zg   = row['zero_gamma']
    cw   = row['call_wall']
    pw   = row['put_wall']
    tgex = row['total_gex']

    # Regime logic
    if pd.isna(zg):
        # ZG None = full short gamma
        regime     = 'SHORT_GAMMA'
        confidence = 0.90
        distance   = None
    else:
        distance = (spot - zg) / zg  # pct distance dari ZG
        if spot > zg:
            regime     = 'LONG_GAMMA'
            confidence = min(0.95, abs(distance) * 10)
        elif spot < zg:
            regime     = 'SHORT_GAMMA'
            confidence = min(0.95, abs(distance) * 10)
        else:
            regime     = 'NEUTRAL'
            confidence = 0.50

    # Override: total GEX negatif besar = short gamma
    if tgex < -5e12:
        regime     = 'SHORT_GAMMA'
        confidence = min(0.99, confidence + 0.10)

    results.append({
        'date'        : row['date'],
        'spot'        : spot,
        'call_wall'   : cw,
        'put_wall'    : pw,
        'zero_gamma'  : zg,
        'total_gex'   : tgex,
        'regime'      : regime,
        'confidence'  : round(confidence, 3),
        'distance_pct': round(distance, 6) if distance else None
    })

df_regime = pd.DataFrame(results)
print(df_regime[['date','spot','zero_gamma','regime','confidence']].to_string())

# Simpan
con.execute("DROP TABLE IF EXISTS regime_daily")
con.execute("CREATE TABLE regime_daily AS SELECT * FROM df_regime")
con.close()
print("\nSaved to regime_daily!")