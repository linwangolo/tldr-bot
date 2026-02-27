# tldr-bot

Automated daily pipeline: read TLDR newsletters from Gmail, summarize with AWS Bedrock (Claude), generate audio with Amazon Polly, store summary + audio in S3, and post a briefing to Slack.

## Architecture

- **Trigger**: CloudWatch Events (cron daily at 7:30 AM UTC).
- **Lambda**: Connects to Gmail via IMAP, fetches TLDR emails from the last 24 hours, extracts web-version URLs, parses content with BeautifulSoup, summarizes with Claude 3.5 Haiku, generates MP3 with Polly Neural, saves `summaries/YYYY-MM-DD.json` and `audio/YYYY-MM-DD.mp3` to S3, then posts a rich message to Slack (inline summary + links to JSON and audio).

## Prerequisites

1. **Google App Password**  
   [Google Account → Security → App Passwords](https://myaccount.google.com/apppasswords). Create one for "Mail" (2FA required). You will store this in AWS Secrets Manager.

2. **Slack Incoming Webhook**  
   - [api.slack.com/apps](https://api.slack.com/apps) → Create New App → From scratch.  
   - Name it (e.g. "TLDR Bot"), select your workspace.  
   - Incoming Webhooks → ON → Add New Webhook to Workspace → choose channel.  
   - Copy the webhook URL.

3. **AWS**  
   - Account with CLI configured.  
   - `cdk bootstrap` run once in the target account/region.  
   - In [Bedrock console](https://console.aws.amazon.com/bedrock) (same region as deploy), enable **Claude 3.5 Haiku** (model access).


## Deployment

Requires [uv](https://docs.astral.sh/uv/).

```bash
brew install uv
cd tldr-bot
uv venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt
# Optional: for reproducible installs, run uv pip compile requirements.txt -o requirements.lock then use uv pip sync requirements.lock

# Build Lambda layer (required before first deploy)
chmod +x build_layer.sh
./build_layer.sh

# Create secrets (replace placeholders)
aws secretsmanager create-secret --name tldr-bot/gmail-app-password --secret-string "YOUR_APP_PASSWORD"
aws secretsmanager create-secret --name tldr-bot/gmail-address --secret-string "YOUR_EMAIL@gmail.com"
aws secretsmanager create-secret --name tldr-bot/slack-webhook-url --secret-string "YOUR_SLACK_WEBHOOK_URL"

# Deploy
npm install -g aws-cdk
cdk bootstrap
cdk deploy

```

After deploy, the Lambda runs daily at 7:30 AM UTC. You can change the schedule in `tldr_ingest/tldr_ingest_stack.py` (`Schedule.cron(minute="30", hour="7")`).

## Project layout

- `app.py` – CDK app entry.
- `tldr_ingest/tldr_ingest_stack.py` – Stack: S3 bucket, Lambda, layer, CloudWatch rule, IAM, Polly role.
- `lambda/` – Lambda code: `handler.py` (orchestrator), `email_reader.py`, `parser.py`, `summarizer.py`, `tts.py`, `slack_notifier.py`.
- `lambda/requirements.txt` – Dependencies for the Lambda layer (BeautifulSoup, lxml).
- `build_layer.sh` – Installs layer deps into `lambda_layer/python` for CDK.

## S3 outputs

- `summaries/YYYY-MM-DD.json` – Full daily summary (date, sources, issues, LLM summary text, metadata).
- `audio/YYYY-MM-DD.mp3` – Spoken briefing (Polly Neural).  
Objects expire after 30 days (bucket lifecycle).

## Slack message

Each run posts a message with:

- Header: "TLDR Daily Briefing — YYYY-MM-DD".
- Inline summary text.
- Link to play the MP3.
- Link to download the summary JSON.

Presigned URLs expire after 24 hours.
