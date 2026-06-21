from typing import Dict, List, Tuple

from clients.gemini_client import GeminiClient
from clients.salesforce_client import SalesforceClient
from clients.snowflake_client import SnowflakeClient
from config import settings
from config.prompts import get_prompt
from utils.dbt_runner import run_dbt_build
from utils.error_handler import GeminiAPIError
from utils.logger import setup_logger
from pathlib import Path
from datetime import datetime
import os

logger = setup_logger(__name__)


def extract_and_load(sf_client: SalesforceClient, snow_client: SnowflakeClient,
                     days: int = 90) -> List[Dict]:
    """Extract from Salesforce and MERGE into raw_* landing tables.

    Returns the validated opportunity list (records_processed count). All
    derivation happens in dbt after run_dbt_transform().
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

    snow_client.load_opportunities(valid)
    snow_client.load_activities(activities)
    snow_client.load_stage_history(stage_history)

    return valid


def run_dbt_transform() -> None:
    """Build dbt marts from raw landing tables."""
    run_dbt_build()


def chart_path(name: str, output_dir: Path) -> Path:
    return output_dir / f'{name}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'


def generate_optional_commentary(workflow_type: str, data_summary: str,
                                 chart_paths: List[Path]) -> Tuple[str, Dict]:
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
