from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import duckdb
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

app = FastAPI(title="DFT-Lite API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = r"C:\Users\ollama\Documents\DFT\dft-lite\dft.duckdb"
EVENTS_CSV = Path(__file__).resolve().parent / "data" / "macro_events.csv"

def get_con():
    return duckdb.connect(DB_PATH, read_only=True)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

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

# ── GEX Heatmap (L1.5) ─────────────────────────────────────
def _heatmap_table_exists(con: duckdb.DuckDBPyConnection) -> bool:
    row = con.execute(
        """
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_name = 'exposure_per_strike_minute'
        """
    ).fetchone()
    return bool(row and row[0])


@app.get("/api/v1/gex/heatmap/{parent}")
def get_gex_heatmap(parent: str, date: str = None):
    parent = parent.upper()
    con = get_con()

    if not _heatmap_table_exists(con):
        con.close()
        raise HTTPException(
            503,
            "exposure_per_strike_minute table not built. "
            "Run `python gex_heatmap_compute.py` first.",
        )

    if date:
        df = con.execute(
            """
            SELECT ts, strike, gex_dollar
            FROM exposure_per_strike_minute
            WHERE parent_symbol = ?
              AND ts::DATE = ?
            ORDER BY ts, strike
            """,
            [parent, date],
        ).df()
    else:
        last = con.execute(
            """
            SELECT MAX(ts::DATE) FROM exposure_per_strike_minute
            WHERE parent_symbol = ?
            """,
            [parent],
        ).fetchone()[0]
        if last is None:
            con.close()
            raise HTTPException(404, f"No heatmap data for {parent}")
        df = con.execute(
            """
            SELECT ts, strike, gex_dollar
            FROM exposure_per_strike_minute
            WHERE parent_symbol = ?
              AND ts::DATE = ?
            ORDER BY ts, strike
            """,
            [parent, str(last)],
        ).df()
        date = str(last)

    con.close()

    if len(df) == 0:
        raise HTTPException(404, f"No heatmap data for {parent} {date}")

    # Pivot long → wide [strike × ts]; preserve sorted strikes (asc) and times.
    df["strike"] = df["strike"].astype(float)
    pivot = (
        df.pivot_table(
            index="strike",
            columns="ts",
            values="gex_dollar",
            aggfunc="sum",
        )
        .sort_index()
    )
    pivot = pivot.reindex(sorted(pivot.columns), axis=1)
    pivot = pivot.fillna(0.0)

    strikes = [float(s) for s in pivot.index.tolist()]
    ts_minutes = [pd.Timestamp(c).strftime("%H:%M") for c in pivot.columns]
    gex_matrix = pivot.values.astype(float).tolist()

    flat = pivot.values.astype(float).flatten()
    flat = flat[np.isfinite(flat)]
    if flat.size:
        q = np.quantile(flat, [0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95]).tolist()
    else:
        q = [0.0] * 7

    return {
        "ok": True,
        "ts": _utc_now().isoformat().replace("+00:00", "Z"),
        "version": "v1",
        "data": {
            "parent": parent,
            "date": str(date),
            "strikes": strikes,
            "ts_minutes": ts_minutes,
            "gex_dollar": gex_matrix,
            "color_quantiles": {
                "p05": q[0],
                "p10": q[1],
                "p25": q[2],
                "p50": q[3],
                "p75": q[4],
                "p90": q[5],
                "p95": q[6],
            },
        },
    }


# ── Events / Macro Calendar (L1.8) ─────────────────────────
def _load_events() -> pd.DataFrame:
    if not EVENTS_CSV.exists():
        return pd.DataFrame(columns=["event_type", "timestamp"])
    df = pd.read_csv(EVENTS_CSV)
    if "timestamp" not in df.columns or "event_type" not in df.columns:
        return pd.DataFrame(columns=["event_type", "timestamp"])
    df["event_type"] = df["event_type"].astype(str).str.upper().str.strip()
    # CSV mixes date-only OPEX rows with full timestamps for FOMC/CPI/NFP;
    # format="ISO8601" tolerates both within the same column.
    df["timestamp"] = pd.to_datetime(
        df["timestamp"], utc=True, errors="coerce", format="ISO8601"
    )
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    return df


def _next_event(df: pd.DataFrame, kind: str, now_utc: datetime):
    if df.empty:
        return None
    rows = df[(df["event_type"] == kind) & (df["timestamp"] >= pd.Timestamp(now_utc))]
    if rows.empty:
        return None
    ts = rows.iloc[0]["timestamp"]
    return ts


def _is_quad_witching(opex_date: pd.Timestamp | None) -> bool:
    if opex_date is None:
        return False
    # Quad witching = third Friday of Mar / Jun / Sep / Dec.
    if opex_date.weekday() != 4:  # 0=Mon .. 4=Fri
        return False
    if opex_date.month not in (3, 6, 9, 12):
        return False
    return 15 <= opex_date.day <= 21


@app.get("/api/v1/events/next")
def get_events_next():
    now = _utc_now()
    df = _load_events()

    next_fomc = _next_event(df, "FOMC", now)
    next_cpi  = _next_event(df, "CPI",  now)
    next_nfp  = _next_event(df, "NFP",  now)
    next_opex = _next_event(df, "OPEX", now)

    candidates = [t for t in (next_fomc, next_cpi, next_nfp, next_opex) if t is not None]
    if candidates:
        soonest = min(candidates)
        days_to_next = max(0, int((soonest - pd.Timestamp(now)).total_seconds() // 86400))
    else:
        days_to_next = None

    def _iso(ts) -> str | None:
        if ts is None:
            return None
        ts = pd.Timestamp(ts)
        if ts.normalize() == ts:
            return ts.strftime("%Y-%m-%d")
        return ts.strftime("%Y-%m-%dT%H:%M:%SZ")

    return {
        "ok": True,
        "ts": now.isoformat().replace("+00:00", "Z"),
        "version": "v1",
        "data": {
            "next_fomc": _iso(next_fomc),
            "next_cpi":  _iso(next_cpi),
            "next_nfp":  _iso(next_nfp),
            "next_opex": _iso(next_opex),
            "is_quad_witching": _is_quad_witching(next_opex),
            "days_to_next_event": days_to_next,
        },
    }