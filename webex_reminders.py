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

        # Always filter by mentionedPeople=me (this includes @All mentions)
        params = {"roomId": room["id"], "max": 20, "mentionedPeople": "me"}
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

        # If --include-all, also fetch messages that mention "All" but didn't trigger mentionedPeople=me
        if include_all:
            all_params = {"roomId": room["id"], "max": 50}
            all_resp = requests.get(
                "https://webexapis.com/v1/messages",
                headers=headers,
                params=all_params,
            )
            if all_resp.status_code != 200:
                continue
            existing_ids = {m["id"] for m in messages}
            for msg in all_resp.json().get("items", []):
                created = datetime.fromisoformat(msg["created"].replace("Z", "+00:00"))
                if created < since:
                    break
                # Check if message mentions "All" (mentionedGroups contains "all")
                if "all" in [g.lower() for g in msg.get("mentionedGroups", [])]:
                    if msg["id"] not in existing_ids:
                        msg["_spaceName"] = room.get("title", "Unknown Space")
                        messages.append(msg)

    return messages


def get_thread_replies(headers, since, my_id):
    """Get replies to threads you started in active spaces."""
    rooms_resp = requests.get(
        "https://webexapis.com/v1/rooms", headers=headers, params={"max": 50, "sortBy": "lastactivity"}
    )
    rooms_resp.raise_for_status()

    replies = []
    for room in rooms_resp.json().get("items", []):
        last_activity = datetime.fromisoformat(room["lastActivity"].replace("Z", "+00:00"))
        if last_activity < since:
            break
        if room.get("type") == "direct":
            continue

        msgs_resp = requests.get(
            "https://webexapis.com/v1/messages",
            headers=headers,
            params={"roomId": room["id"], "max": 50},
        )
        if msgs_resp.status_code != 200:
            continue

        messages = msgs_resp.json().get("items", [])
        # Find thread parents I created
        my_parent_ids = {
            msg["id"] for msg in messages
            if msg.get("personId") == my_id and not msg.get("parentId")
        }

        # Collect replies from others to my threads
        for msg in messages:
            created = datetime.fromisoformat(msg["created"].replace("Z", "+00:00"))
            if created < since:
                continue
            if msg.get("parentId") in my_parent_ids and msg.get("personId") != my_id:
                msg["_spaceName"] = room.get("title", "Unknown Space")
                replies.append(msg)

    return replies


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


def format_email_body(mentions, dms, thread_replies=None):
    """Format mentions, DMs, and thread replies into an HTML email body."""
    local_tz = datetime.now().astimezone().tzinfo
    body = "<h2>Webex Summary - Last Hour</h2>"

    if mentions:
        body += "<h3>Mentions</h3>"
        grouped = {}
        for msg in sorted(mentions, key=lambda m: m["created"]):
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

    if thread_replies:
        body += "<h3>Thread Replies</h3>"
        grouped = {}
        for msg in sorted(thread_replies, key=lambda m: m["created"]):
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
        for msg in sorted(dms, key=lambda m: m["created"]):
            sender = msg.get("personEmail", "unknown")
            text = msg.get("text", "")[:200]
            created = datetime.fromisoformat(msg["created"].replace("Z", "+00:00"))
            time = created.astimezone(local_tz).strftime("%Y-%m-%d %H:%M")
            body += f"<li><b>{sender}</b> ({time}): {text}</li>"
        body += "</ul>"

    if not mentions and not dms and not thread_replies:
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
    parser.add_argument("--version", action="version", version="%(prog)s 0.8.0")
    parser.add_argument("--hours", type=float, default=1, help="Look back period in hours (default: 1)")
    parser.add_argument("--minutes", type=float, help="Look back period in minutes (overrides --hours)")
    parser.add_argument("--to", help="Email address to send summary to")
    parser.add_argument("--to-list", help="Text file with email addresses to send to (one per line)")
    parser.add_argument("--contacts", help="Text file with email addresses to filter DMs (one per line)")
    parser.add_argument("--include-all", action="store_true", help="Include messages where @All is mentioned in spaces")
    parser.add_argument("--include-my-messages", action="store_true", help="Include your own messages in DMs (excluded by default)")
    parser.add_argument("--thread-replies", action="store_true", help="Include replies to threads you started")
    parser.add_argument("--email-errors", action="store_true", help="Email exceptions from Webex API calls to recipients instead of failing silently")
    parser.add_argument("--dry-run", action="store_true", help="Print summary without sending email")
    args = parser.parse_args()

    if not args.to and not args.to_list:
        parser.error("either --to or --to-list is required")

    since = datetime.now(timezone.utc) - timedelta(minutes=args.minutes if args.minutes else args.hours * 60)
    headers = get_webex_headers()

    # Collect recipients early so --email-errors can use them
    recipients = []
    if args.to:
        recipients.append(args.to)
    if args.to_list and os.path.exists(args.to_list):
        with open(args.to_list) as f:
            recipients.extend(line.strip() for line in f if line.strip())

    print(f"Checking Webex for activity since {since.astimezone().strftime('%Y-%m-%d %H:%M %Z')}...")

    try:
        me = get_me(headers)
        my_email = me.get("emails", [""])[0]

        mentions = get_mentions(headers, since, include_all=args.include_all)
        print(f"  Found {len(mentions)} mention(s)")

        thread_replies = []
        if args.thread_replies:
            my_id = me.get("id", "")
            thread_replies = get_thread_replies(headers, since, my_id)
            print(f"  Found {len(thread_replies)} thread reply(ies)")

        dms = get_direct_messages(headers, since, my_email, args.contacts, include_my_messages=args.include_my_messages)
        print(f"  Found {len(dms)} direct message(s)")
    except Exception as e:
        if args.email_errors and recipients and not args.dry_run:
            import traceback
            traceback.print_exc()
            error_body = (
                "<h2>Webex Email Reminders - Error</h2>"
                f"<p>An exception occurred while fetching Webex data:</p>"
                f"<pre>{traceback.format_exc()}</pre>"
            )
            error_subject = f"Webex Reminders Error: {type(e).__name__}: {e}"
            for recipient in recipients:
                send_email(recipient, error_subject, error_body)
            print(f"Error emailed to {', '.join(recipients)}", file=sys.stderr)
            return
        else:
            raise

    if not mentions and not dms and not thread_replies:
        print("Nothing to report.")
        return

    body = format_email_body(mentions, dms, thread_replies)
    subject = f"Webex Summary - {len(mentions)} mention(s), {len(dms)} DM(s)"
    if thread_replies:
        subject += f", {len(thread_replies)} thread reply(ies)"

    if args.dry_run:
        print(f"\n--- DRY RUN ---\nTo: {', '.join(recipients)}\nSubject: {subject}\n\n{body}")
    else:
        for recipient in recipients:
            send_email(recipient, subject, body)
        print(f"Email sent to {', '.join(recipients)}")


if __name__ == "__main__":
    main()
