# Salesforce Opportunity Analytics Pipeline

Automated pipeline that pulls Salesforce opportunity data, generates charts, and uses Gemini AI to produce insights. Orchestrated by Kestra, triggered by Asana tasks.

## What It Does

Create an Asana task with a specific tag, and the system:
1. Polls Asana every 6 hours (or trigger manually via Kestra UI)
2. Extracts opportunities and activities from Salesforce
3. Loads data into Snowflake
4. Calculates metrics and generates 4 charts (matplotlib)
5. Sends charts + data to Gemini for AI analysis
6. Posts results to Slack with embedded images
7. Uploads charts to Asana task, adds AI insights, marks complete

Three analysis types available, triggered by different Asana tags.

## Demo

### Creating an Asana Task
Create a task in Asana and tag it with one of the three workflow tags to trigger analysis:

<img src="docs/images/asana-task-creation.gif" alt="Asana Task Creation" width="900"/>

### Workflow Execution & Slack Notification
Kestra orchestrates the workflow and sends results to Slack with embedded charts:

<img src="docs/images/kestra-workflow-slack.gif" alt="Kestra Workflow and Slack" width="900"/>

### Completed Asana Task
The task is automatically marked complete with charts attached and AI insights added as comments:

<img src="docs/images/asana-completed-task.png" alt="Asana Completed Task" width="400"/>

## Workflows

**Pipeline Health** (`sales-pipeline-health`)
- Distribution by stage, conversion rates, time in stage, weekly trends
- Use for identifying bottlenecks

**Rep Performance** (`rep-performance`)  
- Close rates, deal sizes, activity patterns by rep
- Use for coaching and reviews

**Revenue Forecast** (`revenue-forecast`)
- Pipeline value, weighted forecast, at-risk analysis
- Use for board meetings and planning

## Tech Stack

- **Kestra**: Workflow orchestration (Docker)
- **Python**: Data extraction, transformation, chart generation
- **Salesforce API**: Source data (opportunities + tasks)
- **Snowflake**: Data warehouse
- **Gemini 2.0 Flash**: Multimodal AI (text + image analysis)
- **Slack**: Notifications via webhook
- **Asana**: Request management and results delivery
- **Imgur**: Chart hosting for Slack

## Setup

### Prerequisites
- Docker Desktop
- Salesforce account (sandbox or developer edition)
- Snowflake account
- Google Gemini API key
- Slack webhook URL
- Asana account with PAT

### 1. Clone and Configure

```bash
git clone https://github.com/Vignesh-Hariharan/salesforce-analytics-pipeline.git
cd salesforce-analytics-pipeline
cp .env.example .env
```

Edit `.env` with your credentials:
```bash
# Snowflake
SNOWFLAKE_ACCOUNT=your-account-id
SNOWFLAKE_USER=your-username
SNOWFLAKE_PASSWORD=your-password
SNOWFLAKE_DATABASE=SALES_ANALYTICS
SNOWFLAKE_SCHEMA=OPPORTUNITIES
SNOWFLAKE_WAREHOUSE=COMPUTE_WH

# Salesforce
SALESFORCE_USERNAME=your-email
SALESFORCE_PASSWORD=your-password
SALESFORCE_SECURITY_TOKEN=your-token
SALESFORCE_DOMAIN=login  # or 'test' for sandbox

# Gemini
GEMINI_API_KEY=your-api-key

# Slack
SLACK_WEBHOOK_URL=your-webhook-url

# Asana
ASANA_ACCESS_TOKEN=your-token
ASANA_PROJECT_GID=your-project-id
```

### 2. Setup Snowflake

Run `sql/setup_snowflake.sql` in Snowflake UI to create database, schema, and tables.

### 3. Setup Asana

Create three tags in your Asana project:
- `sales-pipeline-health`
- `rep-performance`
- `revenue-forecast`

### 4. Start Kestra

```bash
cd docker
docker-compose up -d
```

Wait 30 seconds, then open http://localhost:8080

### 5. Upload Workflows

In Kestra UI, create these flows under namespace `salesforce.analytics`:
- `kestra/flows/asana-poller.yml`
- `kestra/flows/manual-trigger-workflow.yml`
- `kestra/flows/pipeline-health-workflow.yml`
- `kestra/flows/rep-performance-workflow.yml`
- `kestra/flows/revenue-forecast-workflow.yml`

## Usage

### Automated (Production)

1. Create an Asana task in your project
2. Add one of the three tags (`sales-pipeline-health`, `rep-performance`, or `revenue-forecast`)
3. Leave it incomplete
4. Wait for next polling cycle (every 6 hours: 00:00, 06:00, 12:00, 18:00 UTC)
5. Results posted to Asana + Slack

The system will automatically:
- Detect the new task with the workflow tag
- Execute the corresponding analysis workflow
- Generate 4 charts and AI insights
- Upload charts to the Asana task
- Post results to Slack with embedded images
- Mark the task as complete

See the [Demo](#demo) section above for a visual walkthrough.

### Manual Trigger (Testing)

1. Go to Kestra UI (http://localhost:8080)
2. Navigate to `salesforce.analytics` namespace
3. Find `manual-trigger-workflow`
4. Click Execute
5. Select workflow type from dropdown
6. (Optional) Provide Asana task GID and URL for task updates
7. Click Run

Results will be sent to Slack. If you provide a valid Asana task GID, the task will be updated with charts and insights.

## Project Structure

```
.
├── docker/
│   └── docker-compose.yml       # Kestra + Postgres
├── kestra/flows/
│   ├── asana-poller.yml         # Polls Asana every 6h
│   ├── manual-trigger-workflow.yml
│   └── *-workflow.yml           # 3 analysis workflows
├── python/
│   ├── clients/                 # API integrations
│   │   ├── salesforce_client.py
│   │   ├── snowflake_client.py
│   │   ├── gemini_client.py
│   │   ├── slack_client.py
│   │   ├── asana_client.py
│   │   └── image_host_client.py
│   ├── workflows/               # Analysis logic
│   │   ├── pipeline_health.py
│   │   ├── rep_performance.py
│   │   └── revenue_forecast.py
│   ├── config/
│   │   ├── settings.py
│   │   └── prompts.py
│   ├── utils/
│   └── main.py
├── sql/
│   └── setup_snowflake.sql
└── outputs/charts/              # Generated PNGs
```

## Data Model

**fact_opportunities**
- Opportunity details (ID, name, amount, stage, dates, owner)
- Pre-calculated fields (days_open, days_to_close, total_activities)

**dim_activities**
- Tasks linked to opportunities
- Activity type, date, owner

**pipeline_runs**
- Audit log of workflow executions
- Tracks status, records processed, Gemini cost

## AI Analysis

Gemini receives:
- Text prompt with metrics and data summary
- 4 chart images (multimodal input)
- Temperature: 0.3 (consistent output)
- Max tokens: 800

Outputs 4 insights in format:
```
Finding: [Observation from chart]
Impact: [Business consequence]
Action: [Specific next step]
```

Cost: ~$0.01 per run (Gemini 2.0 Flash pricing)

## Development

### Run Python Locally

```bash
cd python
pip install -r requirements.txt
python main.py sales-pipeline-health
```

### Test Individual Components

```python
from clients.salesforce_client import SalesforceClient

sf = SalesforceClient()
opps = sf.get_opportunities(days=90)
print(f"Extracted {len(opps)} opportunities")
```

### View Logs

```bash
docker logs docker-kestra-1 -f
```

## Troubleshooting

**Kestra not starting?**
- Check Docker Desktop is running
- View logs: `docker logs docker-kestra-1`
- Ensure ports 8080/8081 are free

**Salesforce auth failing?**
- Verify username/password/token in `.env`
- Use `login` domain for production, `test` for sandbox
- Reset security token if needed

**No images in Slack?**
- Imgur upload might fail (temporary)
- Charts still uploaded to Asana
- Slack gets text-only notification

**Task not processed?**
- Verify task is in correct Asana project
- Check tag spelling (lowercase, exact match)
- Ensure task is incomplete
- Wait for next 6-hour cycle or trigger manually

## Notes

- Uses Salesforce sandbox data (last 90 days)
- Imgur hosting is a demo convenience; for real business data, use Slack file
  upload or presigned S3 URLs instead of a public image host
- Snowflake X-Small warehouse (auto-suspend after 60s)
- Gemini API has free tier (15 req/min)
- Asana API: 150 req/min limit
- All credentials stored in `.env` (not committed)
- Charts auto-deleted after 7 days

## License

MIT
