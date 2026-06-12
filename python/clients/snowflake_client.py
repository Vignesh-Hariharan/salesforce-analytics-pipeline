import snowflake.connector
from typing import List, Dict, Optional
import time
from datetime import datetime
from utils.logger import setup_logger
from utils.error_handler import retry_on_failure, SnowflakeLoadError
from config import settings

logger = setup_logger(__name__)

# Snowflake recommends batching paramaterized statements; 500 keeps each
# round-trip under typical statement-size limits while still amortizing
# network overhead.
MERGE_BATCH_SIZE = 500


_OPPORTUNITY_MERGE = """
MERGE INTO fact_opportunities t
USING (
    SELECT
        %(opportunity_id)s   AS opportunity_id,
        %(opportunity_name)s AS opportunity_name,
        %(amount)s           AS amount,
        %(stage_name)s       AS stage_name,
        %(created_date)s     AS created_date,
        %(close_date)s       AS close_date,
        %(is_closed)s        AS is_closed,
        %(is_won)s           AS is_won,
        %(owner_id)s         AS owner_id,
        %(owner_name)s       AS owner_name,
        %(days_open)s        AS days_open,
        %(days_to_close)s    AS days_to_close,
        %(total_activities)s AS total_activities
) s
ON t.opportunity_id = s.opportunity_id
WHEN MATCHED THEN UPDATE SET
    opportunity_name = s.opportunity_name,
    amount           = s.amount,
    stage_name       = s.stage_name,
    close_date       = s.close_date,
    is_closed        = s.is_closed,
    is_won           = s.is_won,
    owner_id         = s.owner_id,
    owner_name       = s.owner_name,
    days_open        = s.days_open,
    days_to_close    = s.days_to_close,
    total_activities = s.total_activities,
    load_timestamp   = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (
    opportunity_id, opportunity_name, amount, stage_name,
    created_date, close_date, is_closed, is_won,
    owner_id, owner_name, days_open, days_to_close, total_activities
) VALUES (
    s.opportunity_id, s.opportunity_name, s.amount, s.stage_name,
    s.created_date, s.close_date, s.is_closed, s.is_won,
    s.owner_id, s.owner_name, s.days_open, s.days_to_close, s.total_activities
)
"""

_ACTIVITY_MERGE = """
MERGE INTO dim_activities t
USING (
    SELECT
        %(activity_id)s    AS activity_id,
        %(opportunity_id)s AS opportunity_id,
        %(activity_type)s  AS activity_type,
        %(activity_date)s  AS activity_date,
        %(owner_id)s       AS owner_id
) s
ON t.activity_id = s.activity_id
WHEN MATCHED THEN UPDATE SET
    activity_type  = s.activity_type,
    activity_date  = s.activity_date,
    load_timestamp = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (
    activity_id, opportunity_id, activity_type, activity_date, owner_id
) VALUES (
    s.activity_id, s.opportunity_id, s.activity_type, s.activity_date, s.owner_id
)
"""

_STAGE_HISTORY_MERGE = """
MERGE INTO dim_stage_history t
USING (
    SELECT
        %(history_id)s     AS history_id,
        %(opportunity_id)s AS opportunity_id,
        %(stage_name)s     AS stage_name,
        %(entered_at)s     AS entered_at
) s
ON t.history_id = s.history_id
WHEN NOT MATCHED THEN INSERT (
    history_id, opportunity_id, stage_name, entered_at
) VALUES (
    s.history_id, s.opportunity_id, s.stage_name, s.entered_at
)
"""

_PIPELINE_RUN_INSERT = """
INSERT INTO pipeline_runs (
    run_id, workflow_type, asana_task_id, start_time, end_time,
    status, records_processed, error_message, gemini_tokens_used, gemini_cost
) VALUES (
    %(run_id)s, %(workflow_type)s, %(asana_task_id)s, %(start_time)s, %(end_time)s,
    %(status)s, %(records_processed)s, %(error_message)s, %(gemini_tokens)s, %(gemini_cost)s
)
"""


def _chunk(rows, size):
    for i in range(0, len(rows), size):
        yield rows[i:i + size]


class SnowflakeClient:
    def __init__(self):
        self.conn = None
        self._connect()

    @retry_on_failure(max_attempts=3, delay=2.0, exceptions=(Exception,))
    def _connect(self):
        try:
            self.conn = snowflake.connector.connect(
                user=settings.SNOWFLAKE_USER,
                password=settings.SNOWFLAKE_PASSWORD,
                account=settings.SNOWFLAKE_ACCOUNT,
                database=settings.SNOWFLAKE_DATABASE,
                schema=settings.SNOWFLAKE_SCHEMA,
                warehouse=settings.SNOWFLAKE_WAREHOUSE,
            )
            logger.info("Connected to Snowflake")
        except Exception as e:
            logger.error(f"Snowflake connection failed: {e}")
            raise SnowflakeLoadError(f"Snowflake connection failed: {e}")

    def _executemany_batched(self, sql: str, rows: List[Dict], label: str) -> int:
        if not rows:
            return 0

        start = time.time()
        cursor = self.conn.cursor()
        loaded = 0
        try:
            for batch in _chunk(rows, MERGE_BATCH_SIZE):
                cursor.executemany(sql, batch)
                loaded += len(batch)
            self.conn.commit()
        finally:
            cursor.close()

        logger.info(f"Loaded {loaded} {label} in {(time.time() - start) * 1000:.0f}ms")
        return loaded

    def load_opportunities(self, opportunities: List[Dict]) -> int:
        if not opportunities:
            logger.warning("No opportunities to load")
            return 0
        try:
            return self._executemany_batched(_OPPORTUNITY_MERGE, opportunities, "opportunities")
        except Exception as e:
            logger.error(f"Opportunity load failed: {e}")
            raise SnowflakeLoadError(f"Opportunity load failed: {e}")

    def load_activities(self, activities: List[Dict]) -> int:
        if not activities:
            logger.warning("No activities to load")
            return 0
        try:
            return self._executemany_batched(_ACTIVITY_MERGE, activities, "activities")
        except Exception as e:
            logger.error(f"Activity load failed: {e}")
            raise SnowflakeLoadError(f"Activity load failed: {e}")

    def load_stage_history(self, transitions: List[Dict]) -> int:
        if not transitions:
            logger.warning("No stage transitions to load")
            return 0
        try:
            return self._executemany_batched(_STAGE_HISTORY_MERGE, transitions, "stage transitions")
        except Exception as e:
            logger.error(f"Stage history load failed: {e}")
            raise SnowflakeLoadError(f"Stage history load failed: {e}")

    def execute_query(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        try:
            cursor = self.conn.cursor()
            cursor.execute(query, params or {})
            columns = [d[0] for d in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            cursor.close()
            return results
        except Exception as e:
            logger.error(f"Query failed: {e}")
            raise SnowflakeLoadError(f"Query failed: {e}")

    def log_pipeline_run(self, run_id: str, workflow_type: str, asana_task_id: str,
                         start_time: datetime, end_time: datetime, status: str,
                         records_processed: int, error_message: Optional[str] = None,
                         gemini_tokens: int = 0, gemini_cost: float = 0.0):
        try:
            cursor = self.conn.cursor()
            cursor.execute(_PIPELINE_RUN_INSERT, {
                'run_id': run_id,
                'workflow_type': workflow_type,
                'asana_task_id': asana_task_id,
                'start_time': start_time,
                'end_time': end_time,
                'status': status,
                'records_processed': records_processed,
                'error_message': error_message,
                'gemini_tokens': gemini_tokens,
                'gemini_cost': gemini_cost,
            })
            self.conn.commit()
            cursor.close()
            logger.info(f"Pipeline run logged: {run_id} ({status})")
        except Exception as e:
            # Audit log failures should not mask the underlying workflow error.
            logger.error(f"Failed to log pipeline run: {e}")

    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("Snowflake connection closed")
