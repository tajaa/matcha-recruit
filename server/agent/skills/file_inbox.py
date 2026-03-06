"""File Inbox Processor — watches inbox folder, summarizes via Gemini, moves to processed."""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# File types we can process (text-based)
SUPPORTED_EXTENSIONS = {".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".xml", ".html"}


async def run(config, sandbox) -> list[str]:
    """Process all files in the inbox folder."""
    files = sandbox.fs.list_dir("inbox")
    # Filter out dotfiles and unsupported types
    files = [
        f for f in files
        if not f.startswith(".")
        and any(f.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS)
    ]

    if not files:
        logger.info("Inbox empty, nothing to process")
        return []

    logger.info(f"Found {len(files)} file(s) in inbox: {files}")
    outputs = []

    for filename in files:
        try:
            output = await _process_file(filename, sandbox)
            outputs.append(output)
        except Exception as e:
            logger.error(f"Failed to process {filename}: {e}")

    return outputs


async def _process_file(filename: str, sandbox) -> str:
    """Read a file from inbox, summarize it, write output, move to processed."""
    content = sandbox.fs.read(f"inbox/{filename}")
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    now_display = datetime.now().strftime("%I:%M %p")

    # Strip extension for the output filename
    base = filename.rsplit(".", 1)[0] if "." in filename else filename

    prompt = f"""Summarize this document. Extract:
1. A concise summary (2-4 sentences)
2. Key points (bulleted list)
3. Action items with any deadlines mentioned (as a checklist)

If the document doesn't contain action items or deadlines, note that.

Document filename: {filename}
Document contents:
{content}"""

    try:
        summary = await sandbox.gemini.generate(prompt)
    except Exception as e:
        logger.error(f"Gemini failed for {filename}: {e}")
        summary = f"Gemini summarization failed: {e}\n\nRaw content length: {len(content)} chars"

    output_name = f"output/processed-{base}-{timestamp}.md"
    output_content = f"""# File Summary: {filename}

Processed at {now_display}

{summary}

---
_Original: processed/{filename}_
"""

    sandbox.fs.write(output_name, output_content)

    # Move original to processed
    sandbox.fs.move(f"inbox/{filename}", f"processed/{filename}")

    logger.info(f"Processed {filename} -> {output_name}")
    return output_name
