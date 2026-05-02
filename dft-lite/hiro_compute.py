import duckdb
import numpy as np
import pandas as pd

DB_PATH     = r"C:\Users\ollama\Documents\DFT\dft-lite\dft.duckdb"
PARQUET_DIR = r"C:\Users\ollama\Documents\DFT\parquet"

con = duckdb.connect(DB_PATH)

# Buat view trades
print("Creating trades view...")
con.execute("DROP VIEW IF EXISTS trades_raw")
con.execute(f"""
    CREATE VIEW trades_raw AS
    SELECT ts_event, instrument_id, price, size, side
    FROM read_parquet('{PARQUET_DIR}/spx_trades.parquet')
    WHERE action = 'T' AND price > 0 AND size > 0

    UNION ALL

    SELECT ts_event, instrument_id, price, size, side
    FROM read_parquet('{PARQUET_DIR}/spxw_trades.parquet')
    WHERE action = 'T' AND price > 0 AND size > 0
""")

# Lee-Ready: side B=+1, S=-1, N=pakai tick rule
print("Computing HIRO for 2026-04-08...")
df = con.execute("""
    SELECT
        t.ts_event,
        t.instrument_id,
        t.price,
        t.size,
        t.side,
        d.parent_symbol,
        d.option_type,
        d.strike_price
    FROM trades_raw t
    JOIN instrument_def d USING (instrument_id)
    WHERE t.ts_event::DATE = '2026-04-08'
    ORDER BY t.ts_event
""").df()
con.close()

print(f"Trades loaded: {len(df):,}")
print(f"Side distribution: {df['side'].value_counts().to_dict()}")

# ── Lee-Ready classifier ───────────────────────────────────
def lee_ready(df):
    """
    B → +1 (buy aggressor)
    S → -1 (sell aggressor)
    N → tick rule (price vs prev trade)
    """
    sides = []
    prev_prices = {}  # per instrument_id

    for _, row in df.iterrows():
        iid = row['instrument_id']
        if row['side'] == 'B':
            side = 1
        elif row['side'] == 'S':
            side = -1
        else:
            # Tick rule
            prev = prev_prices.get(iid, None)
            if prev is None:
                side = 0
            elif row['price'] > prev:
                side = 1
            elif row['price'] < prev:
                side = -1
            else:
                side = 0
        sides.append(side)
        prev_prices[iid] = row['price']

    return sides

print("Running Lee-Ready classifier...")
df['lr_side'] = lee_ready(df)
print(f"Side after LR: {pd.Series(df['lr_side']).value_counts().to_dict()}")

# ── Compute signed premium ─────────────────────────────────
multiplier = 100
df['signed_premium'] = df['lr_side'] * df['price'] * df['size'] * multiplier

# ── Aggregate ke 1-minute buckets ─────────────────────────
df['ts_minute'] = df['ts_event'].dt.floor('1min')

hiro = (df.groupby(['ts_minute', 'parent_symbol'])
        .agg(
            signed_premium=('signed_premium', 'sum'),
            n_trades=('size', 'count'),
            n_block=('size', lambda x: (x >= 50).sum())
        )
        .reset_index()
        .sort_values('ts_minute'))

# Cumulative per parent
hiro['cumulative'] = hiro.groupby('parent_symbol')['signed_premium'].cumsum()

print(f"\nHIRO 1-min buckets: {len(hiro):,}")
print(hiro[hiro['parent_symbol']=='SPXW'].head(20).to_string())

# Plot simple untuk visualisasi
print("\nSPXW HIRO summary:")
spxw = hiro[hiro['parent_symbol']=='SPXW']
print(f"  Max cumulative : ${spxw['cumulative'].max():,.0f}")
print(f"  Min cumulative : ${spxw['cumulative'].min():,.0f}")
print(f"  Final cumulative: ${spxw['cumulative'].iloc[-1]:,.0f}")
print(f"  Total trades   : {spxw['n_trades'].sum():,}")

# Simpan ke DuckDB
con = duckdb.connect(DB_PATH)
con.execute("DROP TABLE IF EXISTS hiro_daily")
con.execute("CREATE TABLE hiro_daily AS SELECT * FROM hiro")
print("\nSaved to hiro_daily!")

# Simpan juga view trades
print("trades_raw view created ✅")
con.close()