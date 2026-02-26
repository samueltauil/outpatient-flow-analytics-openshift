"""Tests for the procedure catalog."""

import pytest
from src.generator.catalog import (
    ANESTHESIA_TYPES,
    FACILITIES,
    PROCEDURES,
    SERVICE_LINES,
    ProcedureDef,
    get_procedures_by_service_line,
)


class TestProcedureCatalog:
    def test_minimum_procedure_count(self):
        """Plan requires >= 50 procedure types."""
        assert len(PROCEDURES) >= 50

    def test_all_procedures_have_valid_service_lines(self):
        for p in PROCEDURES:
            assert p.service_line in SERVICE_LINES, f"{p.procedure_type} has unknown service_line: {p.service_line}"

    def test_all_service_lines_have_anesthesia_types(self):
        for sl in SERVICE_LINES:
            assert sl in ANESTHESIA_TYPES, f"Missing anesthesia types for {sl}"

    def test_anesthesia_weights_sum_to_one(self):
        for sl, choices in ANESTHESIA_TYPES.items():
            total = sum(w for _, w in choices)
            assert abs(total - 1.0) < 0.01, f"{sl} anesthesia weights sum to {total}"

    def test_duration_parameters_are_positive(self):
        for p in PROCEDURES:
            for name, (mu, sigma) in [
                ("checkin_to_preop", p.checkin_to_preop),
                ("preop_to_op", p.preop_to_op),
                ("op_to_postop", p.op_to_postop),
                ("postop_to_discharge", p.postop_to_discharge),
            ]:
                assert mu > 0, f"{p.procedure_type}.{name} mu={mu} must be positive"
                assert sigma > 0, f"{p.procedure_type}.{name} sigma={sigma} must be positive"

    def test_unique_procedure_names(self):
        names = [p.procedure_type for p in PROCEDURES]
        assert len(names) == len(set(names)), "Duplicate procedure names found"

    def test_facilities_defined(self):
        assert len(FACILITIES) == 3
        for fid, fac in FACILITIES.items():
            assert "name" in fac
            assert "timezone" in fac
            assert "daily_volume" in fac
            vol_min, vol_max = fac["daily_volume"]
            assert vol_min > 0
            assert vol_max >= vol_min

    def test_get_procedures_by_service_line(self):
        gi_procs = get_procedures_by_service_line("GI")
        assert len(gi_procs) >= 5
        assert all(p.service_line == "GI" for p in gi_procs)

    def test_service_line_coverage(self):
        """Ensure we have procedures across many service lines."""
        assert len(SERVICE_LINES) >= 8
