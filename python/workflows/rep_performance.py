import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
from pathlib import Path
from datetime import datetime
from typing import Dict, List
import numpy as np
from clients.salesforce_client import SalesforceClient
from clients.snowflake_client import SnowflakeClient
from clients.gemini_client import GeminiClient
from config.prompts import get_prompt
from config import settings
from utils.logger import setup_logger
from workflows._shared import extract_and_load

logger = setup_logger(__name__)

WORKFLOW_TYPE = 'rep-performance'

def run_workflow(run_id: str) -> Dict:
    logger.info(f"Starting rep performance workflow: {run_id}")
    start_time = datetime.now()

    sf_client = SalesforceClient()
    snow_client = SnowflakeClient()

    try:
        opportunities = extract_and_load(sf_client, snow_client, days=90)

        metrics = calculate_metrics(snow_client)
        
        chart_paths = generate_charts(snow_client)
        
        data_summary = build_data_summary(metrics)
        prompt, temperature = get_prompt(WORKFLOW_TYPE, data_summary)
        
        gemini_client = GeminiClient(temperature=temperature)
        insights_result = gemini_client.generate_insights(prompt, chart_paths)
        
        end_time = datetime.now()
        snow_client.log_pipeline_run(
            run_id=run_id,
            workflow_type=WORKFLOW_TYPE,
            asana_task_id='',
            start_time=start_time,
            end_time=end_time,
            status='success',
            records_processed=len(opportunities),
            gemini_tokens=insights_result['total_tokens'],
            gemini_cost=insights_result['cost']
        )
        
        snow_client.close()
        
        logger.info("Rep performance workflow completed successfully")
        
        return {
            'status': 'success',
            'workflow_type': WORKFLOW_TYPE,
            'metrics': metrics,
            'insights': insights_result['insights'],
            'chart_paths': [str(p) for p in chart_paths],
            'gemini_stats': {
                'tokens': insights_result['total_tokens'],
                'cost': insights_result['cost']
            },
            'records_processed': len(opportunities)
        }
        
    except Exception as e:
        logger.error(f"Rep performance workflow failed: {str(e)}")
        end_time = datetime.now()
        snow_client.log_pipeline_run(
            run_id=run_id,
            workflow_type=WORKFLOW_TYPE,
            asana_task_id='',
            start_time=start_time,
            end_time=end_time,
            status='failed',
            records_processed=0,
            error_message=str(e)
        )
        snow_client.close()
        raise

def calculate_metrics(snow_client: SnowflakeClient) -> Dict:
    logger.info("Calculating rep performance metrics")
    
    rep_query = """
        SELECT 
            owner_name,
            COUNT(*) as total_opps,
            SUM(CASE WHEN is_won THEN 1 ELSE 0 END) as won_opps,
            AVG(amount) as avg_deal_size,
            AVG(total_activities) as avg_activities,
            SUM(amount) as total_revenue
        FROM fact_opportunities
        WHERE is_closed
        GROUP BY owner_name
        HAVING COUNT(*) >= 3
        ORDER BY won_opps DESC
    """
    rep_data = snow_client.execute_query(rep_query)
    
    for rep in rep_data:
        total = rep['TOTAL_OPPS']
        won = rep['WON_OPPS']
        rep['close_rate'] = (won / total * 100) if total > 0 else 0
    
    activity_query = """
        SELECT 
            is_won,
            AVG(total_activities) as avg_activities
        FROM fact_opportunities
        WHERE is_closed AND total_activities > 0
        GROUP BY is_won
    """
    activity_data = snow_client.execute_query(activity_query)
    
    won_activities = 0
    lost_activities = 0
    for row in activity_data:
        if row['IS_WON']:
            won_activities = row['AVG_ACTIVITIES']
        else:
            lost_activities = row['AVG_ACTIVITIES']
    
    top_close_rate = max([r['close_rate'] for r in rep_data]) if rep_data else 0
    avg_deal_size = sum([r['AVG_DEAL_SIZE'] for r in rep_data]) / len(rep_data) if rep_data else 0
    avg_activities = sum([r['AVG_ACTIVITIES'] for r in rep_data]) / len(rep_data) if rep_data else 0
    
    metrics = {
        'reps_count': len(rep_data),
        'top_close_rate': top_close_rate,
        'avg_deal_size': avg_deal_size,
        'avg_activities': avg_activities,
        'won_activities': won_activities,
        'lost_activities': lost_activities,
        'rep_breakdown': rep_data
    }
    
    logger.info(f"Calculated metrics for {len(rep_data)} reps")
    return metrics

def generate_charts(snow_client: SnowflakeClient) -> List[Path]:
    logger.info("Generating rep performance charts")
    chart_paths = []
    
    rep_query = """
        SELECT 
            owner_name,
            COUNT(*) as total_opps,
            SUM(CASE WHEN is_won THEN 1 ELSE 0 END) as won_opps
        FROM fact_opportunities
        WHERE is_closed
        GROUP BY owner_name
        HAVING COUNT(*) >= 3
        ORDER BY won_opps DESC
        LIMIT 10
    """
    rep_data = snow_client.execute_query(rep_query)
    
    if rep_data:
        for rep in rep_data:
            total = rep['TOTAL_OPPS']
            won = rep['WON_OPPS']
            rep['close_rate'] = (won / total * 100) if total > 0 else 0
        
        df_reps = pd.DataFrame(rep_data)
        
        plt.figure(figsize=(8, 5))
        plt.bar(df_reps['OWNER_NAME'], df_reps['close_rate'], color='steelblue', width=0.6)
        plt.ylabel('Close Rate (%)')
        plt.xlabel('Sales Rep')
        plt.title('Close Rate by Rep')
        plt.ylim(0, 110)
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        path = settings.OUTPUT_DIR / f'rep_performance_close_rate_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
        plt.savefig(path, dpi=100, bbox_inches='tight')
        plt.close()
        chart_paths.append(path)
        logger.info(f"Chart 1 saved: {path.name}")
    
    deal_query = """
        SELECT 
            owner_name,
            AVG(amount) as avg_deal_size
        FROM fact_opportunities
        WHERE is_won AND amount > 0
        GROUP BY owner_name
        HAVING COUNT(*) >= 2
        ORDER BY avg_deal_size DESC
        LIMIT 10
    """
    deal_data = snow_client.execute_query(deal_query)
    
    if deal_data:
        df_deals = pd.DataFrame(deal_data)
        
        plt.figure(figsize=(8, 5))
        plt.bar(df_deals['OWNER_NAME'], df_deals['AVG_DEAL_SIZE'], color='coral', width=0.6)
        plt.ylabel('Average Deal Size ($)')
        plt.xlabel('Sales Rep')
        plt.title('Average Deal Size by Rep')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        path = settings.OUTPUT_DIR / f'rep_performance_deal_size_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
        plt.savefig(path, dpi=100, bbox_inches='tight')
        plt.close()
        chart_paths.append(path)
        logger.info(f"Chart 2 saved: {path.name}")
    
    activity_query = """
        SELECT 
            total_activities,
            CASE WHEN is_won THEN 1 ELSE 0 END as won
        FROM fact_opportunities
        WHERE is_closed AND total_activities > 0
        LIMIT 200
    """
    activity_data = snow_client.execute_query(activity_query)
    
    if activity_data:
        df_activity = pd.DataFrame(activity_data)
        
        plt.figure(figsize=(10, 6))
        won_df = df_activity[df_activity['WON'] == 1]
        lost_df = df_activity[df_activity['WON'] == 0]
        
        plt.scatter(won_df['TOTAL_ACTIVITIES'], [1]*len(won_df), alpha=0.6, c='green', label='Won', s=50)
        plt.scatter(lost_df['TOTAL_ACTIVITIES'], [0]*len(lost_df), alpha=0.6, c='red', label='Lost', s=50)
        
        if len(won_df) > 0:
            z = np.polyfit(df_activity['TOTAL_ACTIVITIES'], df_activity['WON'], 1)
            p = np.poly1d(z)
            plt.plot(df_activity['TOTAL_ACTIVITIES'].sort_values(), 
                    p(df_activity['TOTAL_ACTIVITIES'].sort_values()), 
                    "k--", alpha=0.5, label='Trend')
        
        plt.xlabel('Number of Activities')
        plt.ylabel('Outcome')
        plt.title('Activities vs Deal Outcome')
        plt.yticks([0, 1], ['Lost', 'Won'])
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        path = settings.OUTPUT_DIR / f'rep_performance_activities_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
        plt.savefig(path, dpi=100, bbox_inches='tight')
        plt.close()
        chart_paths.append(path)
        logger.info(f"Chart 3 saved: {path.name}")
    
    won_lost_query = """
        SELECT 
            CASE WHEN is_won THEN 'Won' ELSE 'Lost' END as outcome,
            total_activities
        FROM fact_opportunities
        WHERE is_closed AND total_activities > 0
    """
    won_lost_data = snow_client.execute_query(won_lost_query)
    
    if won_lost_data:
        df_wl = pd.DataFrame(won_lost_data)
        
        plt.figure(figsize=(10, 6))
        df_wl.boxplot(column='TOTAL_ACTIVITIES', by='OUTCOME', grid=False)
        plt.xlabel('Outcome')
        plt.ylabel('Number of Activities')
        plt.title('Activity Distribution: Won vs Lost Deals')
        plt.suptitle('')
        plt.tight_layout()
        path = settings.OUTPUT_DIR / f'rep_performance_distribution_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
        plt.savefig(path, dpi=100, bbox_inches='tight')
        plt.close()
        chart_paths.append(path)
        logger.info(f"Chart 4 saved: {path.name}")
    
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
        summary += f"\n{i+1}. {rep['OWNER_NAME']}: {rep['close_rate']:.1f}% close rate, "
        summary += f"${rep['AVG_DEAL_SIZE']:,.0f} avg deal, "
        summary += f"{rep['AVG_ACTIVITIES']:.1f} avg activities"
    
    return summary

