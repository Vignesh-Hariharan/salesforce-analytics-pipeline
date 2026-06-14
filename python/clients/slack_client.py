import time
from typing import Dict, Optional

import requests

from config import settings
from utils.error_handler import retry_on_failure, SlackAPIError
from utils.logger import setup_logger

logger = setup_logger(__name__)


WORKFLOW_TITLES = {
    'sales-pipeline-health': 'Pipeline Health Report',
    'rep-performance':       'Sales Rep Performance Report',
    'revenue-forecast':      'Revenue Forecast Report',
}


class SlackClient:
    def __init__(self):
        self.webhook_url = settings.SLACK_WEBHOOK_URL

    @retry_on_failure(max_attempts=3, delay=2.0, exceptions=(requests.RequestException,))
    def send_notification(self, workflow_type: str, metrics: Dict, insights: str,
                          asana_task_url: Optional[str] = None,
                          asana_note: Optional[str] = None) -> bool:
        try:
            blocks = self._build_blocks(workflow_type, metrics, insights, asana_task_url, asana_note)
            start = time.time()
            response = requests.post(
                self.webhook_url,
                json={'blocks': blocks},
                headers={'Content-Type': 'application/json'},
                timeout=10,
            )
            if response.status_code != 200:
                logger.error(f"Slack rejected payload ({response.status_code}): {response.text}")
                response.raise_for_status()
            logger.info(f"Slack notification sent in {(time.time() - start) * 1000:.0f}ms")
            return True
        except requests.RequestException:
            raise
        except Exception as e:
            logger.error(f"Slack notification failed: {e}")
            raise SlackAPIError(f"Slack notification failed: {e}")

    def _build_blocks(self, workflow_type: str, metrics: Dict, insights: str,
                      asana_task_url: Optional[str], asana_note: Optional[str]) -> list:
        blocks = [
            {'type': 'header', 'text': {'type': 'plain_text',
                                        'text': WORKFLOW_TITLES.get(workflow_type, 'Analytics Report')}},
            {'type': 'section', 'fields': self._format_metrics(workflow_type, metrics)},
            {'type': 'divider'},
        ]

        if asana_note:
            blocks.append({'type': 'context',
                           'elements': [{'type': 'mrkdwn', 'text': asana_note}]})

        for insight in self._parse_insights(insights):
            blocks.append({'type': 'section',
                           'text': {'type': 'mrkdwn', 'text': insight}})
            blocks.append({'type': 'divider'})

        if asana_task_url:
            blocks.append({
                'type': 'actions',
                'elements': [{
                    'type': 'button',
                    'text': {'type': 'plain_text', 'text': 'View charts in Asana'},
                    'url': asana_task_url,
                    'style': 'primary',
                }],
            })
        else:
            blocks.append({
                'type': 'context',
                'elements': [{'type': 'mrkdwn',
                              'text': 'Charts attached to the originating Asana task.'}],
            })

        return blocks

    @staticmethod
    def _parse_insights(insights: str) -> list:
        """Group consecutive lines into insight blocks at every 'Finding:' marker.

        Slack mrkdwn handles `< > &` literally inside section text, so no
        escaping is needed; the prior implementation HTML-escaped these and
        produced `&lt;` artefacts in numeric ranges.
        """
        groups: list[list[str]] = []
        current: list[str] = []
        for raw in insights.splitlines():
            line = raw.strip()
            if line.startswith('Finding:'):
                if current:
                    groups.append(current)
                current = [line]
            elif line and current:
                current.append(line)
        if current:
            groups.append(current)
        return ['\n'.join(g) for g in groups]

    @staticmethod
    def _format_metrics(workflow_type: str, metrics: Dict) -> list:
        if workflow_type == 'sales-pipeline-health':
            return [
                _field('Total opportunities', metrics.get('total_opportunities', 0)),
                _field('Close rate',          f"{metrics.get('close_rate', 0):.1f}%"),
                _field('Avg days to close',   f"{metrics.get('avg_days_to_close', 0):.0f}"),
                _field('Pipeline value',      f"${metrics.get('pipeline_value', 0):,.0f}"),
            ]
        if workflow_type == 'rep-performance':
            return [
                _field('Reps analyzed',  metrics.get('reps_count', 0)),
                _field('Top close rate', f"{metrics.get('top_close_rate', 0):.1f}%"),
                _field('Avg deal size',  f"${metrics.get('avg_deal_size', 0):,.0f}"),
                _field('Avg activities', f"{metrics.get('avg_activities', 0):.1f}"),
            ]
        if workflow_type == 'revenue-forecast':
            fields = [
                _field('Pipeline value',     f"${metrics.get('total_pipeline', 0):,.0f}"),
                _field('Weighted forecast',  f"${metrics.get('weighted_forecast', 0):,.0f}"),
                _field('Open opps',          metrics.get('open_opps', 0)),
                _field('At risk (>90 days)', f"${metrics.get('at_risk_value', 0):,.0f}"),
            ]
            fallback = metrics.get('weights_fallback_count', 0)
            if fallback:
                fields.append(_field(
                    'Stage weights',
                    f"{fallback} fell back to default (insufficient history)",
                ))
            return fields
        return []


def _field(label: str, value) -> Dict:
    return {'type': 'mrkdwn', 'text': f"*{label}:* {value}"}
