from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import duckdb
import pandas as pd
from datetime import datetime

app = FastAPI(title="DFT-Lite API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = r"C:\Users\ollama\Documents\DFT\dft-lite\dft.duckdb"

def get_con():
    return duckdb.connect(DB_PATH, read_only=True)

# ── Health ─────────────────────────────────────────────────
@app.get("/api/v1/health")
def health():
    con = get_con()
    spx_last  = con.execute("SELECT MAX(date) FROM levels_daily").fetchone()[0]
    con.close()
    return {
        "ok": True,
        "ts": datetime.utcnow().isoformat() + "Z",
        "version": "v1",
        "data": {
            "status"    : "replay_mode",
            "spx_last_date": str(spx_last),
        }
    }

# ── Levels ─────────────────────────────────────────────────
@app.get("/api/v1/levels/{parent}")
def get_levels(parent: str, date: str = None):
    con = get_con()
    if date:
        row = con.execute("""
            SELECT * FROM levels_daily
            WHERE date = ? 
            ORDER BY date DESC LIMIT 1
        """, [date]).df()
    else:
        row = con.execute("""
            SELECT * FROM levels_daily
            ORDER BY date DESC LIMIT 1
        """).df()
    con.close()

    if len(row) == 0:
        raise HTTPException(404, f"No data for {parent} {date}")

    r = row.iloc[0]
    return {
        "ok"  : True,
        "ts"  : datetime.utcnow().isoformat() + "Z",
        "data": {
            "parent"          : parent.upper(),
            "date"            : str(r['date']),
            "spot_at_close"   : r['spot'],
            "call_wall"       : r['call_wall'],
            "put_wall"        : r['put_wall'],
            "zero_gamma"      : None if pd.isna(r['zero_gamma']) else r['zero_gamma'],
            "total_gex_dollar": r['total_gex'],
        }
    }

# ── Regime ─────────────────────────────────────────────────
@app.get("/api/v1/regime/{parent}")
def get_regime(parent: str, date: str = None):
    con = get_con()
    if date:
        row = con.execute("""
            SELECT * FROM regime_daily WHERE date = ? LIMIT 1
        """, [date]).df()
    else:
        row = con.execute("""
            SELECT * FROM regime_daily ORDER BY date DESC LIMIT 1
        """).df()
    con.close()

    if len(row) == 0:
        raise HTTPException(404, f"No regime data")

    r = row.iloc[0]
    return {
        "ok"  : True,
        "ts"  : datetime.utcnow().isoformat() + "Z",
        "data": {
            "parent"      : parent.upper(),
            "date"        : str(r['date']),
            "spot"        : r['spot'],
            "zero_gamma"  : None if pd.isna(r['zero_gamma']) else r['zero_gamma'],
            "regime"      : r['regime'],
            "confidence"  : r['confidence'],
            "distance_pct": None if pd.isna(r['distance_pct']) else r['distance_pct'],
        }
    }

# ── HIRO ───────────────────────────────────────────────────
@app.get("/api/v1/hiro/{parent}")
def get_hiro(parent: str, date: str = None):
    con = get_con()
    if date:
        df = con.execute("""
            SELECT * FROM hiro_daily
            WHERE parent_symbol = ?
              AND ts_minute::DATE = ?
            ORDER BY ts_minute
        """, [parent.upper(), date]).df()
    else:
        last = con.execute("""
            SELECT MAX(ts_minute::DATE) FROM hiro_daily
            WHERE parent_symbol = ?
        """, [parent.upper()]).fetchone()[0]
        df = con.execute("""
            SELECT * FROM hiro_daily
            WHERE parent_symbol = ?
              AND ts_minute::DATE = ?
            ORDER BY ts_minute
        """, [parent.upper(), str(last)]).df()
    con.close()

    if len(df) == 0:
        raise HTTPException(404, "No HIRO data")

    return {
        "ok"  : True,
        "ts"  : datetime.utcnow().isoformat() + "Z",
        "data": {
            "parent"         : parent.upper(),
            "bucket"         : "1m",
            "ts"             : df['ts_minute'].astype(str).tolist(),
            "signed_premium" : df['signed_premium'].tolist(),
            "cumulative"     : df['cumulative'].tolist(),
            "n_trades"       : df['n_trades'].tolist(),
        }
    }

# ── Spot ───────────────────────────────────────────────────
@app.get("/api/v1/spot/{asset}")
def get_spot(asset: str):
    con = get_con()
    row = con.execute("""
        SELECT * FROM spot_price ORDER BY ts DESC LIMIT 1
    """).df()
    con.close()

    r = row.iloc[0]
    return {
        "ok"  : True,
        "ts"  : datetime.utcnow().isoformat() + "Z",
        "data": {
            "asset"         : asset.upper(),
            "spot"          : r['spot'],
            "as_of"         : str(r['ts']),
            "source"        : "yahoo_daily_interpolated",
            "stale_seconds" : 60,
        }
    }