#!/usr/bin/env python3
"""Webex Email Reminders - Check Webex mentions and DMs, send email summary via Nylas."""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from nylas import Client as NylasClient


def get_webex_headers():
    token = os.environ.get("WEBEX_JWT")
    if not token:
        sys.exit("Error: WEBEX_JWT environment variable not set")
    return {"Authorization": f"Bearer {token}"}


def get_me(headers):
    resp = requests.get("https://webexapis.com/v1/people/me", headers=headers)
    resp.raise_for_status()
    return resp.json()


def get_mentions(headers, since, include_all=False):
    """Get messages where you are mentioned across all spaces."""
    rooms_resp = requests.get(
        "https://webexapis.com/v1/rooms", headers=headers, params={"max": 50, "sortBy": "lastactivity"}
    )
    rooms_resp.raise_for_status()

    messages = []
    for room in rooms_resp.json().get("items", []):
        last_activity = datetime.fromisoformat(room["lastActivity"].replace("Z", "+00:00"))
        if last_activity < since:
            break
        if room.get("type") == "direct":
            continue

        params = {"roomId": room["id"], "max": 20}
        if not include_all:
            params["mentionedPeople"] = "me"

        msgs_resp = requests.get(
            "https://webexapis.com/v1/messages",
            headers=headers,
            params=params,
        )
        if msgs_resp.status_code != 200:
            continue

        for msg in msgs_resp.json().get("items", []):
            created = datetime.fromisoformat(msg["created"].replace("Z", "+00:00"))
            if created >= since:
                msg["_spaceName"] = room.get("title", "Unknown Space")
                messages.append(msg)
    return messages


def get_direct_messages(headers, since, my_email, contacts_file=None, include_my_messages=False):
    """Get direct messages from the last hour, optionally filtered by a contacts file."""
    allowed_emails = None
    if contacts_file and os.path.exists(contacts_file):
        with open(contacts_file) as f:
            allowed_emails = {line.strip().lower() for line in f if line.strip()}

    rooms_resp = requests.get(
        "https://webexapis.com/v1/rooms", headers=headers, params={"type": "direct", "max": 50}
    )
    rooms_resp.raise_for_status()

    messages = []
    for room in rooms_resp.json().get("items", []):
        last_activity = datetime.fromisoformat(room["lastActivity"].replace("Z", "+00:00"))
        if last_activity < since:
            continue

        msgs_resp = requests.get(
            "https://webexapis.com/v1/messages",
            headers=headers,
            params={"roomId": room["id"], "max": 20},
        )
        msgs_resp.raise_for_status()

        for msg in msgs_resp.json().get("items", []):
            created = datetime.fromisoformat(msg["created"].replace("Z", "+00:00"))
            if created < since:
                break
            sender = msg.get("personEmail", "").lower()
            if not include_my_messages and sender == my_email.lower():
                continue
            if allowed_emails and sender not in allowed_emails:
                continue
            messages.append(msg)

    return messages


def format_email_body(mentions, dms):
    """Format mentions and DMs into an HTML email body."""
    local_tz = datetime.now().astimezone().tzinfo
    body = "<h2>Webex Summary - Last Hour</h2>"

    if mentions:
        body += "<h3>Mentions</h3>"
        grouped = {}
        for msg in mentions:
            space = msg.get("_spaceName", "Unknown Space")
            grouped.setdefault(space, []).append(msg)
        for space, msgs in grouped.items():
            body += f"<h4>{space}</h4><ul>"
            for msg in msgs:
                sender = msg.get("personEmail", "unknown")
                text = msg.get("text", "")[:200]
                created = datetime.fromisoformat(msg["created"].replace("Z", "+00:00"))
                time = created.astimezone(local_tz).strftime("%Y-%m-%d %H:%M")
                body += f"<li><b>{sender}</b> ({time}): {text}</li>"
            body += "</ul>"

    if dms:
        body += "<h3>Direct Messages</h3><ul>"
        for msg in dms:
            sender = msg.get("personEmail", "unknown")
            text = msg.get("text", "")[:200]
            created = datetime.fromisoformat(msg["created"].replace("Z", "+00:00"))
            time = created.astimezone(local_tz).strftime("%Y-%m-%d %H:%M")
            body += f"<li><b>{sender}</b> ({time}): {text}</li>"
        body += "</ul>"

    if not mentions and not dms:
        body += "<p>No new mentions or direct messages in the last hour.</p>"

    return body


def send_email(to_email, subject, body):
    """Send email via Nylas SDK."""
    api_key = os.environ.get("NYLAS_API_KEY")
    grant_id = os.environ.get("NYLAS_GRANT_ID")
    if not api_key or not grant_id:
        sys.exit("Error: NYLAS_API_KEY and NYLAS_GRANT_ID environment variables required")

    nylas = NylasClient(api_key=api_key)
    nylas.messages.send(
        grant_id,
        request_body={
            "to": [{"email": to_email}],
            "subject": subject,
            "body": body,
        },
    )


def main():
    parser = argparse.ArgumentParser(description="Webex Email Reminders")
    parser.add_argument("--version", action="version", version="%(prog)s 0.5.0")
    parser.add_argument("--hours", type=float, default=1, help="Look back period in hours (default: 1)")
    parser.add_argument("--minutes", type=float, help="Look back period in minutes (overrides --hours)")
    parser.add_argument("--to", help="Email address to send summary to")
    parser.add_argument("--to-list", help="Text file with email addresses to send to (one per line)")
    parser.add_argument("--contacts", help="Text file with email addresses to filter DMs (one per line)")
    parser.add_argument("--include-all", action="store_true", help="Include all messages in active spaces, not just mentions")
    parser.add_argument("--include-my-messages", action="store_true", help="Include your own messages in DMs (excluded by default)")
    parser.add_argument("--dry-run", action="store_true", help="Print summary without sending email")
    args = parser.parse_args()

    if not args.to and not args.to_list:
        parser.error("either --to or --to-list is required")

    since = datetime.now(timezone.utc) - timedelta(minutes=args.minutes if args.minutes else args.hours * 60)
    headers = get_webex_headers()

    print(f"Checking Webex for activity since {since.isoformat()}...")

    me = get_me(headers)
    my_email = me.get("emails", [""])[0]

    mentions = get_mentions(headers, since, include_all=args.include_all)
    print(f"  Found {len(mentions)} mention(s)")

    dms = get_direct_messages(headers, since, my_email, args.contacts, include_my_messages=args.include_my_messages)
    print(f"  Found {len(dms)} direct message(s)")

    if not mentions and not dms:
        print("Nothing to report.")
        return

    body = format_email_body(mentions, dms)
    subject = f"Webex Summary - {len(mentions)} mention(s), {len(dms)} DM(s)"

    recipients = []
    if args.to:
        recipients.append(args.to)
    if args.to_list and os.path.exists(args.to_list):
        with open(args.to_list) as f:
            recipients.extend(line.strip() for line in f if line.strip())

    if args.dry_run:
        print(f"\n--- DRY RUN ---\nTo: {', '.join(recipients)}\nSubject: {subject}\n\n{body}")
    else:
        for recipient in recipients:
            send_email(recipient, subject, body)
        print(f"Email sent to {', '.join(recipients)}")


if __name__ == "__main__":
    main()
