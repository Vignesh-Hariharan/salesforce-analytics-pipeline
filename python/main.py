import sys
import uuid
from datetime import datetime
from pathlib import Path
from clients.asana_client import AsanaClient
from clients.slack_client import SlackClient
from clients.image_host_client import ImageHostClient
from utils.logger import setup_logger
from utils.error_handler import PipelineException

logger = setup_logger(__name__)

def run_workflow(workflow_type: str, asana_task_gid: str = None, asana_task_url: str = None):
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
        except Exception as e:
            logger.warning(f"Failed to upload images: {e}")
        
        slack_client = SlackClient()
        slack_client.send_notification(
            workflow_type=workflow_type,
            metrics=result['metrics'],
            insights=result['insights'],
            asana_task_url=asana_task_url,
            image_urls=image_urls
        )
        
        if asana_task_gid:
            logger.info("Updating Asana task")
            asana_client = AsanaClient()
            
            for chart_path_str in result['chart_paths']:
                chart_path = Path(chart_path_str)
                if chart_path.exists():
                    asana_client.upload_attachment(asana_task_gid, chart_path)
            
            comment = f"""
Pipeline Execution Complete

Workflow: {workflow_type}
Run ID: {run_id}
Status: Success
Records Processed: {result['records_processed']}
Gemini Tokens Used: {result['gemini_stats']['tokens']}
Cost: ${result['gemini_stats']['cost']:.4f}

AI INSIGHTS:
{result['insights']}
"""
            asana_client.add_comment(asana_task_gid, comment)
            asana_client.move_to_complete(asana_task_gid)
            logger.info("Asana task updated and marked complete")
        
        logger.info(f"Workflow {workflow_type} completed successfully")
        return result
        
    except Exception as e:
        logger.error(f"Workflow {workflow_type} failed: {str(e)}")
        
        if asana_task_gid:
            try:
                asana_client = AsanaClient()
                error_comment = f"""
Pipeline Execution Failed

Workflow: {workflow_type}
Run ID: {run_id}
Error: {str(e)}

Please check the logs for more details.
"""
                asana_client.add_comment(asana_task_gid, error_comment)
            except:
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

