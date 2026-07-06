"""
config.py — Loads config.yaml and exposes a typed, importable CFG object.

Why a module instead of calling yaml.safe_load() in the main script?
- Centralises the load-once-fail-fast pattern: if config.yaml is missing
  or malformed, you get a clear ImportError at startup, not a KeyError
  somewhere deep in the pipeline.
- Makes every other module do `from config import CFG` — one import, no path juggling.
"""
import os
import yaml

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_THIS_DIR, "config.yaml")


def _load() -> dict:
    if not os.path.exists(_CONFIG_PATH):
        raise FileNotFoundError(
            f"config.yaml not found at {_CONFIG_PATH}. "
            "Create it from config.yaml before running the pipeline."
        )
    with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data


CFG: dict = _load()

# --- Convenience accessors (avoids CFG["paths"]["db_path"] everywhere) ---
DATASET_DIR: str = os.path.join(_THIS_DIR, CFG["paths"]["dataset_dir"])
DB_PATH: str = os.path.join(_THIS_DIR, CFG["paths"]["db_path"])
LOGS_DIR: str = os.path.join(_THIS_DIR, CFG["paths"]["logs_dir"])
REJECTED_DIR: str = os.path.join(_THIS_DIR, CFG["paths"]["rejected_rows_dir"])
STATE_FILE: str = os.path.join(_THIS_DIR, CFG["paths"]["state_file"])
SCHEMA_FILE: str = os.path.join(_THIS_DIR, CFG["paths"]["schema_file"])
SCHEMA_VERSION: int = int(CFG["schema_version"])

FILES: dict = CFG["files"]
COLUMN_RENAMES: dict = CFG.get("column_renames", {})
CURRENCY_COLUMNS: dict = CFG.get("currency_columns", {})
DATE_COLUMNS: dict = CFG.get("date_columns", {})
VALIDATION: dict = CFG.get("validation", {})
