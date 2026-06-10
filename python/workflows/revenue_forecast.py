import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List
from clients.salesforce_client import SalesforceClient
from clients.snowflake_client import SnowflakeClient
from clients.gemini_client import GeminiClient
from config.prompts import get_prompt
from config import settings
from utils.logger import setup_logger

logger = setup_logger(__name__)

WORKFLOW_TYPE = 'revenue-forecast'

STAGE_WEIGHTS = {
    'Prospecting': 0.10,
    'Qualification': 0.25,
    'Needs Analysis': 0.40,
    'Proposal': 0.60,
    'Negotiation': 0.80,
    'Closed Won': 1.0
}

def run_workflow(run_id: str) -> Dict:
    logger.info(f"Starting revenue forecast workflow: {run_id}")
    start_time = datetime.now()
    
    sf_client = SalesforceClient()
    snow_client = SnowflakeClient()
    
    try:
        opportunities = sf_client.get_opportunities(days=90)
        if not opportunities:
            logger.warning("No opportunities found in Salesforce for the last 90 days")
            raise ValueError("No opportunities found in Salesforce")
        
        valid_opps = [o for o in opportunities if o.get('opportunity_id') and o.get('opportunity_name')]
        if len(valid_opps) < len(opportunities):
            logger.warning(f"Filtered out {len(opportunities) - len(valid_opps)} invalid opportunities")
        opportunities = valid_opps
        
        if not opportunities:
            raise ValueError("No valid opportunities found after data validation")
        
        opp_ids = [o['opportunity_id'] for o in opportunities]
        activities = sf_client.get_activities(opp_ids)
        
        activity_counts = {}
        for act in activities:
            opp_id = act['opportunity_id']
            activity_counts[opp_id] = activity_counts.get(opp_id, 0) + 1
        
        for opp in opportunities:
            opp_id = opp['opportunity_id']
            opp['total_activities'] = activity_counts.get(opp_id, 0)
            
            if opp['created_date']:
                created = pd.to_datetime(opp['created_date'])
                if opp['close_date']:
                    closed = pd.to_datetime(opp['close_date'])
                    opp['days_to_close'] = (closed - created).days
                    opp['days_open'] = (closed - created).days
                else:
                    opp['days_to_close'] = None
                    opp['days_open'] = (datetime.now() - created).days
            else:
                opp['days_to_close'] = None
                opp['days_open'] = None
        
        snow_client.load_opportunities(opportunities)
        snow_client.load_activities(activities)
        
        metrics = calculate_metrics(snow_client)
        
        chart_paths = generate_charts(snow_client, metrics)
        
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
        
        logger.info("Revenue forecast workflow completed successfully")
        
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
        logger.error(f"Revenue forecast workflow failed: {str(e)}")
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
    logger.info("Calculating revenue forecast metrics")
    
    pipeline_query = """
        SELECT 
            SUM(amount) as total_pipeline,
            COUNT(*) as open_opps
        FROM fact_opportunities
        WHERE NOT is_closed AND amount > 0
    """
    pipeline_result = snow_client.execute_query(pipeline_query)
    total_pipeline = float(pipeline_result[0].get('TOTAL_PIPELINE', 0)) if pipeline_result and pipeline_result[0].get('TOTAL_PIPELINE') else 0.0
    open_opps = int(pipeline_result[0].get('OPEN_OPPS', 0)) if pipeline_result else 0
    
    stage_query = """
        SELECT 
            stage_name,
            SUM(amount) as stage_value,
            COUNT(*) as count
        FROM fact_opportunities
        WHERE NOT is_closed AND amount > 0
        GROUP BY stage_name
    """
    stage_data = snow_client.execute_query(stage_query)
    
    weighted_forecast = 0
    stage_forecasts = []
    for stage in stage_data:
        stage_name = stage['STAGE_NAME']
        stage_value = float(stage['STAGE_VALUE']) if stage['STAGE_VALUE'] else 0.0
        weight = STAGE_WEIGHTS.get(stage_name, 0.25)
        weighted_value = stage_value * weight
        weighted_forecast += weighted_value
        
        stage_forecasts.append({
            'stage': stage_name,
            'value': stage_value,
            'weight': weight,
            'weighted_value': weighted_value
        })
    
    closed_query = """
        SELECT 
            DATE_TRUNC('month', close_date) as month,
            SUM(amount) as revenue
        FROM fact_opportunities
        WHERE is_won AND close_date >= DATEADD(month, -6, CURRENT_DATE())
        GROUP BY month
        ORDER BY month
    """
    closed_data = snow_client.execute_query(closed_query)
    
    at_risk_query = """
        SELECT SUM(amount) as at_risk_value
        FROM fact_opportunities
        WHERE NOT is_closed AND days_open > 90
    """
    at_risk_result = snow_client.execute_query(at_risk_query)
    at_risk_value = float(at_risk_result[0].get('AT_RISK_VALUE', 0)) if at_risk_result and at_risk_result[0].get('AT_RISK_VALUE') else 0.0
    
    confidence = 75 if weighted_forecast > 0 else 0
    
    metrics = {
        'total_pipeline': total_pipeline or 0,
        'open_opps': open_opps,
        'weighted_forecast': weighted_forecast,
        'confidence': confidence,
        'at_risk_value': at_risk_value or 0,
        'stage_forecasts': stage_forecasts,
        'historical_revenue': closed_data
    }
    
    logger.info(f"Forecast: ${weighted_forecast:,.0f} from ${total_pipeline:,.0f} pipeline")
    return metrics

def generate_charts(snow_client: SnowflakeClient, metrics: Dict) -> List[Path]:
    logger.info("Generating revenue forecast charts")
    chart_paths = []
    
    waterfall_data = [
        ('Total Pipeline', metrics['total_pipeline']),
        ('At Risk', -metrics['at_risk_value']),
        ('Weighted Forecast', metrics['weighted_forecast'])
    ]
    
    plt.figure(figsize=(10, 6))
    values = [waterfall_data[0][1], waterfall_data[1][1], waterfall_data[2][1]]
    colors = ['steelblue', 'coral', 'seagreen']
    plt.bar(range(len(waterfall_data)), values, color=colors, alpha=0.7)
    
    for i, (label, value) in enumerate(waterfall_data):
        plt.text(i, value, f'${abs(value):,.0f}', ha='center', va='bottom' if value > 0 else 'top')
    
    plt.xticks(range(len(waterfall_data)), [d[0] for d in waterfall_data])
    plt.ylabel('Value ($)')
    plt.title('Revenue Waterfall')
    plt.tight_layout()
    path = settings.OUTPUT_DIR / f'revenue_forecast_waterfall_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
    plt.savefig(path, dpi=100, bbox_inches='tight')
    plt.close()
    chart_paths.append(path)
    logger.info(f"Chart 1 saved: {path.name}")
    
    if metrics['stage_forecasts']:
        df_stages = pd.DataFrame(metrics['stage_forecasts'])
        
        plt.figure(figsize=(10, 6))
        plt.barh(df_stages['stage'], df_stages['weight'] * 100, color='mediumpurple')
        plt.xlabel('Probability Weight (%)')
        plt.ylabel('Stage')
        plt.title('Stage Probability Weights')
        plt.xlim(0, 100)
        plt.tight_layout()
        path = settings.OUTPUT_DIR / f'revenue_forecast_weights_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
        plt.savefig(path, dpi=100, bbox_inches='tight')
        plt.close()
        chart_paths.append(path)
        logger.info(f"Chart 2 saved: {path.name}")
    
    if metrics['historical_revenue']:
        df_hist = pd.DataFrame(metrics['historical_revenue'])
        df_hist['MONTH'] = pd.to_datetime(df_hist['MONTH']).dt.strftime('%b')
        df_hist['REVENUE'] = df_hist['REVENUE'].apply(lambda x: float(x) if x else 0.0)
        
        plt.figure(figsize=(10, 6))
        plt.plot(df_hist['MONTH'], df_hist['REVENUE'], marker='o', linewidth=2, color='steelblue', label='Actual')
        
        forecast_month = (datetime.now() + timedelta(days=30)).strftime('%b')
        forecast_value = metrics['weighted_forecast']
        plt.scatter([forecast_month], [forecast_value], color='coral', s=100, label='Forecast', zorder=5)
        
        plt.xlabel('Month')
        plt.ylabel('Revenue ($)')
        plt.title('Monthly Revenue Trend with Forecast')
        plt.legend()
        plt.xticks(rotation=45)
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        path = settings.OUTPUT_DIR / f'revenue_forecast_trend_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
        plt.savefig(path, dpi=100, bbox_inches='tight')
        plt.close()
        chart_paths.append(path)
        logger.info(f"Chart 3 saved: {path.name}")
    
    age_query = """
        SELECT days_open
        FROM fact_opportunities
        WHERE NOT is_closed AND days_open IS NOT NULL
    """
    age_data = snow_client.execute_query(age_query)
    
    if age_data:
        df_age = pd.DataFrame(age_data)
        
        plt.figure(figsize=(10, 6))
        plt.hist(df_age['DAYS_OPEN'], bins=20, color='seagreen', alpha=0.7, edgecolor='black')
        plt.axvline(x=90, color='red', linestyle='--', label='At Risk (>90 days)')
        plt.xlabel('Days Open')
        plt.ylabel('Number of Opportunities')
        plt.title('Pipeline Age Distribution')
        plt.legend()
        plt.tight_layout()
        path = settings.OUTPUT_DIR / f'revenue_forecast_age_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png'
        plt.savefig(path, dpi=100, bbox_inches='tight')
        plt.close()
        chart_paths.append(path)
        logger.info(f"Chart 4 saved: {path.name}")
    
    return chart_paths

def build_data_summary(metrics: Dict) -> str:
    summary = f"""
Total Pipeline Value: ${metrics['total_pipeline']:,.0f}
Open Opportunities: {metrics['open_opps']}
Weighted Forecast: ${metrics['weighted_forecast']:,.0f}
Forecast Confidence: {metrics['confidence']:.0f}%
At Risk Value (>90 days): ${metrics['at_risk_value']:,.0f}

STAGE BREAKDOWN WITH WEIGHTS:
"""
    
    for stage in metrics['stage_forecasts']:
        summary += f"\n{stage['stage']}: ${stage['value']:,.0f} "
        summary += f"(weight: {stage['weight']*100:.0f}% = ${stage['weighted_value']:,.0f})"
    
    if metrics['historical_revenue']:
        summary += "\n\nHISTORICAL REVENUE (Last 6 Months):"
        for month_data in metrics['historical_revenue'][-3:]:
            month = pd.to_datetime(month_data['MONTH']).strftime('%b %Y')
            revenue = month_data['REVENUE']
            summary += f"\n{month}: ${revenue:,.0f}"
    
    return summary

