"""Tests for ETL batch job logic (unit tests without actual DB connections)."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from src.etl.batch_etl import TRANSFER_COLUMNS


class TestETLConfig:
    def test_transfer_columns_defined(self):
        assert len(TRANSFER_COLUMNS) > 0
        assert "event_id" in TRANSFER_COLUMNS
        assert "facility_id" in TRANSFER_COLUMNS
        assert "procedure_type" in TRANSFER_COLUMNS
        assert "checkin_time" in TRANSFER_COLUMNS
        assert "created_at" in TRANSFER_COLUMNS
        assert "source_generator_id" in TRANSFER_COLUMNS

    def test_no_generated_columns_in_transfer(self):
        """Generated columns should not be in transfer list."""
        generated = ["dur_checkin_to_preop", "dur_preop_to_op",
                      "dur_op_to_postop", "dur_postop_to_discharge", "dur_total"]
        for col in generated:
            assert col not in TRANSFER_COLUMNS, f"Generated column {col} should not be transferred"


class TestETLWatermark:
    @patch("src.etl.batch_etl.psycopg2")
    def test_get_watermark_returns_none_for_new_source(self, mock_pg):
        from src.etl.batch_etl import get_watermark
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        result = get_watermark(mock_conn, "test-source")
        assert result is None

    @patch("src.etl.batch_etl.psycopg2")
    def test_get_watermark_returns_timestamp(self, mock_pg):
        from src.etl.batch_etl import get_watermark
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        ts = datetime(2025, 1, 6, 12, 0, 0, tzinfo=timezone.utc)
        mock_cursor.fetchone.return_value = (ts,)
        mock_conn.cursor.return_value.__enter__ = lambda s: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        result = get_watermark(mock_conn, "test-source")
        assert result == ts
