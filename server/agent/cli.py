"""Interactive agent CLI — chat, drag-and-drop files, run skills on demand."""

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

def _make_banner(local_model: str | None) -> str:
    model_line = f"  \033[32mLocal model: {local_model}\033[0m\n" if local_model else ""
    return f"""
\033[1mmatcha-agent\033[0m — drop files or type a message
{model_line}
  \033[2mDrag a file here to process it
  Type a message to chat with the agent
  /briefing   — run RSS briefing now
  /email      — fetch and summarize Gmail
  /inbox      — show pending inbox files
  /output     — list recent outputs
  /feeds      — show RSS feeds
  /clear      — reset conversation
  /quit       — exit\033[0m
"""


class AgentCLI:
    def __init__(self):
        self.config = load_config()
        self.sandbox = Sandbox(self.config)
        self.conversation: list[dict] = []
        self.processed_files: list[str] = []

    def run(self):
        local_name = Path(self.config.local_model_path).stem if self.config.local_model_path else None
        print(_make_banner(local_name))
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

    _COMMANDS = {"/quit", "/exit", "/briefing", "/email", "/inbox", "/output", "/feeds", "/clear", "/help"}

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
            summary = await self.sandbox.gemini.generate(prompt)
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

        # Prefer local model for chat, fall back to Gemini
        llm = self.sandbox.local or self.sandbox.gemini
        label = "Local" if self.sandbox.local else "Gemini"

        print()
        try:
            response = await llm.generate(prompt)
        except Exception as e:
            print(f"\033[31m{label} error: {e}\033[0m")
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
    try:
        AgentCLI().run()
    except SystemExit:
        pass


if __name__ == "__main__":
    main()
