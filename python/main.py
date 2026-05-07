import sys
import uuid
from datetime import datetime
from pathlib import Path
from clients.asana_client import AsanaClient
from clients.slack_client import SlackClient
from clients.image_host_client import ImageHostClient
from config import settings
from utils.logger import setup_logger
from utils.error_handler import PipelineException
from utils.chart_cleanup import cleanup_old_charts

logger = setup_logger(__name__)

VALID_WORKFLOW_TYPES = ['sales-pipeline-health', 'rep-performance', 'revenue-forecast']

def run_workflow(workflow_type: str, asana_task_gid: str = None, asana_task_url: str = None):
    if workflow_type not in VALID_WORKFLOW_TYPES:
        raise ValueError(f"Invalid workflow type: {workflow_type}. Must be one of {VALID_WORKFLOW_TYPES}")
    
    logger.info(f"Main orchestrator started for workflow: {workflow_type}")
    run_id = f"{workflow_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    try:
        if workflow_type == 'sales-pipeline-health':
            from workflows.pipeline_health import run_workflow as run_pipeline_health
            result = run_pipeline_health(run_id)
        elif workflow_type == 'rep-performance':
            from workflows.rep_performance import run_workflow as run_rep_performance
            result = run_rep_performance(run_id)
        elif workflow_type == 'revenue-forecast':
            from workflows.revenue_forecast import run_workflow as run_revenue_forecast
            result = run_revenue_forecast(run_id)
        else:
            raise ValueError(f"Unknown workflow type: {workflow_type}")
        
        logger.info("Uploading charts and sending Slack notification")
        
        image_urls = []
        try:
            image_host = ImageHostClient()
            chart_paths = [Path(p) for p in result['chart_paths']]
            image_urls = image_host.upload_images(chart_paths)
            logger.info(f"Generated {len(image_urls)} image URLs")
        except Exception as e:
            logger.warning(f"Failed to upload images: {e}")
        
        asana_configured = settings.is_asana_configured()
        asana_skipped_note = None if asana_configured else "Warning: Asana integration not configured - task updates skipped"
        
        slack_client = SlackClient()
        slack_client.send_notification(
            workflow_type=workflow_type,
            metrics=result['metrics'],
            insights=result['insights'],
            asana_task_url=asana_task_url,
            image_urls=image_urls,
            asana_note=asana_skipped_note
        )
        
        if asana_task_gid and asana_configured:
            logger.info("Updating Asana task")
            try:
                asana_client = AsanaClient()
                
                task_info = asana_client.get_task_info(asana_task_gid)
                if task_info and task_info.get('completed'):
                    logger.info(f"Task {asana_task_gid} already completed, skipping update")
                else:
                    for chart_path_str in result['chart_paths']:
                        chart_path = Path(chart_path_str)
                        if chart_path.exists():
                            asana_client.upload_attachment(asana_task_gid, chart_path)
                
                    insights_text = result['insights']
                    insights_list = insights_text.split('\n\n')
                    
                    formatted_insights = []
                    chart_names = ['Chart 1', 'Chart 2', 'Chart 3', 'Chart 4']
                    for i, insight in enumerate(insights_list):
                        if insight.strip():
                            formatted_insights.append(f"[{chart_names[i]}]\n{insight}")
                    
                    comment = f"""Analysis Complete

{workflow_type.replace('-', ' ').title()}
Records: {result['records_processed']} | Run: {run_id[:16]}

See 4 charts attached above. Each insight below corresponds to one chart.

{chr(10).join(formatted_insights)}

Gemini: {result['gemini_stats']['tokens']} tokens (${result['gemini_stats']['cost']:.4f})
Full report with images sent to Slack.
"""
                asana_client.add_comment(asana_task_gid, comment)
                asana_client.move_to_complete(asana_task_gid)
                logger.info("Asana task updated and marked complete")
            except Exception as e:
                logger.warning(f"Failed to update Asana: {str(e)}")
        elif asana_task_gid and not asana_configured:
            logger.warning("Asana task GID provided but Asana not configured - skipping update")
        elif not asana_task_gid and asana_configured:
            logger.info("No Asana task GID provided - skipping Asana update")
        
        cleanup_old_charts(days_to_keep=7)
        logger.info(f"Workflow {workflow_type} completed successfully")
        return result
        
    except Exception as e:
        logger.error(f"Workflow {workflow_type} failed: {str(e)}")
        
        if asana_task_gid and settings.is_asana_configured():
            try:
                asana_client = AsanaClient()
                error_comment = f"""Analysis Failed

{workflow_type.replace('-', ' ').title()}
Run ID: {run_id}

Error: {str(e)}

Check Kestra logs for details.
"""
                asana_client.add_comment(asana_task_gid, error_comment)
            except Exception:
                logger.error("Failed to update Asana with error message")
        
        raise PipelineException(f"Workflow failed: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <workflow_type> [asana_task_gid] [asana_task_url]")
        sys.exit(1)
    
    workflow_type = sys.argv[1]
    asana_task_gid = sys.argv[2] if len(sys.argv) > 2 else None
    asana_task_url = sys.argv[3] if len(sys.argv) > 3 else None
    
    try:
        result = run_workflow(workflow_type, asana_task_gid, asana_task_url)
        print(f"SUCCESS: {result['status']}")
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {str(e)}")
        sys.exit(1)

