import matplotlib
matplotlib.use('Agg')

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime
from typing import Dict, List

from clients.salesforce_client import SalesforceClient
from clients.snowflake_client import SnowflakeClient
from config import settings
from utils.logger import setup_logger
from workflows._shared import extract_and_load, generate_optional_commentary, run_dbt_transform

logger = setup_logger(__name__)

WORKFLOW_TYPE = 'rep-performance'


def run_workflow(run_id: str) -> Dict:
    logger.info(f"Starting rep performance workflow: {run_id}")
    start_time = datetime.now()

    sf_client = SalesforceClient()
    snow_client = SnowflakeClient()

    try:
        opportunities = extract_and_load(sf_client, snow_client, days=90)
        run_dbt_transform()

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
        logger.error(f"Rep performance workflow failed: {e}")
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
    rep_data = snow_client.execute_query("""
        SELECT
            owner_name,
            total_opps,
            won_opps,
            avg_deal_size,
            avg_activities,
            total_revenue,
            close_rate_pct
        FROM fct_rep_performance
        ORDER BY won_opps DESC
    """)

    for rep in rep_data:
        rep['close_rate'] = float(rep['CLOSE_RATE_PCT'] or 0)

    activity_data = snow_client.execute_query("""
        SELECT
            is_won,
            AVG(total_activities) AS avg_activities
        FROM fct_opportunities
        WHERE is_closed AND total_activities > 0
        GROUP BY is_won
    """)

    won_activities = 0.0
    lost_activities = 0.0
    for row in activity_data:
        if row['IS_WON']:
            won_activities = float(row['AVG_ACTIVITIES'] or 0)
        else:
            lost_activities = float(row['AVG_ACTIVITIES'] or 0)

    top_close_rate = max((r['close_rate'] for r in rep_data), default=0)
    avg_deal_size = (
        sum(r['AVG_DEAL_SIZE'] or 0 for r in rep_data) / len(rep_data)
        if rep_data else 0
    )
    avg_activities = (
        sum(r['AVG_ACTIVITIES'] or 0 for r in rep_data) / len(rep_data)
        if rep_data else 0
    )

    return {
        'reps_count': len(rep_data),
        'top_close_rate': top_close_rate,
        'avg_deal_size': avg_deal_size,
        'avg_activities': avg_activities,
        'won_activities': won_activities,
        'lost_activities': lost_activities,
        'rep_breakdown': rep_data,
    }


def generate_charts(snow_client: SnowflakeClient) -> List[Path]:
    chart_paths: List[Path] = []
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    out = settings.OUTPUT_DIR

    rep_data = snow_client.execute_query("""
        SELECT owner_name, total_opps, won_opps, close_rate_pct
        FROM fct_rep_performance
        ORDER BY won_opps DESC
        LIMIT 10
    """)

    if rep_data:
        df_reps = pd.DataFrame(rep_data)
        df_reps['CLOSE_RATE'] = df_reps['CLOSE_RATE_PCT'].astype(float)

        plt.figure(figsize=(8, 5))
        plt.bar(df_reps['OWNER_NAME'], df_reps['CLOSE_RATE'], color='steelblue', width=0.6)
        plt.ylabel('Close Rate (%)')
        plt.xlabel('Sales Rep')
        plt.title('Close Rate by Rep')
        plt.ylim(0, 110)
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        path = out / f'rep_performance_close_rate_{ts}.png'
        plt.savefig(path, dpi=100, bbox_inches='tight')
        plt.close()
        chart_paths.append(path)

    deal_data = snow_client.execute_query("""
        SELECT owner_name, avg_deal_size
        FROM fct_rep_performance
        WHERE won_opps >= 2 AND avg_deal_size > 0
        ORDER BY avg_deal_size DESC
        LIMIT 10
    """)

    if deal_data:
        df_deals = pd.DataFrame(deal_data)
        plt.figure(figsize=(8, 5))
        plt.bar(df_deals['OWNER_NAME'], df_deals['AVG_DEAL_SIZE'], color='coral', width=0.6)
        plt.ylabel('Average Deal Size ($)')
        plt.xlabel('Sales Rep')
        plt.title('Average Deal Size by Rep')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        path = out / f'rep_performance_deal_size_{ts}.png'
        plt.savefig(path, dpi=100, bbox_inches='tight')
        plt.close()
        chart_paths.append(path)

    activity_data = snow_client.execute_query("""
        SELECT total_activities, CASE WHEN is_won THEN 1 ELSE 0 END AS won
        FROM fct_opportunities
        WHERE is_closed AND total_activities > 0
        LIMIT 200
    """)

    if activity_data:
        df_activity = pd.DataFrame(activity_data)
        plt.figure(figsize=(10, 6))
        won_df = df_activity[df_activity['WON'] == 1]
        lost_df = df_activity[df_activity['WON'] == 0]

        plt.scatter(won_df['TOTAL_ACTIVITIES'], [1] * len(won_df),
                    alpha=0.6, c='green', label='Won', s=50)
        plt.scatter(lost_df['TOTAL_ACTIVITIES'], [0] * len(lost_df),
                    alpha=0.6, c='red', label='Lost', s=50)

        if len(won_df) > 0:
            z = np.polyfit(df_activity['TOTAL_ACTIVITIES'], df_activity['WON'], 1)
            p = np.poly1d(z)
            xs = df_activity['TOTAL_ACTIVITIES'].sort_values()
            plt.plot(xs, p(xs), 'k--', alpha=0.5, label='Trend')

        plt.xlabel('Number of Activities')
        plt.ylabel('Outcome')
        plt.title('Activities vs Deal Outcome')
        plt.yticks([0, 1], ['Lost', 'Won'])
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        path = out / f'rep_performance_activities_{ts}.png'
        plt.savefig(path, dpi=100, bbox_inches='tight')
        plt.close()
        chart_paths.append(path)

    won_lost_data = snow_client.execute_query("""
        SELECT
            CASE WHEN is_won THEN 'Won' ELSE 'Lost' END AS outcome,
            total_activities
        FROM fct_opportunities
        WHERE is_closed AND total_activities > 0
    """)

    if won_lost_data:
        df_wl = pd.DataFrame(won_lost_data)
        plt.figure(figsize=(10, 6))
        df_wl.boxplot(column='TOTAL_ACTIVITIES', by='OUTCOME', grid=False)
        plt.xlabel('Outcome')
        plt.ylabel('Number of Activities')
        plt.title('Activity Distribution: Won vs Lost Deals')
        plt.suptitle('')
        plt.tight_layout()
        path = out / f'rep_performance_distribution_{ts}.png'
        plt.savefig(path, dpi=100, bbox_inches='tight')
        plt.close()
        chart_paths.append(path)

    return chart_paths


def build_data_summary(metrics: Dict) -> str:
    summary = f"""
Total Reps Analyzed: {metrics['reps_count']}
Top Close Rate: {metrics['top_close_rate']:.1f}%
Average Deal Size: ${metrics['avg_deal_size']:,.0f}
Average Activities per Opp: {metrics['avg_activities']:.1f}

ACTIVITY COMPARISON:
Won Deals: Average {metrics['won_activities']:.1f} activities
Lost Deals: Average {metrics['lost_activities']:.1f} activities

TOP PERFORMERS:
"""

    for i, rep in enumerate(metrics['rep_breakdown'][:5]):
        summary += (
            f"\n{i + 1}. {rep['OWNER_NAME']}: {rep['close_rate']:.1f}% close rate, "
            f"${rep['AVG_DEAL_SIZE']:,.0f} avg deal, "
            f"{rep['AVG_ACTIVITIES']:.1f} avg activities"
        )

    return summary
