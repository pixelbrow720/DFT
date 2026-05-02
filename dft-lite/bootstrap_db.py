import duckdb
import pandas as pd
from pathlib import Path

PARQUET_DIR = r"C:\Users\ollama\Documents\DFT\parquet"
DB_PATH     = r"C:\Users\ollama\Documents\DFT\dft-lite\dft.duckdb"

con = duckdb.connect(DB_PATH)

# ── 1. DEFINITION ──────────────────────────────────────────
print("Loading definition...")
con.execute("""
    CREATE TABLE IF NOT EXISTS instrument_def AS
    SELECT
        instrument_id,
        raw_symbol,
        asset,
        instrument_class   AS option_type,
        expiration,
        strike_price,
        contract_multiplier,
        'SPX' AS parent_symbol
    FROM read_parquet(?)
    WHERE instrument_class IN ('C', 'P')
""", [f"{PARQUET_DIR}/spx_definition.parquet"])

con.execute("""
    INSERT INTO instrument_def
    SELECT
        instrument_id,
        raw_symbol,
        asset,
        instrument_class   AS option_type,
        expiration,
        strike_price,
        contract_multiplier,
        'SPXW' AS parent_symbol
    FROM read_parquet(?)
    WHERE instrument_class IN ('C', 'P')
""", [f"{PARQUET_DIR}/spxw_definition.parquet"])

n = con.execute("SELECT COUNT(*) FROM instrument_def").fetchone()[0]
print(f"  instrument_def: {n:,} rows")

# ── 2. STATISTICS (OI) ─────────────────────────────────────
print("Loading statistics...")
con.execute("""
    CREATE TABLE IF NOT EXISTS option_chain_eod AS
    SELECT
        CAST(ts_event AS DATE)  AS date,
        instrument_id,
        stat_type,
        quantity,
        price,
        'SPX' AS parent_symbol
    FROM read_parquet(?)
    WHERE stat_type = 9   -- OI
""", [f"{PARQUET_DIR}/spx_statistics.parquet"])

con.execute("""
    INSERT INTO option_chain_eod
    SELECT
        CAST(ts_event AS DATE),
        instrument_id,
        stat_type,
        quantity,
        price,
        'SPXW'
    FROM read_parquet(?)
    WHERE stat_type = 9
""", [f"{PARQUET_DIR}/spxw_statistics.parquet"])

n = con.execute("SELECT COUNT(*) FROM option_chain_eod").fetchone()[0]
print(f"  option_chain_eod: {n:,} rows")

# ── 3. Verifikasi join ─────────────────────────────────────
print("\nSample join definition + OI:")
result = con.execute("""
    SELECT
        d.parent_symbol,
        d.strike_price,
        d.option_type,
        d.expiration::DATE AS expiry,
        SUM(o.quantity)    AS total_oi
    FROM instrument_def d
    JOIN option_chain_eod o USING (instrument_id)
    GROUP BY 1,2,3,4
    ORDER BY total_oi DESC
    LIMIT 10
""").df()
print(result.to_string())

con.close()
print("\nDone! dft.duckdb siap.")