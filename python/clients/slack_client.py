import requests
from typing import Dict, Optional
import time
from utils.logger import setup_logger
from utils.error_handler import retry_on_failure, SlackAPIError
from config import settings

logger = setup_logger(__name__)

class SlackClient:
    def __init__(self):
        self.webhook_url = settings.SLACK_WEBHOOK_URL
        logger.info("Initialized Slack client")
    
    @retry_on_failure(max_attempts=3, delay=2.0, exceptions=(requests.RequestException,))
    def send_notification(self, workflow_type: str, metrics: Dict, insights: str, 
                         asana_task_url: Optional[str] = None, 
                         image_urls: Optional[list] = None) -> bool:
        try:
            start_time = time.time()
            
            insights_list = self._parse_insights(insights)
            blocks = self._build_blocks(workflow_type, metrics, insights_list, asana_task_url, image_urls)
            
            payload = {
                "blocks": blocks
            }
            
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            response.raise_for_status()
            
            duration = (time.time() - start_time) * 1000
            logger.info(f"Slack notification sent successfully in {duration:.2f}ms")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Slack notification: {str(e)}")
            raise SlackAPIError(f"Slack notification failed: {str(e)}")
    
    def _parse_insights(self, insights: str) -> list:
        """Parse insights text into list of individual insights"""
        insights_list = []
        lines = insights.split('\n')
        current_insight = []
        
        for line in lines:
            line = line.strip()
            if line.startswith('Finding:'):
                if current_insight:
                    insights_list.append('\n'.join(current_insight))
                current_insight = [line]
            elif line and current_insight:
                current_insight.append(line)
        
        if current_insight:
            insights_list.append('\n'.join(current_insight))
        
        return insights_list
    
    def _build_blocks(self, workflow_type: str, metrics: Dict, insights_list: list, 
                     asana_task_url: Optional[str] = None,
                     image_urls: Optional[list] = None) -> list:
        workflow_titles = {
            'sales-pipeline-health': '📊 Pipeline Health Report',
            'rep-performance': '👥 Sales Rep Performance Report',
            'revenue-forecast': '💰 Revenue Forecast Report'
        }
        
        title = workflow_titles.get(workflow_type, 'Analytics Report')
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": title
                }
            },
            {
                "type": "section",
                "fields": self._format_metrics(workflow_type, metrics)
            },
            {
                "type": "divider"
            }
        ]
        
        if asana_task_url:
            blocks.append({
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View in Asana"
                        },
                        "url": asana_task_url,
                        "style": "primary"
                    }
                ]
            })
        
        if image_urls and insights_list:
            chart_descriptions = self._get_chart_descriptions(workflow_type)
            
            for i, url in enumerate(image_urls):
                blocks.append({"type": "divider"})
                
                if i < len(insights_list):
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*📊 Analysis {i+1}*\n{insights_list[i]}"
                        }
                    })
                
                if i < len(chart_descriptions):
                    blocks.append({
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{chart_descriptions[i]['title']}*\n_{chart_descriptions[i]['desc']}_"
                        }
                    })
                
                blocks.append({
                    "type": "image",
                    "image_url": url,
                    "alt_text": chart_descriptions[i]['title'] if i < len(chart_descriptions) else "Chart"
                })
        
        return blocks
    
    def _get_chart_descriptions(self, workflow_type: str) -> list:
        descriptions = {
            'sales-pipeline-health': [
                {
                    'title': 'Chart 1: Opportunities by Stage',
                    'desc': 'Current distribution of opportunities across pipeline stages'
                },
                {
                    'title': 'Chart 2: Stage Conversion Rates',
                    'desc': 'Percentage of opportunities moving from each stage to the next'
                },
                {
                    'title': 'Chart 3: Average Time in Stage',
                    'desc': 'Days opportunities spend in each stage on average'
                },
                {
                    'title': 'Chart 4: Weekly Pipeline Trend',
                    'desc': 'Opportunity count trend over the last 12 weeks'
                }
            ],
            'rep-performance': [
                {
                    'title': 'Chart 1: Close Rate by Rep',
                    'desc': 'Percentage of won deals for each sales representative'
                },
                {
                    'title': 'Chart 2: Average Deal Size by Rep',
                    'desc': 'Average revenue per deal closed by each rep'
                },
                {
                    'title': 'Chart 3: Activities vs Outcome',
                    'desc': 'Correlation between number of activities and deal success'
                },
                {
                    'title': 'Chart 4: Activity Distribution',
                    'desc': 'Comparison of activity patterns between won and lost deals'
                }
            ],
            'revenue-forecast': [
                {
                    'title': 'Chart 1: Revenue Waterfall',
                    'desc': 'Pipeline value flowing to weighted revenue forecast'
                },
                {
                    'title': 'Chart 2: Stage Probability Weights',
                    'desc': 'Win probability applied to each pipeline stage'
                },
                {
                    'title': 'Chart 3: Monthly Revenue Trend',
                    'desc': 'Historical revenue with forecasted future performance'
                },
                {
                    'title': 'Chart 4: Pipeline Age Distribution',
                    'desc': 'How long opportunities have been open (identifies stalled deals)'
                }
            ]
        }
        return descriptions.get(workflow_type, [])
    
    def _format_metrics(self, workflow_type: str, metrics: Dict) -> list:
        fields = []
        
        if workflow_type == 'sales-pipeline-health':
            fields = [
                {"type": "mrkdwn", "text": f"*Total Opportunities:* {metrics.get('total_opportunities', 0)}"},
                {"type": "mrkdwn", "text": f"*Close Rate:* {metrics.get('close_rate', 0):.1f}%"},
                {"type": "mrkdwn", "text": f"*Avg Days to Close:* {metrics.get('avg_days_to_close', 0):.0f}"},
                {"type": "mrkdwn", "text": f"*Pipeline Value:* ${metrics.get('pipeline_value', 0):,.0f}"}
            ]
        elif workflow_type == 'rep-performance':
            fields = [
                {"type": "mrkdwn", "text": f"*Reps Analyzed:* {metrics.get('reps_count', 0)}"},
                {"type": "mrkdwn", "text": f"*Top Close Rate:* {metrics.get('top_close_rate', 0):.1f}%"},
                {"type": "mrkdwn", "text": f"*Avg Deal Size:* ${metrics.get('avg_deal_size', 0):,.0f}"},
                {"type": "mrkdwn", "text": f"*Avg Activities:* {metrics.get('avg_activities', 0):.1f}"}
            ]
        elif workflow_type == 'revenue-forecast':
            fields = [
                {"type": "mrkdwn", "text": f"*Pipeline Value:* ${metrics.get('total_pipeline', 0):,.0f}"},
                {"type": "mrkdwn", "text": f"*Weighted Forecast:* ${metrics.get('weighted_forecast', 0):,.0f}"},
                {"type": "mrkdwn", "text": f"*Confidence:* {metrics.get('confidence', 0):.0f}%"},
                {"type": "mrkdwn", "text": f"*At Risk:* ${metrics.get('at_risk_value', 0):,.0f}"}
            ]
        
        return fields

