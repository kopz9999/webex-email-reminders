# Webex Email Reminders

CLI tool that checks Webex for mentions and direct messages from the last hour and sends an email summary via Nylas.

## Prerequisites

- Python 3.9+
- Nylas CLI: `brew install nylas/nylas-cli/nylas`

## Setup

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
python webex_reminders.py --to your@email.com

# Custom time window
python webex_reminders.py --to your@email.com --hours 2

# Filter DMs by contacts file
python webex_reminders.py --to your@email.com --contacts contacts.txt

# Dry run (prints email content without sending)
python webex_reminders.py --to your@email.com --dry-run
```

### Options

| Flag | Description |
|------|-------------|
| `--to` | Email address to send summary to (required) |
| `--hours` | Look back period in hours (default: 1) |
| `--contacts` | Text file with email addresses to filter DMs |
| `--dry-run` | Print email content to stdout without sending |

## Contacts File (optional)

One email per line to filter which DMs to include:

```
person1@company.com
person2@company.com
```
