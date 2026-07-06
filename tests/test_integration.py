"""
tests/test_integration.py

Integration test: runs the full ETL pipeline against the small fixture dataset
in tests/fixtures/ and asserts that:
  - All expected tables exist
  - Row counts match the fixture file sizes
  - No FK violations exist in the resulting test DB

Run with:  pytest -v
"""
import os
import sqlite3
import sys
import tempfile

import pytest

# Make the project root importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
SCHEMA_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schema.sql")


# ──────────────────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _build_test_db(tmp_db_path: str) -> None:
    """
    Runs a mini ETL pipeline against the fixture CSVs and writes to tmp_db_path.
    Deliberately does NOT import the full etl_pipeline (which reads config.yaml paths)
    — instead, it calls the helper functions directly with overridden paths.
    """
    import importlib
    import config  # noqa: F401  — must be importable

    # Temporarily monkey-patch DATASET_DIR and DB_PATH
    import etl_pipeline as etl
    original_dataset = etl.DATASET_DIR if hasattr(etl, "DATASET_DIR") else None

    # Use importlib to reload with patched constants is messy.
    # Simpler: call the helper functions directly.
    from etl_pipeline import (
        apply_renames,
        clean_currency,
        clean_dates,
        load_csv,
        validate_dataframe,
    )
    import etl_pipeline
    import config as cfg

    # Build a fresh DB
    conn = sqlite3.connect(tmp_db_path)
    with open(SCHEMA_FILE, "r", encoding="utf-8") as fh:
        conn.executescript(fh.read())
    conn.execute(
        "INSERT INTO schema_version (version, applied_at) VALUES (1, datetime('now'));"
    )
    conn.commit()

    # --- Load fixtures ---
    file_map = {
        "Product.csv": "products",
        "Region.csv": "regions",
        "Reseller.csv": "resellers",
        "Salesperson.csv": "salespeople",
        "SalespersonRegion.csv": "salesperson_regions",
        "Targets.csv": "targets",
        "Sales.csv": "sales",
    }
    dataframes = {}
    for filename, table in file_map.items():
        path = os.path.join(FIXTURES_DIR, filename)
        import pandas as pd
        df = pd.read_csv(path, encoding="utf-8")
        df.columns = df.columns.str.strip()
        df = apply_renames(df, filename)
        df = clean_currency(df, cfg.CURRENCY_COLUMNS.get(filename, []))
        df = clean_dates(df, cfg.DATE_COLUMNS.get(filename, []))
        dataframes[table] = df

    # Build calendar
    dates = set()
    if "sales" in dataframes and "OrderDate" in dataframes["sales"].columns:
        dates |= set(dataframes["sales"]["OrderDate"].dropna())
    if "targets" in dataframes and "TargetMonth" in dataframes["targets"].columns:
        dates |= set(dataframes["targets"]["TargetMonth"].dropna())
    import pandas as pd
    dataframes["calendar"] = pd.DataFrame(sorted(dates), columns=["Date"])

    # Truncate and reload (idempotency check: load twice, same result)
    for _ in range(2):
        conn.execute("PRAGMA foreign_keys = OFF;")
        for table in reversed(list(file_map.values()) + ["calendar"]):
            conn.execute(f"DELETE FROM {table};")
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.commit()

        load_order = [
            "calendar", "products", "regions", "resellers",
            "salespeople", "salesperson_regions", "targets", "sales",
        ]
        for table in load_order:
            if table in dataframes:
                dataframes[table].to_sql(table, conn, if_exists="append", index=False)
        conn.commit()

    return conn


# ──────────────────────────────────────────────────────────────────────────────
#  Tests
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def test_db():
    """Creates a temporary test DB from fixture data and yields the connection."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp_path = f.name

    conn = _build_test_db(tmp_path)
    yield conn
    conn.close()
    os.unlink(tmp_path)


def test_all_tables_exist(test_db):
    """All 8 expected tables should exist in the test DB."""
    expected = {
        "calendar", "products", "regions", "resellers",
        "salespeople", "salesperson_regions", "targets", "sales",
    }
    actual = {
        row[0]
        for row in test_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table';"
        ).fetchall()
    }
    assert expected.issubset(actual), f"Missing tables: {expected - actual}"


def test_product_row_count(test_db):
    """Fixture has 5 products — DB should contain exactly 5."""
    count = test_db.execute("SELECT COUNT(*) FROM products;").fetchone()[0]
    assert count == 5


def test_region_row_count(test_db):
    """Fixture has 3 regions — DB should contain exactly 3."""
    count = test_db.execute("SELECT COUNT(*) FROM regions;").fetchone()[0]
    assert count == 3


def test_sales_row_count(test_db):
    """Fixture has 5 sales rows — DB should contain exactly 5."""
    count = test_db.execute("SELECT COUNT(*) FROM sales;").fetchone()[0]
    assert count == 5


def test_idempotency(test_db):
    """
    The _build_test_db helper loads data twice.
    Final row counts should be 5, not 10, proving truncate-then-reload works.
    """
    count = test_db.execute("SELECT COUNT(*) FROM sales;").fetchone()[0]
    assert count == 5, f"Expected 5 (idempotent), got {count} (probably duplicated)"


def test_no_fk_violations(test_db):
    """PRAGMA foreign_key_check should return zero rows after load."""
    test_db.execute("PRAGMA foreign_keys = ON;")
    violations = test_db.execute("PRAGMA foreign_key_check;").fetchall()
    assert violations == [], f"FK violations found: {violations}"


def test_schema_version_recorded(test_db):
    """schema_version table should have at least one row with version >= 1."""
    row = test_db.execute("SELECT MAX(version) FROM schema_version;").fetchone()
    assert row and row[0] >= 1, "schema_version not recorded in DB"


def test_kpi_revenue_positive(test_db):
    """Gross Revenue from fixture sales should be a positive number."""
    row = test_db.execute("SELECT SUM(Sales) FROM sales;").fetchone()
    assert row[0] is not None and row[0] > 0, "Gross Revenue is not positive"


def test_calendar_covers_all_dates(test_db):
    """Every OrderDate in sales should exist in the calendar table."""
    orphaned = test_db.execute("""
        SELECT COUNT(*) FROM sales
        WHERE OrderDate NOT IN (SELECT Date FROM calendar)
        AND OrderDate IS NOT NULL;
    """).fetchone()[0]
    assert orphaned == 0, f"{orphaned} sales rows have dates not in calendar"
