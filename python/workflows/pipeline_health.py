import matplotlib
matplotlib.use('Agg')

from datetime import datetime
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import pandas as pd

from clients.salesforce_client import SalesforceClient
from clients.snowflake_client import SnowflakeClient
from config import settings
from utils.logger import setup_logger
from workflows._shared import chart_path, extract_and_load, generate_optional_commentary

logger = setup_logger(__name__)

WORKFLOW_TYPE = 'sales-pipeline-health'


def run_workflow(run_id: str) -> Dict:
    logger.info(f"Starting pipeline health workflow: {run_id}")
    start_time = datetime.now()

    sf_client = SalesforceClient()
    snow_client = SnowflakeClient()

    try:
        opportunities = extract_and_load(sf_client, snow_client, days=90)

        metrics = calculate_metrics(snow_client)
        chart_paths = generate_charts(snow_client)

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
        logger.error(f"Pipeline health workflow failed: {e}")
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


def calculate_metrics(snow_client: SnowflakeClient) -> Dict:
    summary = snow_client.execute_query("""
        SELECT
            COUNT(*)                                             AS total_opportunities,
            SUM(CASE WHEN is_won THEN 1 ELSE 0 END)              AS closed_won,
            SUM(CASE WHEN is_closed AND NOT is_won THEN 1 ELSE 0 END) AS closed_lost,
            AVG(CASE WHEN is_closed THEN days_to_close END)      AS avg_days_to_close,
            SUM(CASE WHEN NOT is_closed THEN amount ELSE 0 END)  AS pipeline_value,
            AVG(amount)                                          AS avg_deal_size
        FROM fact_opportunities
    """)[0]

    stage_breakdown = snow_client.execute_query("""
        SELECT stage_name,
               COUNT(*)         AS count,
               AVG(days_open)   AS avg_days_in_stage,
               SUM(amount)      AS stage_value
        FROM fact_opportunities
        WHERE NOT is_closed
        GROUP BY stage_name
        ORDER BY count DESC
    """)

    total = summary['TOTAL_OPPORTUNITIES'] or 0
    won = summary['CLOSED_WON'] or 0
    close_rate = (won / total * 100) if total else 0.0

    return {
        'total_opportunities': total,
        'closed_won': won,
        'closed_lost': summary['CLOSED_LOST'] or 0,
        'close_rate': close_rate,
        'avg_days_to_close': summary['AVG_DAYS_TO_CLOSE'] or 0,
        'pipeline_value': summary['PIPELINE_VALUE'] or 0,
        'avg_deal_size': summary['AVG_DEAL_SIZE'] or 0,
        'stage_breakdown': stage_breakdown,
    }


def generate_charts(snow_client: SnowflakeClient) -> List[Path]:
    out = settings.OUTPUT_DIR
    paths: List[Path] = []

    paths.extend(_chart_stage_distribution(snow_client, out))
    paths.extend(_chart_stage_conversion(snow_client, out))
    paths.extend(_chart_time_in_stage(snow_client, out))
    paths.extend(_chart_weekly_trend(snow_client, out))

    return paths


def _chart_stage_distribution(snow_client: SnowflakeClient, out: Path) -> List[Path]:
    rows = snow_client.execute_query("""
        SELECT stage_name, COUNT(*) AS count
        FROM fact_opportunities
        WHERE NOT is_closed
        GROUP BY stage_name
        ORDER BY count DESC
    """)
    if not rows:
        return []
    df = pd.DataFrame(rows)

    plt.figure(figsize=(8, 5))
    plt.bar(df['STAGE_NAME'], df['COUNT'], color='steelblue', width=0.6)
    plt.ylabel('Open opportunities')
    plt.xlabel('Stage')
    plt.title('Open opportunities by stage')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    path = chart_path('pipeline_health_stages', out)
    plt.savefig(path, dpi=100, bbox_inches='tight')
    plt.close()
    return [path]


def _chart_stage_conversion(snow_client: SnowflakeClient, out: Path) -> List[Path]:
    """True funnel conversion derived from OpportunityHistory.

    For each stage, compute the share of opportunities that ever entered
    that stage *and* also entered the next stage in the configured order.
    """
    rows = snow_client.execute_query("""
        WITH reached AS (
            SELECT DISTINCT opportunity_id, stage_name
            FROM dim_stage_history
        ),
        ordered AS (
            SELECT s.position, s.stage_name, COUNT(DISTINCT r.opportunity_id) AS reached_count
            FROM (
                SELECT 1 AS position, 'Prospecting'   AS stage_name UNION ALL
                SELECT 2, 'Qualification'             UNION ALL
                SELECT 3, 'Needs Analysis'            UNION ALL
                SELECT 4, 'Proposal'                  UNION ALL
                SELECT 5, 'Negotiation'               UNION ALL
                SELECT 6, 'Closed Won'
            ) s
            LEFT JOIN reached r ON r.stage_name = s.stage_name
            GROUP BY s.position, s.stage_name
        )
        SELECT position, stage_name, reached_count
        FROM ordered
        ORDER BY position
    """)
    if not rows:
        logger.info("No stage history available; skipping conversion chart")
        return []

    df = pd.DataFrame(rows).sort_values('POSITION').reset_index(drop=True)
    df['NEXT_REACHED'] = df['REACHED_COUNT'].shift(-1)
    df['CONVERSION_PCT'] = (df['NEXT_REACHED'] / df['REACHED_COUNT'].replace(0, pd.NA) * 100).round(1)

    plot_df = df.dropna(subset=['CONVERSION_PCT'])
    if plot_df.empty:
        return []

    labels = [f"{a} → {b}" for a, b in zip(plot_df['STAGE_NAME'], df['STAGE_NAME'].shift(-1).dropna())]

    plt.figure(figsize=(9, 5))
    bars = plt.bar(labels, plot_df['CONVERSION_PCT'], color='coral', width=0.6)
    for bar, value in zip(bars, plot_df['CONVERSION_PCT']):
        plt.text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                 f"{value:.0f}%", ha='center', va='bottom', fontsize=9)
    plt.ylabel('Conversion to next stage (%)')
    plt.xlabel('Stage transition')
    plt.title('Stage-to-stage conversion (from OpportunityHistory)')
    plt.ylim(0, max(110, plot_df['CONVERSION_PCT'].max() + 10))
    plt.xticks(rotation=30, ha='right')
    plt.tight_layout()
    path = chart_path('pipeline_health_conversions', out)
    plt.savefig(path, dpi=100, bbox_inches='tight')
    plt.close()
    return [path]


def _chart_time_in_stage(snow_client: SnowflakeClient, out: Path) -> List[Path]:
    """Average days an opportunity sits in each stage, computed from
    consecutive OpportunityHistory rows ordered by entered_at."""
    rows = snow_client.execute_query("""
        WITH ordered AS (
            SELECT
                opportunity_id,
                stage_name,
                entered_at,
                LEAD(entered_at) OVER (
                    PARTITION BY opportunity_id ORDER BY entered_at
                ) AS next_entered_at
            FROM dim_stage_history
        )
        SELECT stage_name,
               AVG(DATEDIFF('day', entered_at, COALESCE(next_entered_at, CURRENT_TIMESTAMP())))
                   AS avg_days
        FROM ordered
        GROUP BY stage_name
        ORDER BY avg_days DESC
    """)
    if not rows:
        return []

    df = pd.DataFrame(rows)
    plt.figure(figsize=(10, 6))
    plt.bar(df['STAGE_NAME'], df['AVG_DAYS'], color='mediumpurple')
    plt.ylabel('Average days in stage')
    plt.xlabel('Stage')
    plt.title('Average time per stage')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    path = chart_path('pipeline_health_time', out)
    plt.savefig(path, dpi=100, bbox_inches='tight')
    plt.close()
    return [path]


def _chart_weekly_trend(snow_client: SnowflakeClient, out: Path) -> List[Path]:
    rows = snow_client.execute_query("""
        SELECT DATE_TRUNC('week', created_date) AS week_start,
               COUNT(*)                          AS opportunities
        FROM fact_opportunities
        WHERE created_date IS NOT NULL
          AND created_date >= DATEADD(week, -12, CURRENT_DATE())
        GROUP BY week_start
        ORDER BY week_start
    """)
    if not rows:
        return []

    df = pd.DataFrame(rows)
    df['LABEL'] = pd.to_datetime(df['WEEK_START']).dt.strftime('%m/%d')

    plt.figure(figsize=(10, 6))
    plt.plot(df['LABEL'], df['OPPORTUNITIES'], marker='o', linewidth=2, color='seagreen')
    plt.ylabel('New opportunities created')
    plt.xlabel('Week')
    plt.title('Weekly pipeline trend (last 12 weeks)')
    plt.xticks(rotation=45, ha='right')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    path = chart_path('pipeline_health_trend', out)
    plt.savefig(path, dpi=100, bbox_inches='tight')
    plt.close()
    return [path]


def build_data_summary(metrics: Dict) -> str:
    lines = [
        f"Total Opportunities: {metrics['total_opportunities']}",
        f"Closed Won: {metrics['closed_won']}",
        f"Closed Lost: {metrics['closed_lost']}",
        f"Close Rate: {metrics['close_rate']:.1f}%",
        f"Average Days to Close: {metrics['avg_days_to_close']:.0f} days",
        f"Pipeline Value: ${metrics['pipeline_value']:,.0f}",
        f"Average Deal Size: ${metrics['avg_deal_size']:,.0f}",
        "",
        "STAGE BREAKDOWN:",
    ]
    for s in metrics['stage_breakdown']:
        lines.append(
            f"{s['STAGE_NAME']}: {s['COUNT']} opportunities, "
            f"avg {(s['AVG_DAYS_IN_STAGE'] or 0):.0f} days, "
            f"${(s['STAGE_VALUE'] or 0):,.0f} value"
        )
    return "\n".join(lines)
