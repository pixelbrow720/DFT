import duckdb

DB_PATH     = r"C:\Users\ollama\Documents\DFT\dft-lite\dft.duckdb"
PARQUET_DIR = r"C:\Users\ollama\Documents\DFT\parquet"

con = duckdb.connect(DB_PATH)

# Drop view lama yang salah
con.execute("DROP VIEW IF EXISTS cbbo_1m_raw")

# Recreate tanpa division
con.execute(f"""
    CREATE VIEW cbbo_1m_raw AS
    SELECT
        ts_event,
        instrument_id,
        bid_px_00 AS bid_px,
        ask_px_00 AS ask_px,
        (bid_px_00 + ask_px_00) / 2.0 AS mid_px
    FROM read_parquet('{PARQUET_DIR}/spx_cbbo_1m.parquet')
    WHERE bid_px_00 > 0 AND ask_px_00 > 0

    UNION ALL

    SELECT
        ts_event,
        instrument_id,
        bid_px_00,
        ask_px_00,
        (bid_px_00 + ask_px_00) / 2.0
    FROM read_parquet('{PARQUET_DIR}/spxw_cbbo_1m.parquet')
    WHERE bid_px_00 > 0 AND ask_px_00 > 0
""")

# Verifikasi — ATM strike 5400 SPXW 0DTE
print("Sample ATM SPXW 0DTE (2026-04-01):")
df = con.execute("""
    SELECT
        c.ts_event,
        d.parent_symbol,
        d.strike_price,
        d.option_type,
        d.expiration::DATE AS expiry,
        c.bid_px,
        c.ask_px,
        c.mid_px
    FROM cbbo_1m_raw c
    JOIN instrument_def d USING (instrument_id)
    WHERE c.ts_event::DATE = '2026-04-01'
      AND d.expiration::DATE = '2026-04-01'
      AND d.strike_price BETWEEN 5400 AND 5500
      AND d.option_type = 'C'
    ORDER BY c.ts_event
    LIMIT 10
""").df()
print(df.to_string())

con.close()
print("\nView fixed!")