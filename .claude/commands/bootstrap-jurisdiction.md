Bootstrap a new jurisdiction: create it in the database and research all its compliance categories via Gemini. Writes results to a Markdown file for review.

The user will provide a city and state (e.g. "Indianapolis IN" or "bootstrap Portland OR"). Parse the city and state from their input: $ARGUMENTS

If the user also mentions a county (e.g. "Indianapolis IN county Marion"), pass it with `--county`.

Run the script from the server directory:

```
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python scripts/bootstrap_jurisdiction.py "<city>" "<state>"
```

Options:
- `--county "<name>"` — set the county for this jurisdiction.
- `--categories general|healthcare|oncology|medical_compliance|all` — filter by category group (default: all). Can be repeated.
- `--dry-run` — research and write Markdown only, do NOT create the jurisdiction in the DB.
- `--output <path>` — custom output file path (default: `scripts/<city>_<state>_compliance.md`).

**IMPORTANT**: This script INSERTs into the production database (creates a jurisdiction row). If the user didn't explicitly ask to create it, use `--dry-run` to be safe.

After running, report:
1. Whether the jurisdiction was created (or already existed, or dry-run)
2. How many categories were researched and how many requirements were found
3. Where the .md file was written
4. Any failed categories

If the jurisdiction already exists, suggest using `/fill-gaps` instead.
