import argparse
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
import os

from clients.asana_client import AsanaClient
from clients.slack_client import SlackClient
from config import settings
from utils.chart_cleanup import cleanup_old_charts
from utils.error_handler import PipelineException
from utils.logger import setup_logger

logger = setup_logger(__name__)

VALID_WORKFLOW_TYPES = ('sales-pipeline-health', 'rep-performance', 'revenue-forecast')


def run_workflow(workflow_type: str,
                 asana_task_gid: Optional[str] = None,
                 asana_task_url: Optional[str] = None):
    if workflow_type not in VALID_WORKFLOW_TYPES:
        raise ValueError(
            f"Invalid workflow type: {workflow_type!r}. "
            f"Must be one of {VALID_WORKFLOW_TYPES}"
        )

    run_id = f"{workflow_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    logger.info(f"Orchestrator starting: {workflow_type} ({run_id})")

    try:
        result = _dispatch(workflow_type, run_id)

        SlackClient().send_notification(
            workflow_type=workflow_type,
            metrics=result['metrics'],
            insights=result['insights'],
            asana_task_url=asana_task_url,
            asana_note=None if settings.is_asana_configured()
                      else 'Asana integration not configured — task updates skipped.',
        )

        if asana_task_gid:
            _update_asana_task(asana_task_gid, workflow_type, run_id, result)

        cleanup_old_charts(days_to_keep=7)
        logger.info(f"Workflow {workflow_type} completed")
        return result

    except Exception as e:
        logger.error(f"Workflow {workflow_type} failed: {e}")
        if asana_task_gid and settings.is_asana_configured():
            _post_asana_failure(asana_task_gid, workflow_type, run_id, str(e))
        raise PipelineException(f"Workflow failed: {e}") from e


def _dispatch(workflow_type: str, run_id: str):
    if workflow_type == 'sales-pipeline-health':
        from workflows.pipeline_health import run_workflow as run
    elif workflow_type == 'rep-performance':
        from workflows.rep_performance import run_workflow as run
    elif workflow_type == 'revenue-forecast':
        from workflows.revenue_forecast import run_workflow as run
    else:
        raise ValueError(f"Unknown workflow type: {workflow_type!r}")
    return run(run_id)


def _update_asana_task(task_gid: str, workflow_type: str, run_id: str, result: dict) -> None:
    if not settings.is_asana_configured():
        logger.warning("Asana task GID provided but Asana not configured")
        return

    try:
        client = AsanaClient()
        info = client.get_task_info(task_gid)
        if info and info.get('completed'):
            logger.info(f"Asana task {task_gid} already complete; skipping update")
            return

        for chart_path_str in result['chart_paths']:
            chart_path = Path(chart_path_str)
            if chart_path.exists():
                client.upload_attachment(task_gid, chart_path)

        client.add_comment(task_gid, _build_asana_comment(workflow_type, run_id, result))
        client.move_to_complete(task_gid)
        logger.info(f"Asana task {task_gid} updated and marked complete")
    except Exception as e:
        # Asana failures shouldn't fail the whole pipeline; we've already
        # delivered to Slack and logged to Snowflake.
        logger.warning(f"Failed to update Asana task {task_gid}: {e}")


def _build_asana_comment(workflow_type: str, run_id: str, result: dict) -> str:
    lines = [
        "Analysis complete",
        "",
        workflow_type.replace('-', ' ').title(),
        f"Records: {result['records_processed']} | Run: {run_id[:16]}",
        "",
        "See 4 charts attached.",
    ]

    insights = [chunk for chunk in (result.get('insights') or '').split('\n\n') if chunk.strip()]
    if insights:
        lines.append("Each insight below corresponds to one chart.")
        lines.append("")
        lines.extend(f"[Chart {i + 1}]\n{insight}" for i, insight in enumerate(insights))

    stats = result.get('gemini_stats') or {}
    if stats.get('tokens'):
        lines += ["", f"LLM commentary: {stats['tokens']} tokens (${stats['cost']:.4f})."]

    lines += ["", "Full report posted to Slack."]
    return "\n".join(lines)


def _post_asana_failure(task_gid: str, workflow_type: str, run_id: str, error: str) -> None:
    try:
        AsanaClient().add_comment(
            task_gid,
            f"Analysis failed\n\n"
            f"{workflow_type.replace('-', ' ').title()}\n"
            f"Run ID: {run_id}\n\n"
            f"Error: {error}\n\n"
            f"Check Kestra logs for details.",
        )
    except Exception as e:
        logger.error(f"Failed to post Asana failure comment: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run a Salesforce analytics workflow locally.")
    parser.add_argument(
        "workflow_type",
        choices=VALID_WORKFLOW_TYPES,
        help="Which analysis to run",
    )
    parser.add_argument("asana_task_gid", nargs="?", default=None)
    parser.add_argument("asana_task_url", nargs="?", default=None)
    parser.add_argument(
        "--skip-ai",
        action="store_true",
        help="Skip optional LLM chart commentary even when GEMINI_API_KEY is set",
    )
    args = parser.parse_args()

    if args.skip_ai:
        os.environ["SKIP_AI"] = "1"

    try:
        outcome = run_workflow(args.workflow_type, args.asana_task_gid, args.asana_task_url)
        print(f"SUCCESS: {outcome['status']}")
        sys.exit(0)
    except Exception as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
