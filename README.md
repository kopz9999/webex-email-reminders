# Webex Email Reminders

[![GitHub](https://img.shields.io/badge/GitHub-repo-blue)](https://github.com/kopz9999/webex-email-reminders)

CLI tool that checks Webex for mentions and direct messages from the last hour and sends an email summary via Nylas.

## Prerequisites

- Python 3.9+
- Nylas CLI: `brew install nylas/nylas-cli/nylas`

## Setup

```bash
pip install webex-email-reminders
```

Or install from source:
```bash
pip install -r requirements.txt
```

## Environment Variables

```bash
export WEBEX_JWT="your-webex-personal-access-token"
export NYLAS_API_KEY="your-nylas-api-key"
export NYLAS_GRANT_ID="your-nylas-grant-id"
```

## Usage

```bash
# Send summary email
webex-email-reminders --to your@email.com

# Send to multiple recipients from a file
webex-email-reminders --to-list recipients.txt

# Both single and list
webex-email-reminders --to your@email.com --to-list recipients.txt

# Custom time window
webex-email-reminders --to your@email.com --hours 2

# Filter DMs by contacts file
webex-email-reminders --to your@email.com --contacts contacts.txt

# Dry run (prints email content without sending)
webex-email-reminders --to your@email.com --dry-run

# Check version
webex-email-reminders --version
```

### Options

| Flag | Description |
|------|-------------|
| `--to` | Email address to send summary to |
| `--to-list` | Text file with email addresses to send to (one per line) |
| `--hours` | Look back period in hours (default: 1) |
| `--minutes` | Look back period in minutes (overrides --hours) |
| `--contacts` | Text file with email addresses to filter DMs |
| `--include-all` | Include all messages in active spaces, not just mentions |
| `--include-my-messages` | Include your own messages in DMs (excluded by default) |
| `--dry-run` | Print email content to stdout without sending |
| `--version` | Show version number |

## Local Development

```bash
python3 webex_reminders.py --to-list recipients.txt --hours 3
```

## Contacts File (optional)

One email per line to filter which DMs to include:

```
person1@company.com
person2@company.com
```

## Version Management

When releasing a new version, update the version in these files:

1. `pyproject.toml` — `version = "X.Y.Z"`
2. `webex_reminders.py` — `version="%(prog)s X.Y.Z"`

Then tag and deploy:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
./deploy.sh
```

## Deploy

```bash
./deploy.sh
```

## Crontab

Run hourly during work hours (8am–6pm EST, Mon–Fri):

```crontab
0 8-18 * * 1-5 /path/to/your/reminders.sh
```
