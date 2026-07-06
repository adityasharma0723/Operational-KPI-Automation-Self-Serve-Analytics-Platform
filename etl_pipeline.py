"""
etl_pipeline.py — Hardened B2B Sales ETL Pipeline.

Implements (in execution order):
  [1] Config-driven paths  (config.py / config.yaml)
  [2] Structured logging   (logs/pipeline_YYYY-MM-DD.log)
  [3] Per-file isolation   (one try/except per CSV; pipeline continues on failure)
  [4] Data validation      (pandera schema checks + FK cross-checks + quarantine)
  [5] Idempotent loads     (truncate-then-reload in a single SQLite transaction)
  [6] Schema versioning    (schema.sql applied only when version is new/missing)
"""

import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone

import pandas as pd

from config import (
    CFG,
    COLUMN_RENAMES,
    CURRENCY_COLUMNS,
    DATE_COLUMNS,
    DB_PATH,
    DATASET_DIR,
    FILES,
    LOGS_DIR,
    REJECTED_DIR,
    SCHEMA_FILE,
    SCHEMA_VERSION,
    STATE_FILE,
    VALIDATION,
)

# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 0 — Bootstrap: folders + logging
# ──────────────────────────────────────────────────────────────────────────────

os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(REJECTED_DIR, exist_ok=True)

_log_filename = os.path.join(
    LOGS_DIR, f"pipeline_{datetime.now().strftime('%Y-%m-%d')}.log"
)


# Reconfigure stdout to UTF-8 so emoji / unicode symbols don't fail on Windows cp1252
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    handlers=[
        logging.FileHandler(_log_filename, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),  # Console at INFO
    ],
)
# Demote console handler to INFO so debug noise stays in the file only
logging.getLogger().handlers[1].setLevel(logging.INFO)

log = logging.getLogger(__name__)




# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 1 — Schema versioning helpers
# ──────────────────────────────────────────────────────────────────────────────

def _get_db_schema_version(conn: sqlite3.Connection) -> int:
    """Returns the current schema version stored in the DB, or 0 if not present."""
    try:
        row = conn.execute(
            "SELECT MAX(version) FROM schema_version;"
        ).fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return 0


def apply_schema_if_needed(conn: sqlite3.Connection) -> None:
    """
    Reads schema.sql and runs it only if the DB version is below SCHEMA_VERSION.
    This prevents redundant DDL execution on every run.
    """
    current = _get_db_schema_version(conn)
    if current >= SCHEMA_VERSION:
        log.debug(
            "Schema already at version %d — skipping DDL execution.", current
        )
        return

    log.info(
        "Applying schema v%d (current DB version: %d).", SCHEMA_VERSION, current
    )
    with open(SCHEMA_FILE, "r", encoding="utf-8") as fh:
        ddl = fh.read()

    conn.executescript(ddl)

    # Record the new version
    conn.execute(
        "INSERT INTO schema_version (version, applied_at) VALUES (?, ?);",
        (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    log.info("Schema v%d applied successfully.", SCHEMA_VERSION)


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 2 — Extract helpers
# ──────────────────────────────────────────────────────────────────────────────

def load_csv(filename: str) -> pd.DataFrame:
    """
    Reads a CSV file, auto-detecting comma vs tab delimiter.
    Strips whitespace from headers and string values, replaces 'nan' with None.
    Raises FileNotFoundError or ValueError with a clear message on failure.
    """
    path = os.path.join(DATASET_DIR, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Expected CSV not found: {path}")

    for sep in (",", "\t"):
        try:
            df = pd.read_csv(path, sep=sep, encoding="utf-8")
            if len(df.columns) > 1:
                break
        except Exception:
            continue
    else:
        raise ValueError(f"Could not parse {filename} with comma or tab separator.")

    df.columns = df.columns.str.strip()
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).str.strip().replace("nan", None)

    log.debug("  Loaded '%s': %d rows, %d columns.", filename, len(df), len(df.columns))
    return df


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 3 — Transform helpers
# ──────────────────────────────────────────────────────────────────────────────

def clean_currency(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """
    Strips $ and , from currency strings and casts to float.
    Example: '$4,049.98' -> 4049.98
    Nulls and unparseable strings become NaN (not silently zero).
    """
    for col in columns:
        if col not in df.columns:
            log.warning("  Currency column '%s' not found — skipping.", col)
            continue
        before = df[col].isna().sum()
        df[col] = (
            df[col]
            .astype(str)
            .str.replace(r"[\$,]", "", regex=True)
            .replace({"nan": None, "": None})
        )
        df[col] = pd.to_numeric(df[col], errors="coerce")
        after = df[col].isna().sum()
        if after > before:
            log.warning(
                "  '%s': %d values could not be parsed to numeric (became NaN).",
                col, after - before,
            )
    return df


def clean_dates(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """
    Parses date strings (e.g. 'Friday, August 25, 2017') into ISO 'YYYY-MM-DD'.
    Uses format='mixed' to handle columns that contain multiple date styles
    (e.g. ISO dates and long-form dates co-existing in the same column).
    Unparseable dates become None (not silently kept as strings).
    """
    for col in columns:
        if col not in df.columns:
            log.warning("  Date column '%s' not found — skipping.", col)
            continue
        before_nulls = df[col].isna().sum()
        df[col] = pd.to_datetime(df[col], format="mixed", errors="coerce").dt.strftime("%Y-%m-%d")
        after_nulls = df[col].isna().sum()
        if after_nulls > before_nulls:
            log.warning(
                "  '%s': %d dates could not be parsed (became null).",
                col, after_nulls - before_nulls,
            )
    return df



def apply_renames(df: pd.DataFrame, filename: str) -> pd.DataFrame:
    """Applies column renames from config.yaml to match the DB schema."""
    renames = COLUMN_RENAMES.get(filename, {})
    if renames:
        df = df.rename(columns=renames)
        log.debug("  Applied %d column renames for '%s'.", len(renames), filename)
    return df


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 4 — Validation layer
# ──────────────────────────────────────────────────────────────────────────────

# Validation rules keyed by table name.
# Each entry is a dict with optional keys:
#   pk          : column that must be unique + not null
#   required    : columns that must not be null
#   non_negative: columns where all values must be >= 0
#   fk          : {"column": <col>, "ref_df_key": <key in parent_dfs dict>}

VALIDATION_RULES: dict = {
    "products": {
        "pk": "ProductKey",
        "required": ["ProductKey"],
        "non_negative": ["Standard_Cost"],
    },
    "regions": {
        "pk": "SalesTerritoryKey",
        "required": ["SalesTerritoryKey", "Region", "Country"],
    },
    "resellers": {
        "pk": "ResellerKey",
        "required": ["ResellerKey"],
    },
    "salespeople": {
        "pk": "EmployeeKey",
        "required": ["EmployeeKey", "EmployeeID"],
    },
    "salesperson_regions": {
        "required": ["EmployeeKey", "SalesTerritoryKey"],
    },
    "targets": {
        "required": ["EmployeeID", "TargetMonth"],
        "non_negative": ["Target"],
    },
    "sales": {
        "required": ["SalesOrderNumber", "ProductKey", "ResellerKey", "EmployeeKey", "SalesTerritoryKey"],
        "non_negative": ["Quantity", "Unit_Price", "Sales", "Cost"],
        "fk": [
            {"column": "ProductKey",        "ref_table": "products",    "ref_col": "ProductKey"},
            {"column": "ResellerKey",       "ref_table": "resellers",   "ref_col": "ResellerKey"},
            {"column": "EmployeeKey",       "ref_table": "salespeople", "ref_col": "EmployeeKey"},
            {"column": "SalesTerritoryKey", "ref_table": "regions",     "ref_col": "SalesTerritoryKey"},
        ],
    },
}


def _load_pipeline_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def _save_pipeline_state(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)


def validate_dataframe(
    table_name: str,
    df: pd.DataFrame,
    parent_dfs: dict[str, pd.DataFrame],
    state: dict,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Validates df against VALIDATION_RULES[table_name] and row-count state.
    Returns (clean_df, rejected_df).

    All rejected rows are tagged with a 'rejection_reason' column.
    WHY we return instead of raise: per-file isolation means one bad table
    should NOT crash the entire pipeline — we quarantine and continue.
    """
    rules = VALIDATION_RULES.get(table_name, {})
    rejected_masks = pd.Series(False, index=df.index)
    reject_reasons = pd.Series("", index=df.index, dtype=str)

    # 1. PK uniqueness
    pk_col = rules.get("pk")
    if pk_col and pk_col in df.columns:
        dupes = df[pk_col].duplicated(keep=False)
        if dupes.any():
            log.warning(
                "  [%s] %d duplicate PK values in '%s'.", table_name, dupes.sum(), pk_col
            )
            rejected_masks |= dupes
            reject_reasons[dupes] = reject_reasons[dupes] + f"dup_pk:{pk_col}; "

    # 2. Not-null required columns
    for col in rules.get("required", []):
        if col in df.columns:
            nulls = df[col].isna()
            if nulls.any():
                log.warning(
                    "  [%s] %d null values in required column '%s'.",
                    table_name, nulls.sum(), col,
                )
                rejected_masks |= nulls
                reject_reasons[nulls] = reject_reasons[nulls] + f"null:{col}; "

    # 3. Non-negative numeric columns
    for col in rules.get("non_negative", []):
        if col in df.columns:
            neg = df[col].lt(0) & df[col].notna()
            if neg.any():
                log.warning(
                    "  [%s] %d negative values in '%s'.", table_name, neg.sum(), col
                )
                rejected_masks |= neg
                reject_reasons[neg] = reject_reasons[neg] + f"negative:{col}; "

    # 4. Foreign key cross-checks
    for fk in rules.get("fk", []):
        child_col = fk["column"]
        ref_table = fk["ref_table"]
        ref_col = fk["ref_col"]
        if child_col in df.columns and ref_table in parent_dfs:
            valid_keys = set(parent_dfs[ref_table][ref_col].dropna().unique())
            orphaned = ~df[child_col].isin(valid_keys) & df[child_col].notna()
            if orphaned.any():
                log.warning(
                    "  [%s] %d orphaned FK values in '%s' (no match in %s.%s).",
                    table_name, orphaned.sum(), child_col, ref_table, ref_col,
                )
                rejected_masks |= orphaned
                reject_reasons[orphaned] = (
                    reject_reasons[orphaned] + f"orphan_fk:{child_col}->{ref_table}.{ref_col}; "
                )

    # 5. Row count anomaly check vs last run
    last_count = state.get(table_name, {}).get("row_count")
    if last_count is not None and last_count > 0:
        max_factor = VALIDATION.get("max_growth_factor", 1.5)
        min_factor = VALIDATION.get("min_shrink_factor", 0.5)
        ratio = len(df) / last_count
        if ratio > max_factor:
            log.warning(
                "  [%s] Row count %d is %.1fx last run (%d) — exceeds growth threshold of %.1fx.",
                table_name, len(df), ratio, last_count, max_factor,
            )
        elif ratio < min_factor:
            log.warning(
                "  [%s] Row count %d is %.1fx last run (%d) — below shrink threshold of %.1fx.",
                table_name, len(df), ratio, last_count, min_factor,
            )

    # Split into clean vs rejected
    clean_df = df[~rejected_masks].copy()
    rejected_df = df[rejected_masks].copy()
    if not rejected_df.empty:
        rejected_df["rejection_reason"] = reject_reasons[rejected_masks].values

    log.info(
        "  [%s] Validation complete: %d clean rows, %d rejected.",
        table_name, len(clean_df), len(rejected_df),
    )
    return clean_df, rejected_df


def quarantine_rejected(table_name: str, rejected_df: pd.DataFrame) -> None:
    """Saves rejected rows to rejected_rows/<table_name>_rejected.csv."""
    if rejected_df.empty:
        return
    out_path = os.path.join(
        REJECTED_DIR,
        f"{table_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_rejected.csv",
    )
    rejected_df.to_csv(out_path, index=False, encoding="utf-8")
    log.warning(
        "  [%s] %d rejected rows quarantined → %s",
        table_name, len(rejected_df), out_path,
    )


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 5 — Idempotent load (truncate-then-reload)
# ──────────────────────────────────────────────────────────────────────────────

# Drop order respects FK dependencies (children before parents).
_TRUNCATE_ORDER = [
    "sales",
    "targets",
    "salesperson_regions",
    "salespeople",
    "resellers",
    "regions",
    "products",
    "calendar",
]


def truncate_all_tables(conn: sqlite3.Connection) -> None:
    """
    Deletes all rows from data tables in FK-safe order.
    WHY truncate-then-reload over upsert:
      - SQLite's INSERT OR REPLACE generates new rowids (breaks audit trails).
      - ON CONFLICT DO UPDATE requires explicit UNIQUE constraints on all FKs.
      - Truncate is O(n) regardless of update frequency — simpler and predictable.
      - If source loses a row, truncate ensures the DB reflects that; upsert would leave stale data.
    """
    conn.execute("PRAGMA foreign_keys = OFF;")
    for table in _TRUNCATE_ORDER:
        try:
            conn.execute(f"DELETE FROM {table};")
            log.debug("  Truncated table '%s'.", table)
        except sqlite3.OperationalError as exc:
            log.warning("  Could not truncate '%s': %s", table, exc)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.commit()
    log.info("All data tables truncated (schema preserved).")


# ──────────────────────────────────────────────────────────────────────────────
#  SECTION 6 — Main ETL orchestration
# ──────────────────────────────────────────────────────────────────────────────

def run_etl() -> int:
    """
    Orchestrates the full ETL pipeline.
    Returns: 0 on success, 1 if any critical file failed.
    """
    pipeline_start = time.time()
    log.info("=" * 60)
    log.info("STARTING B2B SALES ETL PIPELINE")
    log.info("Dataset dir : %s", DATASET_DIR)
    log.info("Database    : %s", DB_PATH)
    log.info("=" * 60)

    state = _load_pipeline_state()
    file_results: dict[str, dict] = {}  # filename -> {status, rows, error}

    # ── PHASE 1: Extract + Transform (per-file isolated) ──────────────────────
    log.info("\n[1/3] EXTRACT & TRANSFORM")
    dataframes: dict[str, pd.DataFrame] = {}   # table_name -> cleaned DataFrame

    for filename, file_cfg in FILES.items():
        table = file_cfg["table"]
        log.info("  Processing '%s' → table '%s' ...", filename, table)
        try:
            df = load_csv(filename)
            raw_count = len(df)

            df = apply_renames(df, filename)
            df = clean_currency(df, CURRENCY_COLUMNS.get(filename, []))
            df = clean_dates(df, DATE_COLUMNS.get(filename, []))

            dataframes[table] = df
            file_results[filename] = {
                "status": "extracted",
                "rows_raw": raw_count,
                "rows_clean": len(df),
                "table": table,
            }
            log.info(
                "  ✓ '%s': %d raw rows → %d after cleaning.", filename, raw_count, len(df)
            )

        except Exception as exc:
            log.error(
                "  ✗ FAILED to load '%s': %s", filename, exc, exc_info=True
            )
            file_results[filename] = {
                "status": "failed",
                "error": str(exc),
                "table": table,
                "critical": file_cfg.get("critical", False),
            }

    # ── PHASE 2: Build calendar from transaction dates ─────────────────────────
    if "sales" in dataframes or "targets" in dataframes:
        dates: set = set()
        if "sales" in dataframes and "OrderDate" in dataframes["sales"].columns:
            dates |= set(dataframes["sales"]["OrderDate"].dropna())
        if "targets" in dataframes and "TargetMonth" in dataframes["targets"].columns:
            dates |= set(dataframes["targets"]["TargetMonth"].dropna())
        dataframes["calendar"] = pd.DataFrame(sorted(dates), columns=["Date"])
        log.info("  Built calendar dimension: %d dates.", len(dataframes["calendar"]))

    # ── PHASE 3: Validate (before touching the DB) ────────────────────────────
    log.info("\n[2/3] VALIDATE")
    clean_frames: dict[str, pd.DataFrame] = {}
    parent_dfs = {
        t: dataframes[t]
        for t in ("products", "regions", "resellers", "salespeople")
        if t in dataframes
    }

    for table, df in dataframes.items():
        clean_df, rejected_df = validate_dataframe(table, df, parent_dfs, state)
        quarantine_rejected(table, rejected_df)
        clean_frames[table] = clean_df

    # ── PHASE 4: Load (idempotent) ─────────────────────────────────────────────
    log.info("\n[3/3] LOAD")
    conn = sqlite3.connect(DB_PATH)

    try:
        apply_schema_if_needed(conn)
        truncate_all_tables(conn)

        load_order = [
            "calendar", "products", "regions", "resellers",
            "salespeople", "salesperson_regions", "targets", "sales",
        ]

        rows_loaded: dict[str, int] = {}
        for table in load_order:
            if table not in clean_frames:
                log.debug("  Table '%s' has no data — skipping.", table)
                continue
            df = clean_frames[table]
            df.to_sql(table, conn, if_exists="append", index=False)
            rows_loaded[table] = len(df)
            log.info("  ✓ Loaded %d rows into '%s'.", len(df), table)

        conn.commit()

        # ── FK integrity double-check ──────────────────────────────────────────
        fk_violations = conn.execute("PRAGMA foreign_key_check;").fetchall()
        if not fk_violations:
            log.info("  [OK] Foreign Key integrity check passed.")
        else:
            log.error(
                "  [FAIL] %d FK violations detected after load!", len(fk_violations)
            )
            for v in fk_violations[:10]:  # Log first 10 to avoid spam
                log.error("    %s", v)

        # ── KPI summary ───────────────────────────────────────────────────────
        log.info("\nSAMPLE KPIs:")
        row = conn.execute("""
            SELECT
                COUNT(DISTINCT SalesOrderNumber) AS orders,
                SUM(Quantity)                    AS items,
                SUM(Sales)                       AS revenue,
                SUM(Cost)                        AS cost
            FROM sales;
        """).fetchone()
        if row and row[0]:
            log.info("  Total Unique Orders : %s", f"{row[0]:,}")
            log.info("  Total Items Sold    : %s", f"{row[1]:,}")
            log.info("  Gross Revenue       : $%s", f"{row[2]:,.2f}")
            log.info("  Total Cost          : $%s", f"{row[3]:,.2f}")

    finally:
        conn.close()

    # ── Update pipeline state ──────────────────────────────────────────────────
    new_state = {}
    for table, df in clean_frames.items():
        new_state[table] = {"row_count": len(df), "last_run": datetime.now().isoformat()}
    _save_pipeline_state(new_state)

    # ── Final summary table ────────────────────────────────────────────────────
    duration = time.time() - pipeline_start
    log.info("\n" + "=" * 60)
    log.info("PIPELINE SUMMARY (%.2fs)", duration)
    log.info("%-30s %-12s %-10s %s", "File", "Status", "Rows", "Note")
    log.info("-" * 70)
    any_critical_failed = False
    for filename, result in file_results.items():
        status = result.get("status", "unknown")
        rows = result.get("rows_clean", result.get("rows_raw", "—"))
        note = result.get("error", "") or ""
        log.info("%-30s %-12s %-10s %s", filename, status, rows, note[:50])
        if status == "failed" and result.get("critical"):
            any_critical_failed = True
            log.error(
                "CRITICAL: '%s' failed. KPIs from 'sales' table are UNRELIABLE.", filename
            )
    log.info("=" * 60)

    if any_critical_failed:
        log.error("Pipeline exiting with code 1 — critical file failed.")
        return 1

    log.info("ETL pipeline completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(run_etl())
