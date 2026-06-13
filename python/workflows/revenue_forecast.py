import matplotlib
matplotlib.use('Agg')

from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import pandas as pd

from clients.gemini_client import GeminiClient
from clients.salesforce_client import SalesforceClient
from clients.snowflake_client import SnowflakeClient
from config import settings
from config.prompts import get_prompt
from utils.logger import setup_logger
from workflows._shared import chart_path, extract_and_load

logger = setup_logger(__name__)

WORKFLOW_TYPE = 'revenue-forecast'

# When stage history is too thin to derive a stable historical win-rate, fall
# back to these widely-used Salesforce defaults so the forecast still produces
# something defensible. The fallback flag is surfaced to the user so the chart
# is never confused with a model fit.
DEFAULT_STAGE_WEIGHTS = {
    'Prospecting': 0.10,
    'Qualification': 0.25,
    'Needs Analysis': 0.40,
    'Proposal': 0.60,
    'Negotiation': 0.80,
    'Closed Won': 1.00,
}

# A stage needs at least this many historical opportunities before we trust the
# data-derived weight. Below the threshold, the default value is used and the
# row is flagged.
MIN_STAGE_SAMPLE = 10


def run_workflow(run_id: str) -> Dict:
    logger.info(f"Starting revenue forecast workflow: {run_id}")
    start_time = datetime.now()

    sf_client = SalesforceClient()
    snow_client = SnowflakeClient()

    try:
        opportunities = extract_and_load(sf_client, snow_client, days=90)

        metrics = calculate_metrics(snow_client)
        chart_paths = generate_charts(snow_client, metrics)

        prompt, temperature = get_prompt(WORKFLOW_TYPE, build_data_summary(metrics))
        gemini_client = GeminiClient(temperature=temperature)
        insights_result = gemini_client.generate_insights(prompt, chart_paths)

        snow_client.log_pipeline_run(
            run_id=run_id,
            workflow_type=WORKFLOW_TYPE,
            asana_task_id='',
            start_time=start_time,
            end_time=datetime.now(),
            status='success',
            records_processed=len(opportunities),
            gemini_tokens=insights_result['total_tokens'],
            gemini_cost=insights_result['cost'],
        )

        return {
            'status': 'success',
            'workflow_type': WORKFLOW_TYPE,
            'metrics': metrics,
            'insights': insights_result['insights'],
            'chart_paths': [str(p) for p in chart_paths],
            'gemini_stats': {
                'tokens': insights_result['total_tokens'],
                'cost': insights_result['cost'],
            },
            'records_processed': len(opportunities),
        }

    except Exception as e:
        logger.error(f"Revenue forecast workflow failed: {e}")
        snow_client.log_pipeline_run(
            run_id=run_id,
            workflow_type=WORKFLOW_TYPE,
            asana_task_id='',
            start_time=start_time,
            end_time=datetime.now(),
            status='failed',
            records_processed=0,
            error_message=str(e),
        )
        raise
    finally:
        snow_client.close()


def derive_stage_weights(snow_client: SnowflakeClient) -> Tuple[Dict[str, Dict], int]:
    """Compute win probability per stage from historical data.

    For each stage that an opportunity ever entered, win-rate = won / (won + lost).
    Below MIN_STAGE_SAMPLE we don't trust the estimate and fall back to the
    documented industry default.
    """
    rows = snow_client.execute_query("""
        WITH first_touch AS (
            SELECT DISTINCT h.opportunity_id, h.stage_name
            FROM dim_stage_history h
        )
        SELECT
            ft.stage_name,
            COUNT(*)                                      AS sample_size,
            SUM(CASE WHEN o.is_won THEN 1 ELSE 0 END)     AS won_count,
            SUM(CASE WHEN o.is_closed AND NOT o.is_won
                     THEN 1 ELSE 0 END)                   AS lost_count
        FROM first_touch ft
        JOIN fact_opportunities o ON o.opportunity_id = ft.opportunity_id
        WHERE o.is_closed
        GROUP BY ft.stage_name
    """)

    weights: Dict[str, Dict] = {}
    for r in rows:
        sample = r['SAMPLE_SIZE'] or 0
        won = r['WON_COUNT'] or 0
        if sample >= MIN_STAGE_SAMPLE:
            weights[r['STAGE_NAME']] = {
                'weight': won / sample,
                'sample_size': sample,
                'source': 'historical',
            }

    fallback_used = 0
    for stage, default in DEFAULT_STAGE_WEIGHTS.items():
        if stage not in weights:
            weights[stage] = {
                'weight': default,
                'sample_size': 0,
                'source': 'default',
            }
            fallback_used += 1

    if fallback_used:
        logger.warning(
            f"{fallback_used}/{len(DEFAULT_STAGE_WEIGHTS)} stages fell back to default weights "
            f"(need >= {MIN_STAGE_SAMPLE} closed opps for historical fit)"
        )

    return weights, fallback_used


def calculate_metrics(snow_client: SnowflakeClient) -> Dict:
    pipeline = snow_client.execute_query("""
        SELECT SUM(amount) AS total_pipeline,
               COUNT(*)    AS open_opps
        FROM fact_opportunities
        WHERE NOT is_closed AND amount > 0
    """)[0]

    open_stages = snow_client.execute_query("""
        SELECT stage_name,
               SUM(amount) AS stage_value,
               COUNT(*)    AS count
        FROM fact_opportunities
        WHERE NOT is_closed AND amount > 0
        GROUP BY stage_name
    """)

    weights, fallback_count = derive_stage_weights(snow_client)

    weighted_forecast = 0.0
    stage_forecasts = []
    for s in open_stages:
        stage = s['STAGE_NAME']
        value = float(s['STAGE_VALUE'] or 0)
        meta = weights.get(stage, {'weight': 0.25, 'sample_size': 0, 'source': 'default'})
        weighted_value = value * meta['weight']
        weighted_forecast += weighted_value
        stage_forecasts.append({
            'stage': stage,
            'value': value,
            'count': s['COUNT'],
            'weight': meta['weight'],
            'weighted_value': weighted_value,
            'sample_size': meta['sample_size'],
            'weight_source': meta['source'],
        })

    historical_revenue = snow_client.execute_query("""
        SELECT DATE_TRUNC('month', close_date) AS month,
               SUM(amount)                      AS revenue
        FROM fact_opportunities
        WHERE is_won AND close_date >= DATEADD(month, -6, CURRENT_DATE())
        GROUP BY month
        ORDER BY month
    """)

    at_risk = snow_client.execute_query("""
        SELECT SUM(amount) AS at_risk_value
        FROM fact_opportunities
        WHERE NOT is_closed AND days_open > 90
    """)
    at_risk_value = float((at_risk[0]['AT_RISK_VALUE'] or 0)) if at_risk else 0.0

    return {
        'total_pipeline': float(pipeline['TOTAL_PIPELINE'] or 0),
        'open_opps': int(pipeline['OPEN_OPPS'] or 0),
        'weighted_forecast': weighted_forecast,
        'at_risk_value': at_risk_value,
        'stage_forecasts': stage_forecasts,
        'historical_revenue': historical_revenue,
        'weights_fallback_count': fallback_count,
    }


def generate_charts(snow_client: SnowflakeClient, metrics: Dict) -> List[Path]:
    out = settings.OUTPUT_DIR
    paths: List[Path] = []

    paths.extend(_chart_waterfall(metrics, out))
    paths.extend(_chart_stage_weights(metrics, out))
    paths.extend(_chart_revenue_trend(metrics, out))
    paths.extend(_chart_age_distribution(snow_client, out))

    return paths


def _chart_waterfall(metrics: Dict, out: Path) -> List[Path]:
    bars = [
        ('Total pipeline',   metrics['total_pipeline']),
        ('At risk (>90d)',  -metrics['at_risk_value']),
        ('Weighted forecast', metrics['weighted_forecast']),
    ]
    plt.figure(figsize=(10, 6))
    plt.bar(range(len(bars)), [v for _, v in bars],
            color=['steelblue', 'coral', 'seagreen'], alpha=0.85)
    for i, (_, v) in enumerate(bars):
        plt.text(i, v, f"${abs(v):,.0f}",
                 ha='center', va='bottom' if v >= 0 else 'top', fontsize=9)
    plt.xticks(range(len(bars)), [n for n, _ in bars])
    plt.ylabel('Value ($)')
    plt.title('Pipeline waterfall')
    plt.tight_layout()
    path = chart_path('revenue_forecast_waterfall', out)
    plt.savefig(path, dpi=100, bbox_inches='tight')
    plt.close()
    return [path]


def _chart_stage_weights(metrics: Dict, out: Path) -> List[Path]:
    if not metrics['stage_forecasts']:
        return []
    df = pd.DataFrame(metrics['stage_forecasts']).sort_values('weight')

    bar_colors = [
        'mediumpurple' if src == 'historical' else 'lightgray'
        for src in df['weight_source']
    ]

    plt.figure(figsize=(10, 6))
    plt.barh(df['stage'], df['weight'] * 100, color=bar_colors)
    for i, row in enumerate(df.itertuples()):
        label = f"{row.weight * 100:.0f}%"
        if row.weight_source == 'historical':
            label += f"  (n={int(row.sample_size)})"
        else:
            label += "  (default)"
        plt.text(row.weight * 100 + 1, i, label, va='center', fontsize=9)
    plt.xlabel('Win probability (%)')
    plt.title('Stage win probability — historical where available, defaults otherwise')
    plt.xlim(0, 110)
    plt.tight_layout()
    path = chart_path('revenue_forecast_weights', out)
    plt.savefig(path, dpi=100, bbox_inches='tight')
    plt.close()
    return [path]


def _chart_revenue_trend(metrics: Dict, out: Path) -> List[Path]:
    if not metrics['historical_revenue']:
        return []
    df = pd.DataFrame(metrics['historical_revenue']).copy()
    df['LABEL'] = pd.to_datetime(df['MONTH']).dt.strftime('%b %Y')
    df['REVENUE'] = df['REVENUE'].astype(float).fillna(0)

    plt.figure(figsize=(10, 6))
    plt.plot(df['LABEL'], df['REVENUE'], marker='o', linewidth=2,
             color='steelblue', label='Closed-won (actual)')

    forecast_label = (datetime.now() + timedelta(days=30)).strftime('%b %Y')
    plt.scatter([forecast_label], [metrics['weighted_forecast']],
                color='coral', s=100, label='Weighted forecast', zorder=5)

    plt.ylabel('Revenue ($)')
    plt.xlabel('Month')
    plt.title('Closed revenue with weighted forecast')
    plt.legend()
    plt.xticks(rotation=45)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    path = chart_path('revenue_forecast_trend', out)
    plt.savefig(path, dpi=100, bbox_inches='tight')
    plt.close()
    return [path]


def _chart_age_distribution(snow_client: SnowflakeClient, out: Path) -> List[Path]:
    rows = snow_client.execute_query("""
        SELECT days_open
        FROM fact_opportunities
        WHERE NOT is_closed AND days_open IS NOT NULL
    """)
    if not rows:
        return []
    df = pd.DataFrame(rows)

    plt.figure(figsize=(10, 6))
    plt.hist(df['DAYS_OPEN'], bins=20, color='seagreen', alpha=0.75, edgecolor='black')
    plt.axvline(90, color='red', linestyle='--', label='At-risk threshold (90d)')
    plt.xlabel('Days open')
    plt.ylabel('Number of opportunities')
    plt.title('Pipeline age distribution')
    plt.legend()
    plt.tight_layout()
    path = chart_path('revenue_forecast_age', out)
    plt.savefig(path, dpi=100, bbox_inches='tight')
    plt.close()
    return [path]


def build_data_summary(metrics: Dict) -> str:
    lines = [
        f"Total Pipeline: ${metrics['total_pipeline']:,.0f}",
        f"Open Opportunities: {metrics['open_opps']}",
        f"Weighted Forecast: ${metrics['weighted_forecast']:,.0f}",
        f"At-Risk Pipeline (>90 days open): ${metrics['at_risk_value']:,.0f}",
    ]
    if metrics['weights_fallback_count']:
        lines.append(
            f"Note: {metrics['weights_fallback_count']} stage(s) fell back to default weights "
            f"due to insufficient historical samples."
        )
    lines.append("")
    lines.append("STAGE BREAKDOWN:")
    for s in metrics['stage_forecasts']:
        source_tag = (
            f"historical, n={s['sample_size']}"
            if s['weight_source'] == 'historical' else "default"
        )
        lines.append(
            f"{s['stage']}: ${s['value']:,.0f} × {s['weight'] * 100:.0f}% "
            f"= ${s['weighted_value']:,.0f}  [{source_tag}]"
        )

    if metrics['historical_revenue']:
        lines.append("")
        lines.append("RECENT CLOSED REVENUE:")
        for row in metrics['historical_revenue'][-3:]:
            month = pd.to_datetime(row['MONTH']).strftime('%b %Y')
            lines.append(f"{month}: ${(row['REVENUE'] or 0):,.0f}")
    return "\n".join(lines)
