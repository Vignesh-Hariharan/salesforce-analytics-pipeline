from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
import os
import pandas as pd

from clients.gemini_client import GeminiClient
from clients.salesforce_client import SalesforceClient
from clients.snowflake_client import SnowflakeClient
from config import settings
from config.prompts import get_prompt
from utils.error_handler import GeminiAPIError
from utils.logger import setup_logger

logger = setup_logger(__name__)


def extract_and_load(sf_client: SalesforceClient, snow_client: SnowflakeClient,
                     days: int = 90) -> List[Dict]:
    """Extract opportunities, activities and stage history; persist to Snowflake.

    Returns the enriched opportunity list (with derived day counts and activity totals).
    """
    opportunities = sf_client.get_opportunities(days=days)
    if not opportunities:
        raise ValueError(f"No opportunities found in Salesforce for the last {days} days")

    valid = [o for o in opportunities if o.get('opportunity_id') and o.get('opportunity_name')]
    dropped = len(opportunities) - len(valid)
    if dropped:
        logger.warning(f"Dropped {dropped} opportunities missing id or name")
    if not valid:
        raise ValueError("No valid opportunities after filtering")

    opp_ids = [o['opportunity_id'] for o in valid]
    activities = sf_client.get_activities(opp_ids)
    stage_history = sf_client.get_stage_history(opp_ids)

    activity_counts: Dict[str, int] = {}
    for a in activities:
        activity_counts[a['opportunity_id']] = activity_counts.get(a['opportunity_id'], 0) + 1

    now = datetime.now()
    for opp in valid:
        opp['total_activities'] = activity_counts.get(opp['opportunity_id'], 0)
        created = pd.to_datetime(opp['created_date']) if opp.get('created_date') else None
        closed = pd.to_datetime(opp['close_date']) if opp.get('close_date') else None
        if created is not None and closed is not None:
            opp['days_to_close'] = (closed - created).days
            opp['days_open'] = (closed - created).days
        elif created is not None:
            opp['days_to_close'] = None
            opp['days_open'] = (now - created).days
        else:
            opp['days_to_close'] = None
            opp['days_open'] = None

    snow_client.load_opportunities(valid)
    snow_client.load_activities(activities)
    snow_client.load_stage_history(stage_history)

    return valid


def chart_path(name: str, output_dir: Path) -> Path:
    return output_dir / f'{name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'


def generate_optional_commentary(workflow_type: str, data_summary: str,
                                 chart_paths: List[Path]) -> Tuple[str, Dict]:
    """Ask the LLM for a short narrative per chart.

    Commentary is an enrichment layer, not the product: the metrics and charts
    come from SQL. When no API key is configured, or the model call fails, the
    run continues with an empty narrative instead of failing. The reason is
    logged so a skipped commentary is never silent.
    """
    empty_stats = {'tokens': 0, 'cost': 0.0}
    if not settings.is_llm_commentary_enabled():
        if os.getenv('SKIP_AI', '').lower() in ('1', 'true', 'yes'):
            logger.info("SKIP_AI set; skipping optional LLM commentary")
        else:
            logger.info("GEMINI_API_KEY not set; skipping optional LLM commentary")
        return "", empty_stats

    prompt, temperature = get_prompt(workflow_type, data_summary)
    try:
        client = GeminiClient(model_name=settings.GEMINI_MODEL, temperature=temperature)
        result = client.generate_insights(prompt, chart_paths)
        return result['insights'], {'tokens': result['total_tokens'], 'cost': result['cost']}
    except GeminiAPIError as e:
        logger.warning(f"LLM commentary unavailable; continuing without it: {e}")
        return "", empty_stats
