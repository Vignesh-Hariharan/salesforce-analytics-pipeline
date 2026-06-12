CREATE DATABASE IF NOT EXISTS SALES_ANALYTICS;
USE DATABASE SALES_ANALYTICS;

CREATE SCHEMA IF NOT EXISTS OPPORTUNITIES;
USE SCHEMA OPPORTUNITIES;

CREATE WAREHOUSE IF NOT EXISTS COMPUTE_WH
    WAREHOUSE_SIZE = 'X-SMALL'
    AUTO_SUSPEND = 60
    AUTO_RESUME = TRUE
    INITIALLY_SUSPENDED = TRUE;

USE WAREHOUSE COMPUTE_WH;

CREATE TABLE IF NOT EXISTS fact_opportunities (
    opportunity_id     VARCHAR(18) PRIMARY KEY,
    opportunity_name   VARCHAR(255),
    amount             NUMBER(18,2),
    stage_name         VARCHAR(100),
    created_date       DATE,
    close_date         DATE,
    is_closed          BOOLEAN,
    is_won             BOOLEAN,
    owner_id           VARCHAR(18),
    owner_name         VARCHAR(100),
    days_open          NUMBER,
    days_to_close      NUMBER,
    total_activities   NUMBER,
    load_timestamp     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS dim_activities (
    activity_id        VARCHAR(18) PRIMARY KEY,
    opportunity_id     VARCHAR(18),
    activity_type      VARCHAR(255),
    activity_date      DATE,
    owner_id           VARCHAR(18),
    load_timestamp     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Stage transitions sourced from Salesforce OpportunityHistory.
-- Required for honest funnel conversion and time-in-stage metrics.
CREATE TABLE IF NOT EXISTS dim_stage_history (
    history_id         VARCHAR(18) PRIMARY KEY,
    opportunity_id     VARCHAR(18),
    stage_name         VARCHAR(100),
    entered_at         TIMESTAMP_NTZ,
    load_timestamp     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id             VARCHAR(50) PRIMARY KEY,
    workflow_type      VARCHAR(50),
    asana_task_id      VARCHAR(50),
    start_time         TIMESTAMP_NTZ,
    end_time           TIMESTAMP_NTZ,
    status             VARCHAR(20),
    records_processed  NUMBER,
    error_message      VARCHAR(5000),
    gemini_tokens_used NUMBER,
    gemini_cost        NUMBER(10,6),
    load_timestamp     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

SELECT 'Tables created successfully' AS status;
