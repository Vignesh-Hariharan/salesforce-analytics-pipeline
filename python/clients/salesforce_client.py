from simple_salesforce import Salesforce
from typing import List, Dict, Iterable
import time
from utils.logger import setup_logger
from utils.error_handler import retry_on_failure, SalesforceExtractError
from config import settings

logger = setup_logger(__name__)

# SOQL query strings have a hard limit of 100k characters. Keeping batches
# well under that lets us safely concatenate up to ~200 18-char IDs per query.
ID_BATCH_SIZE = 200


def _chunked(items: List[str], size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _quote_ids(ids: List[str]) -> str:
    return "','".join(ids)


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
            logger.info("Connected to Salesforce")
        except Exception as e:
            logger.error(f"Salesforce connection failed: {e}")
            raise SalesforceExtractError(f"Salesforce connection failed: {e}")

    def get_opportunities(self, days: int = 90) -> List[Dict]:
        try:
            start = time.time()
            query = f"""
                SELECT Id, Name, Amount, StageName,
                       CreatedDate, CloseDate, IsClosed, IsWon,
                       OwnerId, Owner.Name
                FROM Opportunity
                WHERE CreatedDate = LAST_N_DAYS:{days}
                ORDER BY CreatedDate DESC
            """
            logger.info(f"Querying opportunities (last {days} days)")
            result = self.sf.query_all(query)

            opportunities = []
            for r in result['records']:
                opportunities.append({
                    'opportunity_id': r['Id'],
                    'opportunity_name': r['Name'],
                    'amount': r.get('Amount') or 0,
                    'stage_name': r['StageName'],
                    'created_date': r['CreatedDate'][:10] if r.get('CreatedDate') else None,
                    'close_date': r['CloseDate'] if r.get('CloseDate') else None,
                    'is_closed': r['IsClosed'],
                    'is_won': r['IsWon'],
                    'owner_id': r['OwnerId'],
                    'owner_name': r['Owner']['Name'] if r.get('Owner') else 'Unknown',
                })

            logger.info(f"Extracted {len(opportunities)} opportunities in {(time.time() - start) * 1000:.0f}ms")
            return opportunities

        except Exception as e:
            logger.error(f"Opportunity extraction failed: {e}")
            raise SalesforceExtractError(f"Opportunity extraction failed: {e}")

    def get_activities(self, opportunity_ids: List[str]) -> List[Dict]:
        if not opportunity_ids:
            return []

        try:
            start = time.time()
            activities: List[Dict] = []

            for batch in _chunked(opportunity_ids, ID_BATCH_SIZE):
                query = f"""
                    SELECT Id, WhatId, Subject, ActivityDate, OwnerId
                    FROM Task
                    WHERE WhatId IN ('{_quote_ids(batch)}')
                      AND ActivityDate != NULL
                """
                result = self.sf.query_all(query)
                for r in result['records']:
                    activities.append({
                        'activity_id': r['Id'],
                        'opportunity_id': r['WhatId'],
                        'activity_type': r.get('Subject') or 'Task',
                        'activity_date': r.get('ActivityDate'),
                        'owner_id': r['OwnerId'],
                    })

            logger.info(f"Extracted {len(activities)} activities for {len(opportunity_ids)} opps "
                        f"in {(time.time() - start) * 1000:.0f}ms")
            return activities

        except Exception as e:
            logger.error(f"Activity extraction failed: {e}")
            raise SalesforceExtractError(f"Activity extraction failed: {e}")

    def get_stage_history(self, opportunity_ids: List[str]) -> List[Dict]:
        """Pull every StageName transition for the given opportunities.

        OpportunityHistory rows are emitted by Salesforce on each stage change,
        so this is the only honest source for funnel conversion and time-in-stage
        analytics. Without it, you only ever see the *current* stage.
        """
        if not opportunity_ids:
            return []

        try:
            start = time.time()
            transitions: List[Dict] = []

            for batch in _chunked(opportunity_ids, ID_BATCH_SIZE):
                query = f"""
                    SELECT Id, OpportunityId, StageName, CreatedDate
                    FROM OpportunityHistory
                    WHERE OpportunityId IN ('{_quote_ids(batch)}')
                """
                result = self.sf.query_all(query)
                for r in result['records']:
                    transitions.append({
                        'history_id': r['Id'],
                        'opportunity_id': r['OpportunityId'],
                        'stage_name': r['StageName'],
                        'entered_at': r['CreatedDate'],
                    })

            logger.info(f"Extracted {len(transitions)} stage transitions in "
                        f"{(time.time() - start) * 1000:.0f}ms")
            return transitions

        except Exception as e:
            logger.error(f"Stage history extraction failed: {e}")
            raise SalesforceExtractError(f"Stage history extraction failed: {e}")
