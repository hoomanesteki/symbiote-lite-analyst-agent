import sqlite3
import pandas as pd
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
CSV_PATH = DATA_DIR / "yellow_tripdata_sample.csv"
DB_PATH = DATA_DIR / "taxi.db"

print("📥 Loading CSV...")
df = pd.read_csv(CSV_PATH)

# Normalize column names (important for SQL + agents)
df.columns = (
    df.columns
    .str.strip()
    .str.lower()
    .str.replace(" ", "_")
)

# Convert datetime columns if present
for col in ["pickup_datetime", "dropoff_datetime"]:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce")

print("🗄️ Creating SQLite database...")
conn = sqlite3.connect(DB_PATH)

df.to_sql(
    "taxi_trips",
    conn,
    if_exists="replace",
    index=False
)

conn.close()

print("✅ SQLite DB created:", DB_PATH)
print("Rows loaded:", len(df))
