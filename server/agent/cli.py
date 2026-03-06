"""Interactive agent CLI — chat, drag-and-drop files, run skills on demand."""

import argparse
import asyncio
import logging
import os
import readline  # noqa: F401 — enables input() history/editing
import shutil
from datetime import datetime
from pathlib import Path

from .config import load_config
from .sandbox import Sandbox, SandboxViolation

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agent.cli")

def _make_banner(llm_label: str) -> str:
    return f"""
\033[1mmatcha-agent\033[0m — drop files or type a message
  \033[32mLLM: {llm_label}\033[0m

  \033[2mDrag a file here to process it
  Type a message to chat with the agent
  /briefing   — run RSS briefing now
  /email      — fetch and summarize Gmail
  /draft      — draft a reply to an email
  /schedule   — create a calendar event from an email
  /inbox      — show pending inbox files
  /output     — list recent outputs
  /feeds      — show RSS feeds
  /clear      — reset conversation
  /quit       — exit\033[0m
"""


class AgentCLI:
    def __init__(self, force_gemini: bool = False):
        self.config = load_config()
        self.sandbox = Sandbox(self.config)
        if force_gemini:
            self.sandbox.llm = self.sandbox.gemini
        self.conversation: list[dict] = []
        self.processed_files: list[str] = []

    def _llm_label(self) -> str:
        if self.sandbox.llm is self.sandbox.local:
            return Path(self.config.local_model_path).stem
        return f"Gemini ({self.config.gemini_model})"

    def run(self):
        print(_make_banner(self._llm_label()))
        while True:
            try:
                user_input = input("\n\033[1m>\033[0m ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n")
                break

            if not user_input:
                continue

            if self._is_command(user_input):
                self._handle_command(user_input)
            elif self._is_file_path(user_input):
                asyncio.run(self._process_file(user_input))
            else:
                asyncio.run(self._chat(user_input))

    _COMMANDS = {"/quit", "/exit", "/briefing", "/email", "/draft", "/schedule", "/inbox", "/output", "/feeds", "/clear", "/help"}

    def _is_command(self, text: str) -> bool:
        return text.split()[0].lower() in self._COMMANDS

    def _is_file_path(self, text: str) -> bool:
        """Detect dragged-in file paths (may have quotes or trailing spaces).

        Returns True for anything that looks like a path — the caller
        handles "file not found" gracefully.
        """
        cleaned = text.strip().strip("'\"").strip()
        # Absolute path or home-relative path with an extension
        if cleaned.startswith(("/", "~")):
            p = Path(cleaned).expanduser()
            # It's a real file
            if p.is_file():
                return True
            # Looks like a file path (has an extension or known parent exists)
            if p.suffix or p.parent.is_dir():
                return True
        return False

    def _clean_path(self, text: str) -> str:
        return text.strip().strip("'\"").strip()

    async def _process_file(self, raw_path: str):
        """Copy file to inbox, process it, show the summary."""
        src = Path(self._clean_path(raw_path)).expanduser()

        if not src.is_file():
            print(f"\n\033[31mFile not found: {src}\033[0m")
            return

        filename = src.name

        print(f"\n\033[2mProcessing {filename}...\033[0m")

        # Copy to inbox
        inbox_path = Path(self.config.workspace_root) / "inbox" / filename
        inbox_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(inbox_path))

        # Read and summarize
        content = self.sandbox.fs.read(f"inbox/{filename}")
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        base = filename.rsplit(".", 1)[0] if "." in filename else filename

        prompt = self._build_file_prompt(filename, content)

        try:
            summary = await self.sandbox.llm.generate(prompt)
        except Exception as e:
            print(f"\n\033[31mGemini error: {e}\033[0m")
            return

        # Save output
        output_name = f"output/processed-{base}-{timestamp}.md"
        output_content = f"# File Summary: {filename}\n\nProcessed at {datetime.now().strftime('%I:%M %p')}\n\n{summary}\n\n---\n_Original: processed/{filename}_\n"
        self.sandbox.fs.write(output_name, output_content)
        self.sandbox.fs.move(f"inbox/{filename}", f"processed/{filename}")

        # Track in conversation context
        self.conversation.append({"role": "user", "content": f"[Dropped file: {filename}]"})
        self.conversation.append({"role": "agent", "content": summary})
        self.processed_files.append(filename)

        print(f"\n{summary}")
        print(f"\n\033[2mSaved to {output_name}\033[0m")

    async def _chat(self, message: str):
        """Chat with the agent, with context from processed files and conversation."""
        self.conversation.append({"role": "user", "content": message})

        context_parts = []
        if self.processed_files:
            context_parts.append(
                f"Files processed this session: {', '.join(self.processed_files)}"
            )

        # Include recent conversation for continuity
        recent = self.conversation[-20:]
        history = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Agent'}: {m['content']}"
            for m in recent[:-1]  # exclude current message
        )
        if history:
            context_parts.append(f"Conversation so far:\n{history}")

        context_block = "\n\n".join(context_parts)

        prompt = f"""You are a helpful assistant running inside a sandboxed agent.
You can discuss files the user has dropped in, provide analysis, and answer questions.
Be concise and direct.

{context_block}

User: {message}"""

        print()
        try:
            response = await self.sandbox.llm.generate(prompt)
        except Exception as e:
            print(f"\033[31mLLM error: {e}\033[0m")
            return

        self.conversation.append({"role": "agent", "content": response})
        print(response)

    def _handle_command(self, cmd: str):
        parts = cmd.strip().split()
        command = parts[0].lower()

        if command == "/quit" or command == "/exit":
            raise SystemExit(0)

        elif command == "/briefing":
            asyncio.run(self._run_briefing())

        elif command == "/email":
            asyncio.run(self._run_email())

        elif command == "/draft":
            asyncio.run(self._run_draft())

        elif command == "/schedule":
            asyncio.run(self._run_schedule())

        elif command == "/inbox":
            files = self.sandbox.fs.list_dir("inbox")
            files = [f for f in files if not f.startswith(".")]
            if files:
                print(f"\nInbox ({len(files)} files):")
                for f in files:
                    print(f"  {f}")
            else:
                print("\nInbox is empty")

        elif command == "/output":
            files = self.sandbox.fs.list_dir("output")
            files = [f for f in files if not f.startswith(".")]
            files.sort(reverse=True)
            if files:
                print(f"\nOutput ({len(files)} files):")
                for f in files[:10]:
                    print(f"  {f}")
            else:
                print("\nNo output files yet")

        elif command == "/feeds":
            if self.config.rss_feeds:
                print("\nRSS Feeds:")
                for feed in self.config.rss_feeds:
                    print(f"  {feed.get('name', 'unnamed')} — {feed['url']}")
            else:
                print("\nNo feeds configured")

        elif command == "/clear":
            self.conversation.clear()
            self.processed_files.clear()
            print("\nConversation cleared")

        elif command == "/help":
            local_name = Path(self.config.local_model_path).stem if self.config.local_model_path else None
            print(_make_banner(local_name))

        else:
            print(f"\nUnknown command: {command}")

    async def _run_briefing(self):
        from .skills import rss_briefing

        print("\n\033[2mFetching RSS feeds...\033[0m")
        try:
            result = await rss_briefing.run(self.config, self.sandbox)
            if result:
                content = self.sandbox.fs.read(result)
                print(f"\n{content}")
            else:
                print("\nNo briefing generated")
        except Exception as e:
            print(f"\n\033[31mBriefing failed: {e}\033[0m")

    async def _run_email(self):
        if self.sandbox.gmail is None:
            print(
                "\n\033[33mGmail not configured.\033[0m\n"
                "  1. Set AGENT_GMAIL_ENABLED=true\n"
                "  2. Run: python -m agent.gmail_auth\n"
            )
            return

        from .skills import email_inbox

        print("\n\033[2mFetching unread emails...\033[0m")
        try:
            result = await email_inbox.run(self.config, self.sandbox)
            if result:
                content = self.sandbox.fs.read(result)
                print(f"\n{content}")
            else:
                print("\nNo new emails or digest already generated today")
        except Exception as e:
            print(f"\n\033[31mEmail fetch failed: {e}\033[0m")

    async def _run_draft(self):
        if self.sandbox.gmail is None:
            print(
                "\n\033[33mGmail not configured.\033[0m\n"
                "  1. Set AGENT_GMAIL_ENABLED=true\n"
                "  2. Run: python -m agent.gmail_auth\n"
            )
            return

        # Show recent emails to pick from
        print("\n\033[2mFetching recent emails...\033[0m")
        try:
            messages = await self.sandbox.gmail.fetch_unread(max_results=5)
        except Exception as e:
            print(f"\n\033[31mFetch failed: {e}\033[0m")
            return

        if not messages:
            print("\nNo unread emails to reply to.")
            return

        emails = []
        for msg in messages:
            email = await self.sandbox.gmail.get_message(msg["id"])
            emails.append(email)

        print()
        for i, e in enumerate(emails, 1):
            print(f"  {i}. {e['subject']}  \033[2m— {e['from']}\033[0m")

        try:
            choice = input("\n\033[1mReply to which? (number):\033[0m ").strip()
            idx = int(choice) - 1
            if idx < 0 or idx >= len(emails):
                print("Invalid choice.")
                return
        except (ValueError, EOFError):
            print("Cancelled.")
            return

        email = emails[idx]
        instructions = input("\033[1mReply instructions (or Enter for auto):\033[0m ").strip()

        prompt = f"""Draft a professional reply to this email. Do NOT include a subject line — just the body text.
{f"Instructions: {instructions}" if instructions else "Write a helpful, concise reply."}

Original email:
From: {email['from']}
Subject: {email['subject']}
Body:
{email['body'][:3000]}"""

        print("\n\033[2mDrafting reply...\033[0m")
        try:
            draft_body = await self.sandbox.llm.generate(prompt)
        except Exception as e:
            print(f"\n\033[31mLLM error: {e}\033[0m")
            return

        print(f"\n{'='*50}")
        print(f"To: {email['from']}")
        print(f"Re: {email['subject']}")
        print(f"{'='*50}")
        print(f"\n{draft_body}\n")

        confirm = input("\033[1mSave to Drafts? (y/n):\033[0m ").strip().lower()
        if confirm != "y":
            print("Discarded.")
            return

        try:
            result = await self.sandbox.gmail.create_draft(
                to=email["from"],
                subject=f"Re: {email['subject']}",
                body=draft_body,
            )
            print(f"\n\033[32mDraft saved.\033[0m Open Gmail to review and send.")
        except Exception as e:
            print(f"\n\033[31mFailed to save draft: {e}\033[0m")

    async def _run_schedule(self):
        if self.sandbox.calendar is None:
            print(
                "\n\033[33mCalendar not configured.\033[0m\n"
                "  1. Set AGENT_GMAIL_ENABLED=true\n"
                "  2. Run: python -m agent.gmail_auth  (re-auth to add calendar scope)\n"
            )
            return

        print("\n\033[2mFetching recent emails...\033[0m")
        try:
            messages = await self.sandbox.gmail.fetch_unread(max_results=5)
        except Exception as e:
            print(f"\n\033[31mFetch failed: {e}\033[0m")
            return

        if not messages:
            print("\nNo unread emails.")
            return

        emails = []
        for msg in messages:
            email = await self.sandbox.gmail.get_message(msg["id"])
            emails.append(email)

        print()
        for i, e in enumerate(emails, 1):
            print(f"  {i}. {e['subject']}  \033[2m— {e['from']}\033[0m")

        try:
            choice = input("\n\033[1mSchedule from which email? (number):\033[0m ").strip()
            idx = int(choice) - 1
            if idx < 0 or idx >= len(emails):
                print("Invalid choice.")
                return
        except (ValueError, EOFError):
            print("Cancelled.")
            return

        email = emails[idx]

        prompt = f"""Extract meeting/event details from this email. Return ONLY valid JSON with these fields:
- "summary": event title (string)
- "start": start datetime in ISO 8601 with timezone, e.g. "2026-03-10T14:00:00-08:00" (string)
- "end": end datetime in ISO 8601 with timezone (string) — if duration not specified, default to 1 hour
- "description": brief description or agenda (string or null)
- "attendees": list of email addresses mentioned (list of strings, or empty list)
- "location": meeting location or video link if mentioned (string or null)

If you cannot determine a date/time, use your best guess based on context (today is {datetime.now().strftime('%Y-%m-%d')}).

Email:
From: {email['from']}
Subject: {email['subject']}
Date: {email['date']}
Body:
{email['body'][:3000]}"""

        print("\n\033[2mExtracting event details...\033[0m")
        try:
            raw = await self.sandbox.llm.generate(prompt)
        except Exception as e:
            print(f"\n\033[31mLLM error: {e}\033[0m")
            return

        # Parse JSON from LLM response (may be wrapped in ```json blocks)
        import json
        import re
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not json_match:
            print(f"\n\033[31mCouldn't parse event details from LLM response.\033[0m")
            print(raw)
            return

        try:
            event_data = json.loads(json_match.group())
        except json.JSONDecodeError:
            print(f"\n\033[31mInvalid JSON from LLM.\033[0m")
            print(raw)
            return

        # Display parsed event for confirmation
        print(f"\n{'='*50}")
        print(f"  Title:     {event_data.get('summary', '(none)')}")
        print(f"  Start:     {event_data.get('start', '(none)')}")
        print(f"  End:       {event_data.get('end', '(none)')}")
        if event_data.get('location'):
            print(f"  Location:  {event_data['location']}")
        if event_data.get('attendees'):
            print(f"  Attendees: {', '.join(event_data['attendees'])}")
        if event_data.get('description'):
            print(f"  Notes:     {event_data['description'][:100]}")
        print(f"{'='*50}")

        confirm = input("\n\033[1mCreate this event? (y/n):\033[0m ").strip().lower()
        if confirm != "y":
            print("Cancelled.")
            return

        try:
            result = await self.sandbox.calendar.create_event(
                summary=event_data.get("summary", email["subject"]),
                start=event_data["start"],
                end=event_data["end"],
                description=event_data.get("description"),
                attendees=event_data.get("attendees") or None,
                location=event_data.get("location"),
            )
            link = result.get("htmlLink", "")
            print(f"\n\033[32mEvent created.\033[0m")
            if link:
                print(f"  {link}")
        except Exception as e:
            print(f"\n\033[31mFailed to create event: {e}\033[0m")

    def _build_file_prompt(self, filename: str, content: str) -> str:
        context = ""
        if self.processed_files:
            context = f"\nPreviously processed files this session: {', '.join(self.processed_files)}\n"

        return f"""Summarize this document. Extract:
1. A concise summary (2-4 sentences)
2. Key points (bulleted list)
3. Action items with any deadlines mentioned (as a checklist)

If the document doesn't contain action items or deadlines, note that.
{context}
Document filename: {filename}
Document contents:
{content}"""


def main():
    parser = argparse.ArgumentParser(description="matcha-agent interactive CLI")
    parser.add_argument("--gemini", action="store_true", help="Use Gemini instead of local model")
    args = parser.parse_args()

    try:
        AgentCLI(force_gemini=args.gemini).run()
    except SystemExit:
        pass


if __name__ == "__main__":
    main()
