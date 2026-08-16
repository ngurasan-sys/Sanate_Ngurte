"""One-time ETL: convert the raw OI-buildup CSV exports (NIFTY/SENSEX,
1-minute per-strike option premium OHLCV + OI, ~11M / ~8.5M rows) into a
Parquet dataset partitioned by underlying + year-month.

Why this exists: the source CSVs are multiple GB each. Re-parsing the
whole file on every backtest run would make iteration impractical — this
script runs once (or whenever new export data lands) and the backtest
engine only ever reads the specific underlying + date-range partitions it
needs afterward.

Usage:
    python backend/scripts/convert_oi_data_to_parquet.py \
        --source "D:/exports" --dest "D:/sanate_data/oi_parquet"

Expects source files named "{UNDERLYING}_oi_buildup_*.csv" with columns
timestamp,symbol,strike,option_type,open,high,low,close,volume,oi
(verified against the real files during development — see the CSV
schema check that shaped this: strikes on NIFTY's real 50-point grid,
option_type in {CE, PE}, ISO timestamps in UTC).
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

CHUNK_SIZE = 500_000
DTYPES = {
    "symbol": "string",
    "strike": "float64",
    "option_type": "string",
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    "volume": "int64",
    "oi": "int64",
}


def convert_file(source_csv: Path, dest_dir: Path, underlying: str) -> int:
    """Streams the CSV in chunks, groups each chunk by year-month, and
    appends to one ParquetWriter per month partition — never holds the
    full file in memory. Deliberately avoids pandas 'category' dtype for
    the string columns: a category's dictionary can differ between
    chunks (e.g. a chunk that only contains CE rows), which produces a
    different Arrow schema per chunk and breaks ParquetWriter's
    single-schema-per-file assumption. Plain strings keep the schema
    identical across every chunk; Parquet dictionary-encodes them at the
    storage layer regardless.
    """
    writers = {}
    total_rows = 0
    try:
        for chunk in pd.read_csv(
            source_csv, dtype=DTYPES, parse_dates=["timestamp"], chunksize=CHUNK_SIZE
        ):
            chunk["year_month"] = chunk["timestamp"].dt.strftime("%Y-%m")
            for year_month, group in chunk.groupby("year_month", observed=True):
                partition_dir = dest_dir / underlying / f"year_month={year_month}"
                partition_dir.mkdir(parents=True, exist_ok=True)
                out_path = partition_dir / "data.parquet"

                table = pa.Table.from_pandas(group.drop(columns=["year_month"]), preserve_index=False)
                if out_path not in writers:
                    writers[out_path] = pq.ParquetWriter(out_path, table.schema)
                writers[out_path].write_table(table)

            total_rows += len(chunk)
            print(f"  ...{total_rows:,} rows processed", file=sys.stderr)
    finally:
        for writer in writers.values():
            writer.close()
    return total_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="D:/exports")
    parser.add_argument("--dest", default="D:/sanate_data/oi_parquet")
    args = parser.parse_args()

    source_dir = Path(args.source)
    dest_dir = Path(args.dest)
    dest_dir.mkdir(parents=True, exist_ok=True)

    for underlying in ("NIFTY", "SENSEX"):
        matches = list(source_dir.glob(f"{underlying}_oi_buildup_*.csv"))
        if not matches:
            print(f"Skipping {underlying}: no {underlying}_oi_buildup_*.csv found in {source_dir}")
            continue
        csv_path = matches[0]
        print(f"Converting {csv_path} -> {dest_dir / underlying} ...")
        rows = convert_file(csv_path, dest_dir, underlying)
        print(f"Done: {underlying} ({rows:,} rows)\n")


if __name__ == "__main__":
    main()
