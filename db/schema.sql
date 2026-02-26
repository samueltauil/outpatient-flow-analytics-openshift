-- =============================================================================
-- Edge & Central PostgreSQL Schema
-- Synthetic Outpatient Flow Analytics Demo
-- =============================================================================

-- Facility dimension table
CREATE TABLE IF NOT EXISTS facility (
    facility_id     VARCHAR(20) PRIMARY KEY,
    facility_name   VARCHAR(100) NOT NULL,
    timezone        VARCHAR(50) DEFAULT 'America/New_York',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Procedure catalog dimension table
CREATE TABLE IF NOT EXISTS procedure_catalog (
    procedure_type          VARCHAR(100) PRIMARY KEY,
    service_line            VARCHAR(50) NOT NULL,
    -- Duration distribution parameters (minutes, log-normal: mu, sigma)
    checkin_to_preop_mu     DOUBLE PRECISION DEFAULT 3.0,
    checkin_to_preop_sigma  DOUBLE PRECISION DEFAULT 0.4,
    preop_to_op_mu          DOUBLE PRECISION DEFAULT 3.2,
    preop_to_op_sigma       DOUBLE PRECISION DEFAULT 0.3,
    op_to_postop_mu         DOUBLE PRECISION DEFAULT 3.5,
    op_to_postop_sigma      DOUBLE PRECISION DEFAULT 0.4,
    postop_to_discharge_mu  DOUBLE PRECISION DEFAULT 3.8,
    postop_to_discharge_sigma DOUBLE PRECISION DEFAULT 0.4,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- Main fact table: outpatient case events
CREATE TABLE IF NOT EXISTS outpatient_case_event (
    event_id                UUID PRIMARY KEY,
    facility_id             VARCHAR(20) NOT NULL REFERENCES facility(facility_id),
    procedure_type          VARCHAR(100) NOT NULL REFERENCES procedure_catalog(procedure_type),
    scheduled_start_time    TIMESTAMPTZ,
    checkin_time            TIMESTAMPTZ NOT NULL,
    preop_start_time        TIMESTAMPTZ NOT NULL,
    op_start_time           TIMESTAMPTZ NOT NULL,
    postop_start_time       TIMESTAMPTZ NOT NULL,
    discharge_time          TIMESTAMPTZ NOT NULL,
    anesthesia_type         VARCHAR(30),
    asa_class               SMALLINT CHECK (asa_class BETWEEN 1 AND 6),
    case_status             VARCHAR(30) DEFAULT 'completed'
                            CHECK (case_status IN ('completed', 'canceled', 'converted_to_inpatient', 'delayed')),
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    source_generator_id     VARCHAR(50),

    -- Derived duration columns (minutes) for analytics convenience
    dur_checkin_to_preop    DOUBLE PRECISION GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (preop_start_time - checkin_time)) / 60.0
    ) STORED,
    dur_preop_to_op         DOUBLE PRECISION GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (op_start_time - preop_start_time)) / 60.0
    ) STORED,
    dur_op_to_postop        DOUBLE PRECISION GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (postop_start_time - op_start_time)) / 60.0
    ) STORED,
    dur_postop_to_discharge DOUBLE PRECISION GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (discharge_time - postop_start_time)) / 60.0
    ) STORED,
    dur_total               DOUBLE PRECISION GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (discharge_time - checkin_time)) / 60.0
    ) STORED
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_case_event_facility
    ON outpatient_case_event (facility_id);
CREATE INDEX IF NOT EXISTS idx_case_event_procedure
    ON outpatient_case_event (procedure_type);
CREATE INDEX IF NOT EXISTS idx_case_event_checkin
    ON outpatient_case_event (checkin_time);
CREATE INDEX IF NOT EXISTS idx_case_event_created
    ON outpatient_case_event (created_at);
CREATE INDEX IF NOT EXISTS idx_case_event_status
    ON outpatient_case_event (case_status);

-- ETL watermark tracking (central DB only)
CREATE TABLE IF NOT EXISTS etl_watermark (
    source_id       VARCHAR(50) PRIMARY KEY,
    last_created_at TIMESTAMPTZ NOT NULL,
    last_run_at     TIMESTAMPTZ DEFAULT NOW(),
    rows_transferred BIGINT DEFAULT 0
);
