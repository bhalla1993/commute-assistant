"""
GTFS Static Data Loader
-----------------------
Loads the GTFS zip into the SQLite database.

Usage:
    python -m db.load_gtfs --zip data/gtfs/GTFS_Durham_TXT.zip

Download the GTFS zip from:
    https://opendata.durham.ca/search?tags=Durham%2520Transit
    → "GTFS Schedule" dataset → Download ZIP

Re-run whenever Durham Region publishes a new timetable.
"""
import csv
import io
import sqlite3
import zipfile
import argparse
from pathlib import Path

from db.database import get_connection, init_db

# Maps GTFS filename → (table_name, [columns to import])
GTFS_FILE_MAP = {
    "stops.txt": (
        "stops",
        ["stop_id", "stop_name", "stop_lat", "stop_lon"],
    ),
    "routes.txt": (
        "routes",
        ["route_id", "route_short_name", "route_long_name", "route_type"],
    ),
    "trips.txt": (
        "trips",
        ["trip_id", "route_id", "service_id", "trip_headsign", "direction_id"],
    ),
    "stop_times.txt": (
        "stop_times",
        ["trip_id", "stop_sequence", "stop_id", "arrival_time", "departure_time"],
    ),
    "calendar_dates.txt": (
        "calendar_dates",
        ["service_id", "date", "exception_type"],
    ),
    "calendar.txt": (
        "calendar",
        ["service_id", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday", "start_date", "end_date"],
    ),
}


def _load_file(
    conn: sqlite3.Connection,
    zf: zipfile.ZipFile,
    gtfs_filename: str,
    table: str,
    columns: list[str],
    batch_size: int = 5000,
) -> int:
    """Load a single GTFS txt file into the database, return row count."""
    try:
        data = zf.read(gtfs_filename).decode("utf-8-sig")
    except KeyError:
        print(f"  [skip] {gtfs_filename} not found in zip")
        return 0

    reader = csv.DictReader(io.StringIO(data))
    placeholders = ", ".join("?" for _ in columns)
    col_list = ", ".join(columns)
    sql = f"INSERT OR REPLACE INTO {table} ({col_list}) VALUES ({placeholders})"

    rows_inserted = 0
    batch: list[tuple] = []

    conn.execute(f"DELETE FROM {table}")  # full reload

    for row in reader:
        values = tuple(row.get(col, None) for col in columns)
        batch.append(values)
        if len(batch) >= batch_size:
            conn.executemany(sql, batch)
            rows_inserted += len(batch)
            batch = []

    if batch:
        conn.executemany(sql, batch)
        rows_inserted += len(batch)

    return rows_inserted


def load_gtfs(zip_path: str) -> None:
    zip_path = Path(zip_path)
    if not zip_path.exists():
        raise FileNotFoundError(f"GTFS zip not found: {zip_path}")

    init_db()
    conn = get_connection()

    print(f"[gtfs] Loading from {zip_path}")
    with zipfile.ZipFile(zip_path) as zf:
        with conn:
            for gtfs_file, (table, columns) in GTFS_FILE_MAP.items():
                count = _load_file(conn, zf, gtfs_file, table, columns)
                print(f"  [gtfs] {table}: {count:,} rows loaded")

    conn.close()
    print("[gtfs] Load complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load GTFS static data into SQLite")
    parser.add_argument(
        "--zip",
        default="data/gtfs/GTFS_Durham_TXT.zip",
        help="Path to the GTFS zip file",
    )
    args = parser.parse_args()
    load_gtfs(args.zip)
