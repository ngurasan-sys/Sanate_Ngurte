import pytest
import os
from app.core.db import DuckDBManager

def test_db_initialization():
    os.environ["DUCKDB_PATH"] = ":memory:"
    db = DuckDBManager()

    db.execute("DELETE FROM levels WHERE level_id = 'L1'")
    # Insert mock level
    db.execute("""
        INSERT INTO levels (level_id, instrument, price, zone_low, zone_high, level_type)
        VALUES ('L1', 'NIFTY', 25000.0, 24995.0, 25005.0, 'Support')
    """)

    result = db.fetchall("SELECT level_id, price FROM levels WHERE level_id = 'L1'")
    assert len(result) == 1
    assert result[0][0] == 'L1'
    assert result[0][1] == 25000.0
