import snowflake.connector
from typing import List, Dict, Optional
import time
from datetime import datetime
from utils.logger import setup_logger
from utils.error_handler import retry_on_failure, SnowflakeLoadError
from config import settings

logger = setup_logger(__name__)

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
                warehouse=settings.SNOWFLAKE_WAREHOUSE
            )
            logger.info("Connected to Snowflake successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Snowflake: {str(e)}")
            raise SnowflakeLoadError(f"Snowflake connection failed: {str(e)}")
    
    def load_opportunities(self, opportunities: List[Dict]) -> int:
        if not opportunities:
            logger.warning("No opportunities to load")
            return 0
        
        try:
            start_time = time.time()
            cursor = self.conn.cursor()
            
            merge_sql = """
                MERGE INTO fact_opportunities AS target
                USING (SELECT 
                    %(opportunity_id)s AS opportunity_id,
                    %(opportunity_name)s AS opportunity_name,
                    %(amount)s AS amount,
                    %(stage_name)s AS stage_name,
                    %(created_date)s AS created_date,
                    %(close_date)s AS close_date,
                    %(is_closed)s AS is_closed,
                    %(is_won)s AS is_won,
                    %(owner_id)s AS owner_id,
                    %(owner_name)s AS owner_name,
                    %(days_open)s AS days_open,
                    %(days_to_close)s AS days_to_close,
                    %(total_activities)s AS total_activities
                ) AS source
                ON target.opportunity_id = source.opportunity_id
                WHEN MATCHED THEN UPDATE SET
                    opportunity_name = source.opportunity_name,
                    amount = source.amount,
                    stage_name = source.stage_name,
                    close_date = source.close_date,
                    is_closed = source.is_closed,
                    is_won = source.is_won,
                    days_open = source.days_open,
                    days_to_close = source.days_to_close,
                    total_activities = source.total_activities,
                    load_timestamp = CURRENT_TIMESTAMP()
                WHEN NOT MATCHED THEN INSERT (
                    opportunity_id, opportunity_name, amount, stage_name,
                    created_date, close_date, is_closed, is_won,
                    owner_id, owner_name, days_open, days_to_close, total_activities
                ) VALUES (
                    source.opportunity_id, source.opportunity_name, source.amount, source.stage_name,
                    source.created_date, source.close_date, source.is_closed, source.is_won,
                    source.owner_id, source.owner_name, source.days_open, source.days_to_close, source.total_activities
                )
            """
            
            loaded = 0
            for opp in opportunities:
                cursor.execute(merge_sql, opp)
                loaded += 1
            
            self.conn.commit()
            cursor.close()
            
            duration = (time.time() - start_time) * 1000
            logger.info(f"Loaded {loaded} opportunities to Snowflake in {duration:.2f}ms")
            return loaded
            
        except Exception as e:
            logger.error(f"Failed to load opportunities: {str(e)}")
            raise SnowflakeLoadError(f"Opportunity load failed: {str(e)}")
    
    def load_activities(self, activities: List[Dict]) -> int:
        if not activities:
            logger.warning("No activities to load")
            return 0
        
        try:
            start_time = time.time()
            cursor = self.conn.cursor()
            
            merge_sql = """
                MERGE INTO dim_activities AS target
                USING (SELECT 
                    %(activity_id)s AS activity_id,
                    %(opportunity_id)s AS opportunity_id,
                    %(activity_type)s AS activity_type,
                    %(activity_date)s AS activity_date,
                    %(owner_id)s AS owner_id
                ) AS source
                ON target.activity_id = source.activity_id
                WHEN MATCHED THEN UPDATE SET
                    activity_type = source.activity_type,
                    activity_date = source.activity_date,
                    load_timestamp = CURRENT_TIMESTAMP()
                WHEN NOT MATCHED THEN INSERT (
                    activity_id, opportunity_id, activity_type, activity_date, owner_id
                ) VALUES (
                    source.activity_id, source.opportunity_id, source.activity_type, 
                    source.activity_date, source.owner_id
                )
            """
            
            loaded = 0
            for activity in activities:
                cursor.execute(merge_sql, activity)
                loaded += 1
            
            self.conn.commit()
            cursor.close()
            
            duration = (time.time() - start_time) * 1000
            logger.info(f"Loaded {loaded} activities to Snowflake in {duration:.2f}ms")
            return loaded
            
        except Exception as e:
            logger.error(f"Failed to load activities: {str(e)}")
            raise SnowflakeLoadError(f"Activity load failed: {str(e)}")
    
    def execute_query(self, query: str) -> List[Dict]:
        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            
            columns = [desc[0] for desc in cursor.description]
            results = []
            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))
            
            cursor.close()
            logger.info(f"Query executed successfully, returned {len(results)} rows")
            return results
            
        except Exception as e:
            logger.error(f"Query execution failed: {str(e)}")
            raise SnowflakeLoadError(f"Query failed: {str(e)}")
    
    def log_pipeline_run(self, run_id: str, workflow_type: str, asana_task_id: str,
                         start_time: datetime, end_time: datetime, status: str,
                         records_processed: int, error_message: Optional[str] = None,
                         gemini_tokens: int = 0, gemini_cost: float = 0.0):
        try:
            cursor = self.conn.cursor()
            insert_sql = """
                INSERT INTO pipeline_runs (
                    run_id, workflow_type, asana_task_id, start_time, end_time,
                    status, records_processed, error_message, gemini_tokens_used, gemini_cost
                ) VALUES (
                    %(run_id)s, %(workflow_type)s, %(asana_task_id)s, %(start_time)s, %(end_time)s,
                    %(status)s, %(records_processed)s, %(error_message)s, %(gemini_tokens)s, %(gemini_cost)s
                )
            """
            cursor.execute(insert_sql, {
                'run_id': run_id,
                'workflow_type': workflow_type,
                'asana_task_id': asana_task_id,
                'start_time': start_time,
                'end_time': end_time,
                'status': status,
                'records_processed': records_processed,
                'error_message': error_message,
                'gemini_tokens': gemini_tokens,
                'gemini_cost': gemini_cost
            })
            self.conn.commit()
            cursor.close()
            logger.info(f"Pipeline run logged: {run_id} - {status}")
        except Exception as e:
            logger.error(f"Failed to log pipeline run: {str(e)}")
    
    def close(self):
        if self.conn:
            self.conn.close()
            logger.info("Snowflake connection closed")

