"""
Synthetic Outpatient Case Event Generator

Generates realistic outpatient surgical case events with:
- Facility-specific procedure mix biases
- Daily volume curves (peak morning check-ins)
- Log-normal duration distributions per procedure type
- Rare event injection (cancellations, delays, conversions)
- Idempotent UUIDs for ETL safety
"""

import argparse
import csv
import json
import logging
import math
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from .catalog import (
    ANESTHESIA_TYPES,
    FACILITIES,
    PROCEDURES,
    ProcedureDef,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Hourly check-in probability weights (hour 0-23)
# Peak check-ins between 6am-10am, tapering through afternoon
CHECKIN_HOUR_WEIGHTS = [
    0.0, 0.0, 0.0, 0.0, 0.0, 0.5,   # 0-5
    3.0, 5.0, 5.0, 4.0, 3.0, 2.5,    # 6-11
    2.0, 2.0, 1.5, 1.0, 0.5, 0.2,    # 12-17
    0.0, 0.0, 0.0, 0.0, 0.0, 0.0,    # 18-23
]


def _weighted_choice(items: list, weights: list, rng: random.Random):
    """Weighted random selection."""
    total = sum(weights)
    r = rng.random() * total
    cumulative = 0.0
    for item, w in zip(items, weights):
        cumulative += w
        if r <= cumulative:
            return item
    return items[-1]


def _sample_lognormal(mu: float, sigma: float, rng: random.Random,
                      min_val: float = 3.0, max_val: float = 600.0) -> float:
    """Sample from log-normal distribution, clamped to [min_val, max_val] minutes."""
    val = math.exp(rng.gauss(mu, sigma))
    return max(min_val, min(val, max_val))


def _build_procedure_weights(facility_id: str) -> Tuple[List[ProcedureDef], List[float]]:
    """Build weighted procedure list based on facility bias."""
    facility = FACILITIES[facility_id]
    bias = facility.get("bias", {})
    procs = []
    weights = []
    for p in PROCEDURES:
        procs.append(p)
        w = bias.get(p.service_line, 1.0)
        weights.append(w)
    return procs, weights


def _pick_anesthesia(service_line: str, rng: random.Random) -> str:
    """Pick anesthesia type based on service line weights."""
    choices = ANESTHESIA_TYPES.get(service_line, [("General", 1.0)])
    types, weights = zip(*choices)
    return _weighted_choice(list(types), list(weights), rng)


def generate_case(
    facility_id: str,
    base_date: datetime,
    procedure: ProcedureDef,
    rng: random.Random,
    generator_id: str = "gen-v1",
) -> Optional[Dict]:
    """Generate a single outpatient case event."""

    # Pick check-in hour based on hourly distribution
    hour = _weighted_choice(list(range(24)), CHECKIN_HOUR_WEIGHTS, rng)
    minute = rng.randint(0, 59)
    second = rng.randint(0, 59)

    checkin_time = base_date.replace(hour=hour, minute=minute, second=second, microsecond=0)

    # Generate durations
    d1 = _sample_lognormal(*procedure.checkin_to_preop, rng)
    d2 = _sample_lognormal(*procedure.preop_to_op, rng)
    d3 = _sample_lognormal(*procedure.op_to_postop, rng)
    d4 = _sample_lognormal(*procedure.postop_to_discharge, rng)

    preop_start = checkin_time + timedelta(minutes=d1)
    op_start = preop_start + timedelta(minutes=d2)
    postop_start = op_start + timedelta(minutes=d3)
    discharge_time = postop_start + timedelta(minutes=d4)

    # Scheduled start (op_start ± some variance)
    schedule_offset = rng.gauss(0, 10)  # minutes early/late
    scheduled_start = op_start - timedelta(minutes=schedule_offset)

    # Case status with rare events
    status_roll = rng.random()
    if status_roll < 0.02:
        case_status = "canceled"
        # Canceled cases: only have checkin and maybe preop
        preop_start = checkin_time + timedelta(minutes=rng.uniform(5, 20))
        op_start = preop_start  # same as preop for canceled
        postop_start = op_start
        discharge_time = preop_start + timedelta(minutes=rng.uniform(10, 30))
    elif status_roll < 0.03:
        case_status = "converted_to_inpatient"
        # Extended postop
        d4_extended = d4 * rng.uniform(2.0, 5.0)
        discharge_time = postop_start + timedelta(minutes=d4_extended)
    elif status_roll < 0.06:
        case_status = "delayed"
        # Add delay to op_start
        delay = rng.uniform(15, 90)
        op_start = op_start + timedelta(minutes=delay)
        postop_start = op_start + timedelta(minutes=d3)
        discharge_time = postop_start + timedelta(minutes=d4)
    else:
        case_status = "completed"

    # ASA class (1-4 typical, 5-6 rare)
    asa_weights = [0.15, 0.40, 0.30, 0.12, 0.02, 0.01]
    asa_class = _weighted_choice([1, 2, 3, 4, 5, 6], asa_weights, rng)

    anesthesia_type = _pick_anesthesia(procedure.service_line, rng)

    # Deterministic UUID from rng for reproducibility
    event_uuid = uuid.UUID(int=rng.getrandbits(128), version=4)

    return {
        "event_id": str(event_uuid),
        "facility_id": facility_id,
        "procedure_type": procedure.procedure_type,
        "scheduled_start_time": scheduled_start.isoformat(),
        "checkin_time": checkin_time.isoformat(),
        "preop_start_time": preop_start.isoformat(),
        "op_start_time": op_start.isoformat(),
        "postop_start_time": postop_start.isoformat(),
        "discharge_time": discharge_time.isoformat(),
        "anesthesia_type": anesthesia_type,
        "asa_class": asa_class,
        "case_status": case_status,
        "source_generator_id": generator_id,
    }


def generate_day(
    facility_id: str,
    date: datetime,
    rng: random.Random,
    generator_id: str = "gen-v1",
) -> List[Dict]:
    """Generate all cases for a facility on a given day."""
    facility = FACILITIES[facility_id]
    vol_min, vol_max = facility["daily_volume"]
    num_cases = rng.randint(vol_min, vol_max)

    procs, weights = _build_procedure_weights(facility_id)
    cases = []
    for _ in range(num_cases):
        proc = _weighted_choice(procs, weights, rng)
        case = generate_case(facility_id, date, proc, rng, generator_id)
        if case:
            cases.append(case)
    return cases


def generate_batch(
    start_date: datetime,
    end_date: datetime,
    seed: int = 42,
    generator_id: str = "gen-v1",
) -> List[Dict]:
    """Generate cases for all facilities over a date range."""
    rng = random.Random(seed)
    all_cases = []
    current = start_date
    while current <= end_date:
        # Skip weekends (most ASCs closed)
        if current.weekday() < 5:
            for facility_id in FACILITIES:
                day_cases = generate_day(facility_id, current, rng, generator_id)
                all_cases.append(day_cases)
                logger.info(
                    "Generated %d cases for %s on %s",
                    len(day_cases), facility_id, current.strftime("%Y-%m-%d"),
                )
        current += timedelta(days=1)
    # Flatten
    flat = [c for day in all_cases for c in day]
    logger.info("Total cases generated: %d", len(flat))
    return flat


def write_csv(cases: List[Dict], output_path: str):
    """Write cases to CSV file."""
    if not cases:
        logger.warning("No cases to write")
        return
    fieldnames = [
        "event_id", "facility_id", "procedure_type", "scheduled_start_time",
        "checkin_time", "preop_start_time", "op_start_time",
        "postop_start_time", "discharge_time", "anesthesia_type",
        "asa_class", "case_status", "source_generator_id",
    ]
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(cases)
    logger.info("Wrote %d cases to %s", len(cases), output_path)


def write_json(cases: List[Dict], output_path: str):
    """Write cases to JSON file."""
    with open(output_path, "w") as f:
        json.dump(cases, f, indent=2, default=str)
    logger.info("Wrote %d cases to %s", len(cases), output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic outpatient case events"
    )
    parser.add_argument(
        "--start-date", type=str, default="2025-01-06",
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date", type=str, default="2025-03-31",
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument(
        "--output", type=str, default="output/cases.csv",
        help="Output file path (.csv or .json)",
    )
    parser.add_argument(
        "--format", choices=["csv", "json"], default="csv",
        help="Output format",
    )
    parser.add_argument(
        "--generator-id", type=str, default="gen-v1",
        help="Generator identifier for traceability",
    )

    args = parser.parse_args()

    start = datetime.strptime(args.start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(args.end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    cases = generate_batch(start, end, seed=args.seed, generator_id=args.generator_id)

    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)

    if args.format == "json":
        write_json(cases, args.output)
    else:
        write_csv(cases, args.output)


if __name__ == "__main__":
    main()
