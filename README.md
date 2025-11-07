# Salesforce Opportunity Analytics Pipeline

Automated pipeline that pulls Salesforce opportunity data, runs analysis, generates charts, and uses Gemini AI to produce insights. Built to demonstrate practical data engineering with real API integrations.

## What This Does

You create an Asana task with a specific tag (like `sales-pipeline-health`), and the system:
1. Detects the task (polls Asana every 6 hours, or trigger manually)
2. Extracts opportunities and activities from Salesforce sandbox
3. Loads data into Snowflake tables
4. Calculates metrics and generates 4 matplotlib charts
5. Sends charts + data to Gemini for multimodal AI analysis
6. Posts results to Slack
7. Attaches charts to Asana task, adds AI insights as comment, marks complete

Three different analysis types available based on Asana tag.

## Architecture

```
Asana Task Created (manual)
    ↓
Kestra Poller (every 6 hours or manual trigger)
    ↓
Python: Extract from Salesforce API
    ↓
Snowflake: Load to fact_opportunities, dim_activities
    ↓
Python: Calculate metrics, generate charts
    ↓
Gemini: Analyze data + chart images, generate insights
    ↓
Slack: Send notification
    ↓
Asana: Upload charts, add comment, mark complete
```

Everything runs locally in Docker. Python does the heavy lifting, Kestra orchestrates.

## Workflows

### 1. Pipeline Health (`sales-pipeline-health` tag)
Analyzes where deals are stuck in the pipeline.
- Opportunities by stage
- Stage conversion rates
- Time spent in each stage
- Weekly trends

### 2. Rep Performance (`rep-performance` tag)
Compares sales rep effectiveness.
- Close rates by rep
- Average deal sizes
- Activity correlation (more calls = more wins?)
- Won vs lost activity patterns

### 3. Revenue Forecast (`revenue-forecast` tag)
Projects revenue based on current pipeline.
- Total pipeline value
- Weighted forecast (applies probability by stage)
- Historical revenue trends
- At-risk deals (stalled >90 days)

## Setup Instructions

### Prerequisites

- Docker Desktop installed and running
- Python 3.9+ (for local testing)
- Accounts: Salesforce sandbox, Snowflake, Gemini API, Slack, Asana

### 1. Snowflake Setup

Run the SQL in `sql/setup_snowflake.sql` to create:
- Database: SALES_ANALYTICS
- Schema: OPPORTUNITIES
- Warehouse: COMPUTE_WH (X-Small, auto-suspend after 60s)
- Tables: fact_opportunities, dim_activities, pipeline_runs

Note: Make sure your Snowflake user has CREATE permissions on database/schema/warehouse.

### 2. Salesforce Connected App

Login to your sandbox:
1. Setup → Apps → App Manager → New Connected App
2. Enable OAuth Settings
3. Callback URL: `https://login.salesforce.com/` (placeholder, not used)
4. Selected OAuth Scopes: Full access (api), Perform requests on your behalf (refresh_token)
5. Save and copy Consumer Key + Consumer Secret

Wait 10 minutes for Salesforce to activate it (seriously, it's slow).

Alternatively, use username/password/security token method:
- Go to Settings → Reset My Security Token
- Check email for token
- Token gets appended to password when authenticating

### 3. Get API Keys

**Gemini:**
- Visit https://aistudio.google.com/app/apikey
- Create API key (free tier: 60 requests/minute)
- Copy key

**Slack:**
- Create incoming webhook: https://api.slack.com/messaging/webhooks
- Choose channel, get webhook URL

**Asana:**
- Go to https://app.asana.com/0/my-apps
- Create Personal Access Token
- Copy token
- Find your project GID: Open project in browser, GID is in URL after `/project/`

### 4. Configure Environment

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Fill in your actual credentials in `.env`. Double-check these, common issues:
- Snowflake account identifier is usually like `XXXXX-XXXXX` not the full URL
- Salesforce security token goes separate from password
- Asana project GID is just the number, not full URL

### 5. Install Python Dependencies

```bash
cd python
pip install -r requirements.txt
```

Test Snowflake connection:
```bash
python -c "from clients.snowflake_client import SnowflakeClient; c = SnowflakeClient(); print('Connected')"
```

If that works, you're good.

### 6. Start Kestra

```bash
cd docker
docker-compose up -d
```

Wait 30 seconds, then open http://localhost:8080

First time takes a while to download images (~2GB).

### 7. Add Secrets to Kestra

In Kestra UI:
- Go to Namespaces → salesforce.analytics (create if doesn't exist)
- Click Secrets tab
- Add each credential from your .env file:
  - SNOWFLAKE_ACCOUNT
  - SNOWFLAKE_USER
  - SNOWFLAKE_PASSWORD
  - SALESFORCE_USERNAME
  - SALESFORCE_PASSWORD
  - SALESFORCE_SECURITY_TOKEN
  - GEMINI_API_KEY
  - SLACK_WEBHOOK_URL
  - ASANA_ACCESS_TOKEN
  - ASANA_PROJECT_GID

Secrets are encrypted at rest.

### 8. Upload Workflows to Kestra

In Kestra UI:
- Flows → Create
- Copy paste content from each YAML in `kestra/flows/`
- Upload all 4 files:
  - asana-poller.yml
  - pipeline-health-workflow.yml
  - rep-performance-workflow.yml
  - revenue-forecast-workflow.yml

Save each one. They should appear in the Flows list.

## Running It

### Manual Trigger (Recommended for Testing)

1. Create Asana task in your project
2. Add tag: `sales-pipeline-health` (or `rep-performance` or `revenue-forecast`)
3. Keep task incomplete
4. In Kestra UI, go to Flows → asana-poller
5. Click Execute button (top right)
6. Watch logs

It should:
- Find your task
- Trigger the appropriate workflow
- Run Python script
- Upload charts to Asana
- Send Slack notification
- Mark task complete

Check Asana task for charts and AI insights in comments.

### Scheduled Polling

Poller runs automatically every 6 hours: 12am, 6am, 12pm, 6pm.

Only works if Docker is running. If your laptop sleeps, schedule pauses.

To disable schedule: Edit asana-poller.yml, set `disabled: true` under triggers.

## Troubleshooting

**Docker containers won't start:**
- Check Docker Desktop is running
- Try `docker-compose down` then `docker-compose up -d`
- Check ports 8080/8081 aren't used by something else

**Kestra can't find Python scripts:**
- Volume mounts in docker-compose.yml need absolute paths
- Check the volumes section references your actual directories

**Salesforce API errors:**
- Verify security token is current (resets when password changes)
- Check your sandbox is active (sandboxes can expire)
- API limits: 15k calls/day on most sandboxes

**Snowflake connection timeout:**
- Account identifier format: remove `https://` and `.snowflakecomputing.com`
- Just use the part like `ABC12345-XY67890`
- Warehouse must be running (auto-resume should handle this)

**Gemini API quota exceeded:**
- Free tier: 60 requests/minute
- Each workflow uses 1 request
- Wait a minute and retry

**Charts not generating:**
- Check outputs/charts/ folder exists
- matplotlib needs write permissions
- Running in Docker might have path issues (check OUTPUT_DIR in settings.py)

**Asana task not found:**
- Project GID must be correct
- Task must have exact tag name (case-sensitive)
- Task must be incomplete

## Tech Stack

- **Orchestration:** Kestra (workflow scheduling, retry logic)
- **Data Extraction:** Salesforce API (simple-salesforce)
- **Data Warehouse:** Snowflake (idempotent MERGE statements)
- **Visualization:** Matplotlib (4 charts per workflow)
- **AI Analysis:** Google Gemini 1.5 Pro (multimodal: text + images)
- **Notifications:** Slack (webhooks), Asana (REST API)
- **Language:** Python 3.11
- **Infrastructure:** Docker Compose

## Project Structure

```
├── docker/
│   └── docker-compose.yml          # Kestra setup
├── kestra/
│   └── flows/                      # Workflow definitions (YAML)
├── python/
│   ├── clients/                    # API clients (5 files)
│   ├── config/                     # Settings, prompts
│   ├── workflows/                  # Core logic for each analysis
│   ├── utils/                      # Logging, error handling
│   ├── main.py                     # Entry point Kestra calls
│   └── requirements.txt
├── sql/
│   └── setup_snowflake.sql         # Database setup
├── outputs/
│   └── charts/                     # Generated PNG files
└── README.md
```

## Quick Test

After setup, test individual connections:

```bash
cd python

# Test Salesforce
python -c "from clients.salesforce_client import SalesforceClient; c = SalesforceClient(); print('Salesforce OK')"

# Test Snowflake
python -c "from clients.snowflake_client import SnowflakeClient; c = SnowflakeClient(); print('Snowflake OK'); c.close()"

# Test full workflow
python main.py sales-pipeline-health
```

Should generate 4 charts in `outputs/charts/` and send Slack notification.

## Cost Estimate

Running locally for demo purposes:
- Snowflake: ~$2-5/month (X-Small warehouse, minimal usage)
- Gemini API: ~$1-2/month (120 calls at ~$0.01 each)
- Salesforce: Free (sandbox)
- Slack/Asana: Free (webhook/API)

Total: ~$3-7/month if running scheduled. $0 if just doing manual demos.

Docker and Python run on your laptop (free).

## Development Notes

**Why Kestra?**
Needed an orchestrator that's not Airflow (too heavy) or cron (too basic). Kestra has nice UI, handles retries, logs everything.

**Why multimodal Gemini?**
Sending charts as images lets AI see patterns humans see. More interesting than just text prompts. Gemini 1.5 Pro handles this well.

**Why three workflows?**
Shows modularity. Easy to add more by copying pattern. Each answers a different business question.

**Data quality issues:**
- Some Salesforce fields might be null (handled with .get() defaults)
- Conversion rate chart uses sample data (real version needs stage history tracking)
- Activity counts might be off if Tasks aren't logged consistently

**Improvements for production:**
- Add dbt for transformations
- Use Kestra's built-in secrets instead of .env in Docker
- Set up proper monitoring/alerting
- Add data quality checks
- Handle more Salesforce edge cases (person accounts, etc)
- Better error messages to Asana when things fail

## License

MIT

