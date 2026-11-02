"""Report what is in MySQL, to fill in .env once credentials are set. Runs SELECT and SHOW only.

    python scripts/inspect_db.py                  list tables with row counts
    python scripts/inspect_db.py <table> <time>   columns, cadence, gaps and history for one table
"""
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.data.mysql_source import make_engine, quote  # noqa: E402


def list_tables(conn):
    tables = [r[0] for r in conn.execute(text("SHOW TABLES"))]
    for t in tables:
        n = conn.execute(text(f"SELECT COUNT(*) FROM {quote(t)}")).scalar()
        print(f"{t}: {n} rows")
    print("\nNext: python scripts/inspect_db.py <table> <time_column>")


def inspect(conn, table, time_col):
    print("Columns:")
    for row in conn.execute(text(f"SHOW COLUMNS FROM {quote(table)}")):
        print(f"  {row[0]}: {row[1]}")

    print("\nServer time zone:", conn.execute(text("SELECT @@global.time_zone, @@session.time_zone")).fetchone())
    first, last, total = conn.execute(text(
        f"SELECT MIN({quote(time_col)}), MAX({quote(time_col)}), COUNT(*) FROM {quote(table)}")).fetchone()
    print(f"\nRange: {first} to {last}, {total} rows")

    print("\nLatest 5 rows:")
    print(pd.read_sql(text(f"SELECT * FROM {quote(table)} ORDER BY {quote(time_col)} DESC LIMIT 5"), conn).to_string())

    times = pd.to_datetime(pd.read_sql(text(
        f"SELECT {quote(time_col)} AS t FROM {quote(table)} ORDER BY {quote(time_col)} DESC LIMIT 20000"), conn)["t"])
    deltas = times.sort_values().diff().dropna()
    print("\nSpacing between rows (latest 20,000):")
    print(deltas.value_counts().head(5).to_string())
    long_gaps = deltas[deltas > pd.Timedelta(minutes=30)]
    print(f"Gaps over 30 min: {len(long_gaps)}, longest {deltas.max()}")
    print(f"Duplicate timestamps: {int(times.duplicated().sum())}")


def main():
    engine = make_engine()
    with engine.connect() as conn:
        if len(sys.argv) == 3:
            inspect(conn, sys.argv[1], sys.argv[2])
        else:
            list_tables(conn)


if __name__ == "__main__":
    main()
