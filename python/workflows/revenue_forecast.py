import matplotlib
matplotlib.use('Agg')

from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import pandas as pd

from clients.salesforce_client import SalesforceClient
from clients.snowflake_client import SnowflakeClient
from config import settings
from utils.logger import setup_logger
from workflows._shared import (
    chart_path, extract_and_load, generate_optional_commentary, run_dbt_transform,
)

logger = setup_logger(__name__)

WORKFLOW_TYPE = 'revenue-forecast'


def run_workflow(run_id: str) -> Dict:
    logger.info(f"Starting revenue forecast workflow: {run_id}")
    start_time = datetime.now()

    sf_client = SalesforceClient()
    snow_client = SnowflakeClient()

    try:
        opportunities = extract_and_load(sf_client, snow_client, days=90)
        run_dbt_transform()

        metrics = calculate_metrics(snow_client)
        chart_paths = generate_charts(snow_client, metrics)

        insights, gemini_stats = generate_optional_commentary(
            WORKFLOW_TYPE, build_data_summary(metrics), chart_paths)

        snow_client.log_pipeline_run(
            run_id=run_id,
            workflow_type=WORKFLOW_TYPE,
            asana_task_id='',
            start_time=start_time,
            end_time=datetime.now(),
            status='success',
            records_processed=len(opportunities),
            gemini_tokens=gemini_stats['tokens'],
            gemini_cost=gemini_stats['cost'],
        )

        return {
            'status': 'success',
            'workflow_type': WORKFLOW_TYPE,
            'metrics': metrics,
            'insights': insights,
            'chart_paths': [str(p) for p in chart_paths],
            'gemini_stats': gemini_stats,
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


def map_stage_forecasts(rows: List[Dict]) -> List[Dict]:
    """Map fct_revenue_forecast rows into the chart/summary shape."""
    return [
        {
            'stage': r['STAGE_NAME'],
            'value': float(r['STAGE_VALUE'] or 0),
            'count': r['OPEN_COUNT'],
            'weight': float(r['WEIGHT'] or 0),
            'weighted_value': float(r['WEIGHTED_VALUE'] or 0),
            'sample_size': r['SAMPLE_SIZE'] or 0,
            'weight_source': (r['WEIGHT_SOURCE'] or 'default').lower(),
        }
        for r in rows
    ]


def calculate_metrics(snow_client: SnowflakeClient) -> Dict:
    summary = snow_client.execute_query("SELECT * FROM fct_revenue_summary")[0]

    stage_rows = snow_client.execute_query("""
        SELECT
            stage_name,
            open_count,
            stage_value,
            weight,
            weighted_value,
            sample_size,
            weight_source
        FROM fct_revenue_forecast
        ORDER BY stage_position
    """)

    historical_revenue = snow_client.execute_query("""
        SELECT month, revenue
        FROM fct_monthly_closed_revenue
        ORDER BY month
    """)

    return {
        'total_pipeline': float(summary['TOTAL_PIPELINE'] or 0),
        'open_opps': int(summary['OPEN_OPPS'] or 0),
        'weighted_forecast': float(summary['WEIGHTED_FORECAST'] or 0),
        'at_risk_value': float(summary['AT_RISK_VALUE'] or 0),
        'stage_forecasts': map_stage_forecasts(stage_rows),
        'historical_revenue': historical_revenue,
        'weights_fallback_count': int(summary['WEIGHTS_FALLBACK_COUNT'] or 0),
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
        ('Total pipeline', metrics['total_pipeline']),
        ('At risk (>90d)', -metrics['at_risk_value']),
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
        FROM fct_opportunities
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
