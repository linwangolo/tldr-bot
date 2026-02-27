# TLDR Bot – project memory

## What this project does

- **tldr-bot** automates reading daily TLDR newsletters from Gmail, summarizing them with AWS Bedrock (Claude 3.5 Haiku), generating audio with Amazon Polly, storing summary JSON and MP3 in S3, and posting a briefing (text + links to summary and audio) to Slack.

## Architecture (implemented)

- **Trigger**: CloudWatch Events rule, cron daily at 7:30 AM UTC.
- **Lambda** (single function):  
  Gmail IMAP → parse emails (extract web-version URLs) → fetch & parse HTML (BeautifulSoup) → Bedrock summarization → save `summaries/YYYY-MM-DD.json` to S3 → Polly TTS → save `audio/YYYY-MM-DD.mp3` to S3 → presigned URLs → Slack webhook (inline summary + link to JSON + link to audio).
- **Secrets**: `tldr-bot/gmail-app-password`, `tldr-bot/gmail-address`, `tldr-bot/slack-webhook-url` in AWS Secrets Manager.
- **IAM**: Lambda has S3 read/write, Secrets Manager read, Bedrock InvokeModel, Polly SynthesizeSpeech + StartSpeechSynthesisTask + GetSpeechSynthesisTask, and PassRole for a dedicated Polly S3 role that writes long-form output to the artifacts bucket.

## Key files

- `tldr_ingest/tldr_ingest_stack.py` – CDK stack (S3, Lambda, layer, schedule, roles).
- `lambda/handler.py` – Pipeline entrypoint; uses `email_reader`, `parser`, `summarizer`, `tts`, `slack_notifier`.
- `lambda/parser.py` – Extracts TLDR web-version URLs from email HTML, fetches and parses with BeautifulSoup; supports multiple newsletters (AI, Tech, DevOps, etc.).
- `build_layer.sh` – Must be run before `cdk deploy` to populate `lambda_layer/python` with beautifulsoup4 and lxml.

## Current task / status

- Implementation is complete per plan: scaffold, CDK stack, Lambda modules (email, parser, summarizer, TTS, Slack), handler, Lambda deps + layer build script, README and memory.

## Notes

- Gmail search uses IMAP `(FROM "tldrnewsletter.com" SINCE <date>)`.
- Summary is saved to S3 then referenced in Slack; audio is stored in S3 and linked via presigned URL.
- Schedule is configurable in the stack (`Schedule.cron(minute="30", hour="7")`).
