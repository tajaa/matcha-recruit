"""Autonomous agent — heartbeat loop with sandboxed skill execution.

Usage:
    python -m agent.agent          # daemon mode (runs every N minutes)
    python -m agent.agent --once   # single run then exit
    python -m agent.agent --interval 5  # custom interval in minutes
"""

import argparse
import asyncio
import logging
import sys

from .config import load_config
from .sandbox import Sandbox, SandboxViolation
from .skills import rss_briefing, file_inbox, email_inbox

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("agent")


def parse_checklist(content: str) -> dict[str, bool]:
    """Parse HEARTBEAT.md checklist into {skill_name: enabled}."""
    tasks = {}
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("- [x]"):
            name = line[5:].strip().split("—")[0].split("—")[0].strip()
            tasks[name] = True
        elif line.startswith("- [ ]"):
            name = line[5:].strip().split("—")[0].split("—")[0].strip()
            tasks[name] = False
    return tasks


async def run_cycle(config, sandbox):
    """Execute one heartbeat cycle."""
    # Read checklist
    try:
        checklist_content = sandbox.fs.read("HEARTBEAT.md")
        tasks = parse_checklist(checklist_content)
    except FileNotFoundError:
        logger.warning("HEARTBEAT.md not found, running all skills")
        tasks = {"rss_briefing": True, "file_inbox": True, "email_inbox": False}

    logger.info(f"Checklist: {tasks}")

    # Execute enabled skills
    if tasks.get("rss_briefing"):
        try:
            result = await rss_briefing.run(config, sandbox)
            if result:
                logger.info(f"RSS briefing: {result}")
        except SandboxViolation as e:
            logger.error(f"RSS briefing sandbox violation: {e}")
        except Exception as e:
            logger.error(f"RSS briefing failed: {e}")

    if tasks.get("file_inbox"):
        try:
            results = await file_inbox.run(config, sandbox)
            if results:
                logger.info(f"File inbox processed: {results}")
        except SandboxViolation as e:
            logger.error(f"File inbox sandbox violation: {e}")
        except Exception as e:
            logger.error(f"File inbox failed: {e}")

    if tasks.get("email_inbox"):
        try:
            result = await email_inbox.run(config, sandbox)
            if result:
                logger.info(f"Email digest: {result}")
        except SandboxViolation as e:
            logger.error(f"Email inbox sandbox violation: {e}")
        except Exception as e:
            logger.error(f"Email inbox failed: {e}")


async def heartbeat(config):
    """Main heartbeat loop."""
    sandbox = Sandbox(config)
    logger.info(f"Agent started. Workspace: {config.workspace_root}")
    logger.info(f"Interval: {config.interval_minutes}m | Feeds: {len(config.rss_feeds)}")

    while True:
        logger.info("--- Heartbeat ---")
        await run_cycle(config, sandbox)
        logger.info(f"Heartbeat complete. Next in {config.interval_minutes}m")
        await asyncio.sleep(config.interval_minutes * 60)


async def run_once(config):
    """Single execution (no loop)."""
    sandbox = Sandbox(config)
    logger.info(f"Agent one-shot. Workspace: {config.workspace_root}")
    await run_cycle(config, sandbox)
    logger.info("Done.")


def main():
    parser = argparse.ArgumentParser(description="Sandboxed autonomous agent")
    parser.add_argument("--once", action="store_true", help="Run once then exit")
    parser.add_argument("--interval", type=int, default=None, help="Heartbeat interval in minutes")
    args = parser.parse_args()

    config = load_config(interval=args.interval)

    if args.once:
        asyncio.run(run_once(config))
    else:
        try:
            asyncio.run(heartbeat(config))
        except KeyboardInterrupt:
            logger.info("Agent stopped.")
            sys.exit(0)


if __name__ == "__main__":
    main()
