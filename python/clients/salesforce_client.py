from simple_salesforce import Salesforce
from typing import List, Dict
import time
from utils.logger import setup_logger
from utils.error_handler import retry_on_failure, SalesforceExtractError
from config import settings

logger = setup_logger(__name__)

class SalesforceClient:
    def __init__(self):
        self.sf = None
        self._connect()
    
    @retry_on_failure(max_attempts=3, delay=2.0, exceptions=(Exception,))
    def _connect(self):
        try:
            self.sf = Salesforce(
                username=settings.SALESFORCE_USERNAME,
                password=settings.SALESFORCE_PASSWORD,
                security_token=settings.SALESFORCE_SECURITY_TOKEN,
                domain=settings.SALESFORCE_DOMAIN
            )
            logger.info("Connected to Salesforce successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Salesforce: {str(e)}")
            raise SalesforceExtractError(f"Salesforce connection failed: {str(e)}")
    
    def get_opportunities(self, days: int = 90) -> List[Dict]:
        try:
            start_time = time.time()
            query = f"""
                SELECT 
                    Id, Name, Amount, StageName,
                    CreatedDate, CloseDate, IsClosed, IsWon,
                    OwnerId, Owner.Name
                FROM Opportunity
                WHERE CreatedDate = LAST_N_DAYS:{days}
                ORDER BY CreatedDate DESC
            """
            
            logger.info(f"Extracting opportunities from last {days} days")
            result = self.sf.query_all(query)
            records = result['records']
            
            opportunities = []
            for record in records:
                opp = {
                    'opportunity_id': record['Id'],
                    'opportunity_name': record['Name'],
                    'amount': record.get('Amount', 0),
                    'stage_name': record['StageName'],
                    'created_date': record['CreatedDate'][:10] if record.get('CreatedDate') else None,
                    'close_date': record['CloseDate'] if record.get('CloseDate') else None,
                    'is_closed': record['IsClosed'],
                    'is_won': record['IsWon'],
                    'owner_id': record['OwnerId'],
                    'owner_name': record['Owner']['Name'] if record.get('Owner') else 'Unknown'
                }
                opportunities.append(opp)
            
            duration = (time.time() - start_time) * 1000
            logger.info(f"Extracted {len(opportunities)} opportunities in {duration:.2f}ms")
            return opportunities
            
        except Exception as e:
            logger.error(f"Failed to extract opportunities: {str(e)}")
            raise SalesforceExtractError(f"Opportunity extraction failed: {str(e)}")
    
    def get_activities(self, opportunity_ids: List[str]) -> List[Dict]:
        if not opportunity_ids:
            logger.warning("No opportunity IDs provided for activity extraction")
            return []
        
        try:
            start_time = time.time()
            ids_str = "','".join(opportunity_ids)
            query = f"""
                SELECT 
                    Id, WhatId, Subject, ActivityDate, OwnerId
                FROM Task
                WHERE WhatId IN ('{ids_str}')
                AND ActivityDate != NULL
                ORDER BY ActivityDate DESC
            """
            
            logger.info(f"Extracting activities for {len(opportunity_ids)} opportunities")
            result = self.sf.query_all(query)
            records = result['records']
            
            activities = []
            for record in records:
                activity = {
                    'activity_id': record['Id'],
                    'opportunity_id': record['WhatId'],
                    'activity_type': record.get('Subject', 'Task'),
                    'activity_date': record['ActivityDate'] if record.get('ActivityDate') else None,
                    'owner_id': record['OwnerId']
                }
                activities.append(activity)
            
            duration = (time.time() - start_time) * 1000
            logger.info(f"Extracted {len(activities)} activities in {duration:.2f}ms")
            return activities
            
        except Exception as e:
            logger.error(f"Failed to extract activities: {str(e)}")
            raise SalesforceExtractError(f"Activity extraction failed: {str(e)}")

