"""Quick email check — fetch, summarize with Qwen (or Gemini), print.

Usage:
    ./run.sh --email              # fetch latest unread, summarize with Qwen
    ./run.sh --email -n 5         # fetch 5 emails
    ./run.sh --email --gemini     # summarize with Gemini instead
"""

import argparse
import asyncio

from .config import load_config
from .sandbox import Sandbox


async def run(max_emails: int = 1, force_gemini: bool = False):
    config = load_config()
    config.gmail_enabled = True

    if force_gemini:
        config.local_model_path = ""

    sandbox = Sandbox(config)

    if sandbox.gmail is None or not sandbox.gmail.is_configured:
        print("Gmail not configured. Run: python -m agent.gmail_auth")
        return

    print("Fetching emails...")
    messages = await sandbox.gmail.fetch_unread(max_results=max_emails)

    if not messages:
        print("No unread emails.")
        return

    print(f"Found {len(messages)} email(s), summarizing...\n")

    emails = []
    for msg in messages:
        email = await sandbox.gmail.get_message(msg["id"])
        emails.append(email)

    # Build summary prompt
    emails_text = "\n\n---\n\n".join(
        f"From: {e['from']}\nSubject: {e['subject']}\nDate: {e['date']}\n\n{e['body'][:2000]}"
        for e in emails
    )

    prompt = f"""Summarize these emails concisely. For each email:
- Bold the subject
- Show the sender
- 1-2 sentence summary
- Flag any action items

Emails:
{emails_text}"""

    summary = await sandbox.llm.generate(prompt)
    print(summary)

    if sandbox.llm is sandbox.local:
        model_name = config.local_model_path.rsplit("/", 1)[-1].replace(".gguf", "")
    else:
        model_name = f"Gemini ({config.gemini_model})"
    print(f"\n\033[2m— summarized with {model_name}\033[0m")

    # Clean up llama-server if it was started
    if sandbox.local:
        sandbox.local.stop()


def main():
    parser = argparse.ArgumentParser(description="Quick email check")
    parser.add_argument("-n", type=int, default=1, help="Number of emails to fetch (default: 1)")
    parser.add_argument("--gemini", action="store_true", help="Use Gemini instead of local model")
    args = parser.parse_args()
    asyncio.run(run(max_emails=args.n, force_gemini=args.gemini))


if __name__ == "__main__":
    main()
