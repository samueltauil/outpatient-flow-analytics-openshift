"""
ETL Batch Job: Edge DB → Central DB

Pattern B (Central pulls): Connects to edge PostgreSQL, pulls rows newer
than a stored watermark, inserts them into central DB idempotently.

Designed to run as a Kubernetes CronJob every 4 hours.
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Columns to transfer (excludes generated columns)
TRANSFER_COLUMNS = [
    "event_id", "facility_id", "procedure_type", "scheduled_start_time",
    "checkin_time", "preop_start_time", "op_start_time",
    "postop_start_time", "discharge_time", "anesthesia_type",
    "asa_class", "case_status", "created_at", "source_generator_id",
]


def get_connection(host: str, port: int, dbname: str, user: str, password: str):
    """Create a PostgreSQL connection."""
    if psycopg2 is None:
        raise ImportError("psycopg2 is required. Install with: pip install psycopg2-binary")
    return psycopg2.connect(
        host=host, port=port, dbname=dbname, user=user, password=password,
        connect_timeout=30,
    )


def get_watermark(central_conn, source_id: str) -> Optional[datetime]:
    """Get the last watermark for a given source."""
    with central_conn.cursor() as cur:
        cur.execute(
            "SELECT last_created_at FROM etl_watermark WHERE source_id = %s",
            (source_id,),
        )
        row = cur.fetchone()
        return row[0] if row else None


def update_watermark(central_conn, source_id: str, last_created_at: datetime, rows: int):
    """Update the watermark after successful transfer."""
    with central_conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO etl_watermark (source_id, last_created_at, last_run_at, rows_transferred)
            VALUES (%s, %s, NOW(), %s)
            ON CONFLICT (source_id)
            DO UPDATE SET
                last_created_at = EXCLUDED.last_created_at,
                last_run_at = NOW(),
                rows_transferred = etl_watermark.rows_transferred + EXCLUDED.rows_transferred
            """,
            (source_id, last_created_at, rows),
        )


def fetch_new_rows(edge_conn, watermark: Optional[datetime], batch_size: int = 10000):
    """Fetch rows from edge DB newer than watermark."""
    cols = ", ".join(TRANSFER_COLUMNS)
    with edge_conn.cursor(name="etl_fetch", cursor_factory=psycopg2.extras.DictCursor) as cur:
        if watermark:
            cur.execute(
                f"SELECT {cols} FROM outpatient_case_event "
                f"WHERE created_at > %s ORDER BY created_at ASC",
                (watermark,),
            )
        else:
            cur.execute(
                f"SELECT {cols} FROM outpatient_case_event ORDER BY created_at ASC"
            )
        while True:
            rows = cur.fetchmany(batch_size)
            if not rows:
                break
            yield rows


def insert_rows(central_conn, rows):
    """Insert rows into central DB idempotently."""
    if not rows:
        return 0
    cols = ", ".join(TRANSFER_COLUMNS)
    placeholders = ", ".join(["%s"] * len(TRANSFER_COLUMNS))
    query = (
        f"INSERT INTO outpatient_case_event ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT (event_id) DO NOTHING"
    )
    count = 0
    with central_conn.cursor() as cur:
        for row in rows:
            values = [row[col] for col in TRANSFER_COLUMNS]
            cur.execute(query, values)
            count += cur.rowcount
    return count


def run_etl(
    edge_host: str, edge_port: int, edge_db: str, edge_user: str, edge_pass: str,
    central_host: str, central_port: int, central_db: str, central_user: str, central_pass: str,
    source_id: str = "edge-collector",
    batch_size: int = 10000,
):
    """Execute one ETL cycle: pull from edge, push to central."""
    start_time = time.time()

    logger.info("Connecting to edge DB at %s:%d/%s", edge_host, edge_port, edge_db)
    edge_conn = get_connection(edge_host, edge_port, edge_db, edge_user, edge_pass)

    logger.info("Connecting to central DB at %s:%d/%s", central_host, central_port, central_db)
    central_conn = get_connection(central_host, central_port, central_db, central_user, central_pass)

    try:
        watermark = get_watermark(central_conn, source_id)
        logger.info("Current watermark for %s: %s", source_id, watermark)

        total_rows = 0
        last_created = watermark

        for batch in fetch_new_rows(edge_conn, watermark, batch_size):
            inserted = insert_rows(central_conn, batch)
            total_rows += inserted
            if batch:
                last_created = batch[-1]["created_at"]
            central_conn.commit()
            logger.info("Batch inserted: %d rows (total: %d)", inserted, total_rows)

        if total_rows > 0 and last_created:
            update_watermark(central_conn, source_id, last_created, total_rows)
            central_conn.commit()

        elapsed = time.time() - start_time
        logger.info(
            "ETL complete: %d rows transferred in %.1fs (source: %s)",
            total_rows, elapsed, source_id,
        )
        return total_rows

    finally:
        edge_conn.close()
        central_conn.close()


def main():
    parser = argparse.ArgumentParser(description="ETL: Edge DB → Central DB")
    # Edge DB config
    parser.add_argument("--edge-host", default=os.getenv("EDGE_DB_HOST", "localhost"))
    parser.add_argument("--edge-port", type=int, default=int(os.getenv("EDGE_DB_PORT", "5432")))
    parser.add_argument("--edge-db", default=os.getenv("EDGE_DB_NAME", "edge_collector"))
    parser.add_argument("--edge-user", default=os.getenv("EDGE_DB_USER", "postgres"))
    parser.add_argument("--edge-pass", default=os.getenv("EDGE_DB_PASSWORD", "postgres"))
    # Central DB config
    parser.add_argument("--central-host", default=os.getenv("CENTRAL_DB_HOST", "localhost"))
    parser.add_argument("--central-port", type=int, default=int(os.getenv("CENTRAL_DB_PORT", "5433")))
    parser.add_argument("--central-db", default=os.getenv("CENTRAL_DB_NAME", "central_analytics"))
    parser.add_argument("--central-user", default=os.getenv("CENTRAL_DB_USER", "postgres"))
    parser.add_argument("--central-pass", default=os.getenv("CENTRAL_DB_PASSWORD", "postgres"))
    # ETL config
    parser.add_argument("--source-id", default="edge-collector")
    parser.add_argument("--batch-size", type=int, default=10000)

    args = parser.parse_args()
    run_etl(
        args.edge_host, args.edge_port, args.edge_db, args.edge_user, args.edge_pass,
        args.central_host, args.central_port, args.central_db, args.central_user, args.central_pass,
        args.source_id, args.batch_size,
    )


if __name__ == "__main__":
    main()
