"""
tests/test_transforms.py

Unit tests for the ETL transform helper functions.
Each test covers normal cases, edge cases, nulls, and malformed input.

Run with:  pytest -v
"""
import math
import sys
import os

import pandas as pd
import pytest

# Make the project root importable from the tests/ folder
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from etl_pipeline import clean_currency, clean_dates


# ──────────────────────────────────────────────────────────────────────────────
#  clean_currency() tests
# ──────────────────────────────────────────────────────────────────────────────

class TestCleanCurrency:

    def _make_df(self, values):
        return pd.DataFrame({"Amount": values})

    def test_normal_dollar_with_commas(self):
        """Standard currency strings like '$4,049.98' should become 4049.98."""
        df = self._make_df(["$4,049.98", "$57.68", "$1,000,000.00"])
        result = clean_currency(df, ["Amount"])
        assert list(result["Amount"]) == [4049.98, 57.68, 1_000_000.00]

    def test_already_numeric_string(self):
        """If a value has no $ or comma, it should still parse correctly."""
        df = self._make_df(["100.50", "0.99", "250"])
        result = clean_currency(df, ["Amount"])
        assert list(result["Amount"]) == [100.50, 0.99, 250.0]

    def test_zero_value(self):
        """$0.00 should become 0.0, not NaN or None."""
        df = self._make_df(["$0.00"])
        result = clean_currency(df, ["Amount"])
        assert result["Amount"].iloc[0] == 0.0

    def test_null_becomes_nan(self):
        """None / missing values should become NaN, not raise an error."""
        df = self._make_df([None, "$10.00"])
        result = clean_currency(df, ["Amount"])
        assert math.isnan(result["Amount"].iloc[0])
        assert result["Amount"].iloc[1] == 10.00

    def test_empty_string_becomes_nan(self):
        """Empty strings should become NaN."""
        df = self._make_df(["", "$5.00"])
        result = clean_currency(df, ["Amount"])
        assert math.isnan(result["Amount"].iloc[0])

    def test_malformed_string_becomes_nan(self):
        """Non-numeric strings (e.g. 'N/A') should become NaN, not crash."""
        df = self._make_df(["N/A", "$20.00"])
        result = clean_currency(df, ["Amount"])
        assert math.isnan(result["Amount"].iloc[0])

    def test_missing_column_does_not_crash(self):
        """Passing a column name that doesn't exist should log a warning, not raise."""
        df = pd.DataFrame({"Other": ["$1.00"]})
        result = clean_currency(df, ["NonExistentColumn"])
        assert "NonExistentColumn" not in result.columns  # No crash, column unchanged

    def test_multiple_columns(self):
        """Multiple currency columns should all be cleaned in one call."""
        df = pd.DataFrame({"Sales": ["$1,000.00"], "Cost": ["$800.50"]})
        result = clean_currency(df, ["Sales", "Cost"])
        assert result["Sales"].iloc[0] == 1000.00
        assert result["Cost"].iloc[0] == 800.50


# ──────────────────────────────────────────────────────────────────────────────
#  clean_dates() tests
# ──────────────────────────────────────────────────────────────────────────────

class TestCleanDates:

    def _make_df(self, values):
        return pd.DataFrame({"OrderDate": values})

    def test_long_form_date(self):
        """'Friday, August 25, 2017' should parse to '2017-08-25'."""
        df = self._make_df(["Friday, August 25, 2017"])
        result = clean_dates(df, ["OrderDate"])
        assert result["OrderDate"].iloc[0] == "2017-08-25"

    def test_already_iso_date(self):
        """Already-clean ISO dates should remain unchanged."""
        df = self._make_df(["2017-08-25"])
        result = clean_dates(df, ["OrderDate"])
        assert result["OrderDate"].iloc[0] == "2017-08-25"

    def test_multiple_date_formats(self):
        """Mix of long-form and ISO dates in the same column should both parse correctly.
        The clean_dates function uses format='mixed' so both styles coexist."""
        df = self._make_df(["Friday, August 25, 2017", "2018-01-15"])
        result = clean_dates(df, ["OrderDate"])
        assert result["OrderDate"].iloc[0] == "2017-08-25"
        assert result["OrderDate"].iloc[1] == "2018-01-15"

    def test_null_becomes_nat(self):
        """None values should become NaT (null), represented as None after strftime."""
        df = self._make_df([None, "2017-08-25"])
        result = clean_dates(df, ["OrderDate"])
        assert result["OrderDate"].iloc[0] is None or result["OrderDate"].iloc[0] != result["OrderDate"].iloc[0]  # NaN check

    def test_malformed_date_becomes_null(self):
        """Unparseable strings should become null, not crash."""
        df = self._make_df(["not-a-date"])
        result = clean_dates(df, ["OrderDate"])
        # Should be NaT / NaN, not 'not-a-date'
        assert result["OrderDate"].iloc[0] != "not-a-date"

    def test_missing_column_does_not_crash(self):
        """Passing a column that doesn't exist should log a warning, not raise."""
        df = pd.DataFrame({"Other": ["something"]})
        result = clean_dates(df, ["NonExistentDate"])
        assert "NonExistentDate" not in result.columns

    def test_first_of_month_date(self):
        """'Saturday, July 1, 2017' should parse to '2017-07-01' (zero-padded day)."""
        df = self._make_df(["Saturday, July 1, 2017"])
        result = clean_dates(df, ["OrderDate"])
        assert result["OrderDate"].iloc[0] == "2017-07-01"
