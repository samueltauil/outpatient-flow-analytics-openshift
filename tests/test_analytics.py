"""Tests for the analytics pipeline."""

import json
import os
import pytest
import random
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from src.generator.catalog import PROCEDURES
from src.generator.generate import generate_batch


@pytest.fixture(scope="module")
def sample_cases():
    """Generate a small dataset for analytics testing."""
    start = datetime(2025, 1, 6, tzinfo=timezone.utc)
    end = datetime(2025, 1, 17, tzinfo=timezone.utc)
    return generate_batch(start, end, seed=42)


@pytest.fixture(scope="module")
def sample_df(sample_cases):
    """Create a DataFrame from sample cases."""
    df = pd.DataFrame(sample_cases)
    for col in ["checkin_time", "preop_start_time", "op_start_time",
                 "postop_start_time", "discharge_time", "scheduled_start_time"]:
        df[col] = pd.to_datetime(df[col])
    return df


class TestComputeDurations:
    def test_computes_duration_columns(self, sample_df):
        from src.analytics.analytics import compute_durations
        df = compute_durations(sample_df.copy())
        for col in ["dur_checkin_to_preop", "dur_preop_to_op",
                     "dur_op_to_postop", "dur_postop_to_discharge", "dur_total"]:
            assert col in df.columns
            # Completed cases should have positive durations
            completed = df[df["case_status"] == "completed"]
            assert (completed[col] > 0).all(), f"Non-positive values in {col}"

    def test_dur_total_equals_sum(self, sample_df):
        from src.analytics.analytics import compute_durations
        df = compute_durations(sample_df.copy())
        completed = df[df["case_status"] == "completed"]
        sum_parts = (
            completed["dur_checkin_to_preop"]
            + completed["dur_preop_to_op"]
            + completed["dur_op_to_postop"]
            + completed["dur_postop_to_discharge"]
        )
        np.testing.assert_allclose(completed["dur_total"].values, sum_parts.values, rtol=1e-5)


class TestComputeAggregates:
    def test_aggregates_structure(self, sample_df):
        from src.analytics.analytics import compute_durations, compute_aggregates
        df = compute_durations(sample_df.copy())
        aggs = compute_aggregates(df)
        assert "facility_id" in aggs.columns
        assert "procedure_type" in aggs.columns
        assert "case_volume" in aggs.columns
        assert len(aggs) > 0

    def test_late_start_rate_computed(self, sample_df):
        from src.analytics.analytics import compute_durations, compute_aggregates
        df = compute_durations(sample_df.copy())
        aggs = compute_aggregates(df)
        if "late_start_rate" in aggs.columns:
            assert aggs["late_start_rate"].between(0, 1).all()


class TestGenerateInsights:
    def test_insights_generated(self, sample_df):
        from src.analytics.analytics import compute_durations, compute_aggregates, generate_insights
        df = compute_durations(sample_df.copy())
        aggs = compute_aggregates(df)
        insights = generate_insights(df, aggs)
        assert len(insights) > 0
        # Should have at least facility summaries
        types = {i["type"] for i in insights}
        assert "facility_summary" in types

    def test_insight_messages_are_strings(self, sample_df):
        from src.analytics.analytics import compute_durations, compute_aggregates, generate_insights
        df = compute_durations(sample_df.copy())
        aggs = compute_aggregates(df)
        insights = generate_insights(df, aggs)
        for insight in insights:
            assert isinstance(insight["message"], str)
            assert len(insight["message"]) > 0


class TestRunAnalytics:
    def test_full_pipeline_csv(self, sample_cases, tmp_path):
        from src.analytics.analytics import run_analytics

        # Write sample data to CSV
        df = pd.DataFrame(sample_cases)
        csv_path = str(tmp_path / "test_cases.csv")
        df.to_csv(csv_path, index=False)

        output_dir = str(tmp_path / "analytics_output")
        results = run_analytics(csv_path, output_dir)

        assert "insights" in results
        assert len(results["insights"]) > 0
        assert os.path.exists(os.path.join(output_dir, "aggregates.csv"))
        assert os.path.exists(os.path.join(output_dir, "analytics_results.json"))

    def test_results_json_valid(self, sample_cases, tmp_path):
        from src.analytics.analytics import run_analytics

        df = pd.DataFrame(sample_cases)
        csv_path = str(tmp_path / "test_cases2.csv")
        df.to_csv(csv_path, index=False)

        output_dir = str(tmp_path / "analytics_output2")
        run_analytics(csv_path, output_dir)

        with open(os.path.join(output_dir, "analytics_results.json")) as f:
            data = json.load(f)
        assert "timestamp" in data
        assert "gpu_available" in data
        assert isinstance(data["insights"], list)
