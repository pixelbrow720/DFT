import duckdb
import yfinance as yf
import pandas as pd
import numpy as np

DB_PATH = r"C:\Users\ollama\Documents\DFT\dft-lite\dft.duckdb"

print("Downloading SPX daily...")
spx_daily = yf.download("^GSPC", start="2026-04-01", end="2026-05-01",
                          interval="1d", progress=False)

# Fix multi-level columns
spx_daily.columns = spx_daily.columns.get_level_values(0)
spx_daily.index = pd.to_datetime(spx_daily.index, utc=True)

rows = []
for date, row in spx_daily.iterrows():
    times = pd.date_range(
        start=date.replace(hour=13, minute=30),
        end=date.replace(hour=20, minute=0),
        freq="1min",
        tz="UTC"
    )
    n = len(times)
    # float() untuk pastikan scalar bukan array
    o = float(row["Open"])
    c = float(row["Close"])
    prices = np.linspace(o, c, n)
    for t, p in zip(times, prices):
        rows.append({"ts": t, "spot": float(p)})

df_spot = pd.DataFrame(rows)
print(f"Generated {len(df_spot):,} rows")
print(df_spot.dtypes)
print(df_spot.head())

con = duckdb.connect(DB_PATH)
con.execute("DROP TABLE IF EXISTS spot_price")
con.execute("CREATE TABLE spot_price AS SELECT * FROM df_spot")
print(con.execute("SELECT * FROM spot_price LIMIT 5").df().to_string())
con.close()
print("Done!")