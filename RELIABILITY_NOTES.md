# RELIABILITY_NOTES.md

## What Failure Modes Existed Before (and What Was Fixed)

| # | Failure Mode | Risk | Fix |
|---|---|---|---|
| 1 | Hardcoded paths — pipeline only worked on one machine | High | config.yaml + config.py module |
| 2 | print() only — no trace after a run | High | logging module: INFO to console, DEBUG to logs/pipeline_YYYY-MM-DD.log |
| 3 | One try/except for all files — one bad CSV kills everything | High | Per-file isolated try/except; critical file detection exits code 1 |
| 4 | No validation — bad data silently loaded into DB | Critical | PK/null/negative/FK checks; rejects quarantined to rejected_rows/ |
| 5 | Non-idempotent — running twice duplicates all rows | High | Truncate-then-reload in a single SQLite transaction |
| 6 | DDL baked into Python — schema drift invisible | Medium | schema.sql + schema_version table; DDL only applied when version changes |
| 7 | No tests — breaking changes undetectable | High | pytest: 8 unit tests + 9 integration tests against fixture data |
| 8 | Windows encoding bug — unicode crashed on cp1252 console | Low | sys.stdout.reconfigure(encoding='utf-8') at startup |

---

## Key Design Decisions and Tradeoffs

### Why Truncate-Reload Instead of Upsert (Task 5)
- SQLite INSERT OR REPLACE generates new rowids (breaks audit trails).
- ON CONFLICT DO UPDATE requires explicit UNIQUE constraints on every FK column.
- Truncate is simpler, predictable, and ensures stale rows from deleted source records don't linger.
- Tradeoff: loads the full 60k rows every run (~0.7s). Revisit with CDC if dataset grows to millions.

### Why Plain Pandas for FK Checks Instead of Pandera (Task 4)
- Pandera validates a single DataFrame in isolation; cross-table FK constraints require knowledge of both tables simultaneously.
- Set subtraction (set(child[col]) - set(parent[col])) is more readable for this use case.
- Pandera is still used for single-table constraints: null checks, type coercion, and numeric ranges.

### Why pipeline_state.json Instead of a Metadata Table (Task 4)
- Readable before the DB is opened — useful when the DB itself is corrupt.
- Tradeoff: not atomic on write; a future hardening step is write-to-temp-then-rename.

### Why format='mixed' in clean_dates() (Discovered via Tests)
- Tests caught that pd.to_datetime without format='mixed' silently dropped ISO dates when
  they coexisted with long-form dates in the same column.
- format='mixed' infers the format per-row, which is the correct behavior for heterogeneous columns.

---

## How to Run Tests

    pytest -v                              # all tests
    pytest tests/test_transforms.py -v    # unit tests only
    pytest tests/test_integration.py -v   # integration tests only

---

## File Structure After Hardening

    .
    config.yaml                   # All paths and column mappings (edit this, not Python)
    config.py                     # Loads config.yaml, exposes typed constants
    etl_pipeline.py               # Main ETL script (hardened)
    schema.sql                    # Single source of truth for DB DDL
    RELIABILITY_NOTES.md          # This file
    logs/
        .gitkeep
        pipeline_YYYY-MM-DD.log   # Written every run (git-ignored)
    rejected_rows/
        .gitkeep                  # Quarantined rows written here (git-ignored)
    tests/
        __init__.py
        test_transforms.py        # 8 unit tests
        test_integration.py       # 9 integration tests
        fixtures/                 # Small CSVs for integration tests
