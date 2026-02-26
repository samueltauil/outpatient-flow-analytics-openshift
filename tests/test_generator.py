"""Tests for the synthetic data generator."""

import pytest
import random
from datetime import datetime, timezone, timedelta

from src.generator.catalog import PROCEDURES, FACILITIES
from src.generator.generate import (
    generate_case,
    generate_day,
    generate_batch,
    write_csv,
    write_json,
    _sample_lognormal,
    _weighted_choice,
    _build_procedure_weights,
)


class TestHelpers:
    def test_weighted_choice_returns_valid_item(self):
        rng = random.Random(42)
        items = ["a", "b", "c"]
        weights = [1.0, 2.0, 3.0]
        for _ in range(100):
            result = _weighted_choice(items, weights, rng)
            assert result in items

    def test_weighted_choice_respects_weights(self):
        rng = random.Random(42)
        items = ["a", "b"]
        weights = [0.0, 1.0]
        for _ in range(50):
            assert _weighted_choice(items, weights, rng) == "b"

    def test_sample_lognormal_within_bounds(self):
        rng = random.Random(42)
        for _ in range(100):
            val = _sample_lognormal(3.0, 0.4, rng, min_val=3.0, max_val=600.0)
            assert 3.0 <= val <= 600.0

    def test_build_procedure_weights(self):
        procs, weights = _build_procedure_weights("HOSP_A")
        assert len(procs) == len(PROCEDURES)
        assert len(weights) == len(PROCEDURES)
        # HOSP_A biases GI, so GI procedures should have weight > 1
        gi_indices = [i for i, p in enumerate(procs) if p.service_line == "GI"]
        assert all(weights[i] > 1.0 for i in gi_indices)


class TestGenerateCase:
    def test_returns_dict_with_required_fields(self):
        rng = random.Random(42)
        proc = PROCEDURES[0]
        base = datetime(2025, 1, 6, tzinfo=timezone.utc)
        case = generate_case("HOSP_A", base, proc, rng)

        required_fields = [
            "event_id", "facility_id", "procedure_type",
            "checkin_time", "preop_start_time", "op_start_time",
            "postop_start_time", "discharge_time",
            "anesthesia_type", "asa_class", "case_status",
            "source_generator_id",
        ]
        for field in required_fields:
            assert field in case, f"Missing field: {field}"

    def test_timestamps_are_ordered(self):
        rng = random.Random(42)
        proc = PROCEDURES[0]
        base = datetime(2025, 1, 6, tzinfo=timezone.utc)
        # Generate many cases and check ordering for completed ones
        for seed in range(100):
            rng = random.Random(seed)
            case = generate_case("HOSP_A", base, proc, rng)
            if case["case_status"] == "completed":
                times = [
                    case["checkin_time"],
                    case["preop_start_time"],
                    case["op_start_time"],
                    case["postop_start_time"],
                    case["discharge_time"],
                ]
                for i in range(len(times) - 1):
                    assert times[i] <= times[i + 1], (
                        f"Timestamps not ordered: {times[i]} > {times[i + 1]} (seed={seed})"
                    )

    def test_case_status_values(self):
        rng = random.Random(42)
        proc = PROCEDURES[0]
        base = datetime(2025, 1, 6, tzinfo=timezone.utc)
        statuses = set()
        for seed in range(500):
            rng = random.Random(seed)
            case = generate_case("HOSP_A", base, proc, rng)
            statuses.add(case["case_status"])
        # Should see at least completed and one other status
        assert "completed" in statuses
        valid = {"completed", "canceled", "converted_to_inpatient", "delayed"}
        assert statuses.issubset(valid)

    def test_asa_class_in_range(self):
        rng = random.Random(42)
        proc = PROCEDURES[0]
        base = datetime(2025, 1, 6, tzinfo=timezone.utc)
        for _ in range(100):
            case = generate_case("HOSP_A", base, proc, rng)
            assert 1 <= case["asa_class"] <= 6


class TestGenerateDay:
    def test_generates_expected_volume(self):
        rng = random.Random(42)
        base = datetime(2025, 1, 6, tzinfo=timezone.utc)
        cases = generate_day("HOSP_A", base, rng)
        vol_min, vol_max = FACILITIES["HOSP_A"]["daily_volume"]
        assert vol_min <= len(cases) <= vol_max

    def test_all_cases_have_same_facility(self):
        rng = random.Random(42)
        base = datetime(2025, 1, 6, tzinfo=timezone.utc)
        cases = generate_day("HOSP_B", base, rng)
        assert all(c["facility_id"] == "HOSP_B" for c in cases)


class TestGenerateBatch:
    def test_batch_generation(self):
        start = datetime(2025, 1, 6, tzinfo=timezone.utc)
        end = datetime(2025, 1, 10, tzinfo=timezone.utc)  # Mon-Fri
        cases = generate_batch(start, end, seed=42)
        assert len(cases) > 0
        # 5 weekdays × 3 facilities × ~50-100 cases each
        assert len(cases) >= 5 * 3 * 40

    def test_reproducibility(self):
        start = datetime(2025, 1, 6, tzinfo=timezone.utc)
        end = datetime(2025, 1, 8, tzinfo=timezone.utc)
        cases1 = generate_batch(start, end, seed=42)
        cases2 = generate_batch(start, end, seed=42)
        assert len(cases1) == len(cases2)
        assert cases1[0]["event_id"] == cases2[0]["event_id"]

    def test_skips_weekends(self):
        # Jan 11-12, 2025 are Sat-Sun
        start = datetime(2025, 1, 11, tzinfo=timezone.utc)
        end = datetime(2025, 1, 12, tzinfo=timezone.utc)
        cases = generate_batch(start, end, seed=42)
        assert len(cases) == 0


class TestWriteOutput:
    def test_write_csv(self, tmp_path):
        rng = random.Random(42)
        proc = PROCEDURES[0]
        base = datetime(2025, 1, 6, tzinfo=timezone.utc)
        cases = [generate_case("HOSP_A", base, proc, rng) for _ in range(10)]
        path = str(tmp_path / "test.csv")
        write_csv(cases, path)
        import csv
        with open(path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 10

    def test_write_json(self, tmp_path):
        rng = random.Random(42)
        proc = PROCEDURES[0]
        base = datetime(2025, 1, 6, tzinfo=timezone.utc)
        cases = [generate_case("HOSP_A", base, proc, rng) for _ in range(10)]
        path = str(tmp_path / "test.json")
        write_json(cases, path)
        import json
        with open(path) as f:
            data = json.load(f)
        assert len(data) == 10
