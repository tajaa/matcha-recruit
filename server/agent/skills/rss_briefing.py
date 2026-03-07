"""RSS Briefing skill — fetches whitelisted RSS feeds, summarizes via Gemini."""

import logging
from datetime import datetime

import feedparser

logger = logging.getLogger(__name__)


async def run(config, sandbox) -> str | None:
    """Fetch RSS feeds and generate a daily briefing."""
    if not config.rss_feeds:
        logger.info("No RSS feeds configured, skipping")
        return None

    today = datetime.now().strftime("%Y-%m-%d")
    output_file = f"output/briefing-{today}.md"

    # Check if we already generated today's briefing
    existing = sandbox.fs.list_dir("output")
    if f"briefing-{today}.md" in existing:
        logger.info(f"Briefing for {today} already exists, skipping")
        return output_file

    all_entries = []
    feed_stats = {}

    for feed_cfg in config.rss_feeds:
        url = feed_cfg["url"]
        name = feed_cfg.get("name", url)
        try:
            raw = await sandbox.fetcher.fetch(url)
            parsed = feedparser.parse(raw)
            entries = parsed.entries[:config.rss_max_entries_per_feed]
            feed_stats[name] = len(entries)

            for entry in entries:
                all_entries.append({
                    "source": name,
                    "title": entry.get("title", "Untitled"),
                    "link": entry.get("link", ""),
                    "summary": entry.get("summary", "")[:500],
                })

            logger.info(f"Fetched {len(entries)} entries from {name}")

        except Exception as e:
            logger.error(f"Failed to fetch {name} ({url}): {e}")
            logger.error(f"Allowed URLs: {sandbox.fetcher._allowed}")
            feed_stats[name] = 0

    if not all_entries:
        logger.warning("No entries fetched from any feed")
        content = f"# Daily Briefing — {today}\n\nNo articles could be fetched. Check feed URLs and network.\n"
        sandbox.fs.write(output_file, content)
        return output_file

    # Build prompt for Gemini
    articles_text = "\n\n".join(
        f"[{e['source']}] {e['title']}\n{e['link']}\n{e['summary']}"
        for e in all_entries
    )

    prompt = f"""Summarize these articles into a daily briefing. Group by topic.
Highlight anything relevant to: {config.rss_interests}

Format as markdown with:
- A "Top Stories" section for the most important items
- Topic sections (AI & Tech, Business, etc.) as appropriate
- Each item: bold title, 1-2 sentence summary, source attribution
- Keep it concise and scannable

Articles:
{articles_text}"""

    try:
        summary = await sandbox.llm.generate(prompt)
    except Exception as e:
        logger.error(f"Gemini summarization failed: {e}")
        summary = "Gemini summarization failed. Raw articles below.\n\n" + articles_text

    # Build final output
    now = datetime.now().strftime("%I:%M %p")
    source_line = ", ".join(f"{name} ({count})" for name, count in feed_stats.items())
    total = sum(feed_stats.values())

    briefing = f"""# Daily Briefing — {today}

Generated at {now} · {len(feed_stats)} feeds · {total} articles scanned

{summary}

---
_Sources: {source_line}_
"""

    sandbox.fs.write(output_file, briefing)
    logger.info(f"Briefing written to {output_file}")
    return output_file
