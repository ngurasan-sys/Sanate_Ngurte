"""Paths for the backtest data pipeline — user/machine-specific, since the
source exports and converted Parquet dataset live outside the repo.
Override via env vars if you're running this on a different machine.
"""

import os
from pathlib import Path

# Where convert_oi_data_to_parquet.py wrote the partitioned Parquet dataset.
OI_PARQUET_DIR = Path(os.environ.get("SANATE_OI_PARQUET_DIR", "D:/sanate_data/oi_parquet"))

# Where the raw *_day.csv (daily spot OHLCV) exports live — small enough
# that no ETL step is needed for these.
RAW_EXPORTS_DIR = Path(os.environ.get("SANATE_RAW_EXPORTS_DIR", "D:/exports"))
