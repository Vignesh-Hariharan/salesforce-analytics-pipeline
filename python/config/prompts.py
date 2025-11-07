PIPELINE_HEALTH_PROMPT = """You are analyzing Salesforce opportunity pipeline health data. Your goal is to identify bottlenecks and actionable improvements.

DATA SUMMARY:
{data_summary}

VISUAL ANALYSIS:
You are viewing 4 charts in order:
1. Opportunities by Stage (bar chart) - shows current distribution
2. Stage Conversion Rates (bar chart with percentages) - shows drop-off between stages
3. Average Time in Stage (bar chart in days) - shows velocity issues
4. Weekly Stage Movement Trend (line chart) - shows progression over time

TASK:
Provide exactly 4 insights (one per chart). Use this exact format without numbering:

Finding: [Specific observation from Chart 1 with numbers]
Impact: [Direct business consequence]
Action: [One concrete next step]

Finding: [Specific observation from Chart 2 with numbers]
Impact: [Direct business consequence]
Action: [One concrete next step]

Finding: [Specific observation from Chart 3 with numbers]
Impact: [Direct business consequence]
Action: [One concrete next step]

Finding: [Specific observation from Chart 4 with numbers]
Impact: [Direct business consequence]
Action: [One concrete next step]

REQUIREMENTS:
- Be concise and specific
- Use actual numbers from charts
- One finding per chart
- Focus on actionable bottlenecks only
"""

REP_PERFORMANCE_PROMPT = """You are analyzing sales representative performance patterns to identify what drives success.

DATA SUMMARY:
{data_summary}

VISUAL ANALYSIS:
You are viewing 4 charts in order:
1. Close Rate by Rep (bar chart) - shows which reps convert best
2. Average Deal Size by Rep (bar chart) - shows deal value patterns
3. Activities vs Close Rate (scatter plot) - shows correlation between effort and results
4. Won vs Lost Activity Distribution (box plot) - shows activity patterns for successful vs unsuccessful deals

TASK:
Provide exactly 4 insights (one per chart). Use this exact format without numbering:

Finding: [Specific observation from Chart 1 with numbers]
Impact: [Direct business consequence]
Action: [One concrete next step]

Finding: [Specific observation from Chart 2 with numbers]
Impact: [Direct business consequence]
Action: [One concrete next step]

Finding: [Specific observation from Chart 3 with numbers]
Impact: [Direct business consequence]
Action: [One concrete next step]

Finding: [Specific observation from Chart 4 with numbers]
Impact: [Direct business consequence]
Action: [One concrete next step]

REQUIREMENTS:
- Be concise and specific
- Use actual numbers from charts
- One finding per chart
- Focus on actionable performance patterns only
"""

REVENUE_FORECAST_PROMPT = """You are analyzing pipeline data to forecast revenue and identify risks.

DATA SUMMARY:
{data_summary}

VISUAL ANALYSIS:
You are viewing 4 charts in order:
1. Revenue Waterfall (from pipeline to weighted forecast) - shows expected conversion
2. Stage Probability Weighting (horizontal bars) - shows confidence by stage
3. Monthly Closed Revenue Trend with Forecast (line chart) - shows historical pattern and projection
4. Pipeline Age Distribution (histogram) - shows how long deals have been open

TASK:
Provide exactly 4 insights (one per chart). Use this exact format without numbering:

Finding: [Specific observation from Chart 1 with numbers]
Impact: [Direct business consequence]
Action: [One concrete next step]

Finding: [Specific observation from Chart 2 with numbers]
Impact: [Direct business consequence]
Action: [One concrete next step]

Finding: [Specific observation from Chart 3 with numbers]
Impact: [Direct business consequence]
Action: [One concrete next step]

Finding: [Specific observation from Chart 4 with numbers]
Impact: [Direct business consequence]
Action: [One concrete next step]

REQUIREMENTS:
- Be concise and specific
- Use actual numbers from charts
- One finding per chart
- Focus on actionable revenue risks only
"""

PROMPT_CONFIGS = {
    'sales-pipeline-health': {
        'template': PIPELINE_HEALTH_PROMPT,
        'temperature': 0.3,
        'focus': 'bottleneck identification'
    },
    'rep-performance': {
        'template': REP_PERFORMANCE_PROMPT,
        'temperature': 0.4,
        'focus': 'pattern recognition'
    },
    'revenue-forecast': {
        'template': REVENUE_FORECAST_PROMPT,
        'temperature': 0.3,
        'focus': 'predictive accuracy'
    }
}

def get_prompt(workflow_type: str, data_summary: str) -> tuple:
    config = PROMPT_CONFIGS.get(workflow_type)
    if not config:
        raise ValueError(f"Unknown workflow type: {workflow_type}")
    
    prompt = config['template'].format(data_summary=data_summary)
    temperature = config['temperature']
    
    return prompt, temperature

