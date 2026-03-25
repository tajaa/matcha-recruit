Research and seed penalty/fine data for compliance requirements that are missing enforcement information.

No arguments needed — this skill auto-discovers requirements without penalty data and enriches them.

---

## Step 1: Run the seed script

Bootstrap penalty data from hardcoded authoritative sources (Federal Register, agency websites):

```bash
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python scripts/seed_penalty_data.py
```

This covers the major categories (HIPAA, OSHA, FLSA, FCA, CMS, DEA, etc.) with official penalty ranges.

## Step 2: Find remaining gaps

Query the database for requirements that still lack penalty data:

```bash
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python -c "
import asyncio, asyncpg, os
async def main():
    conn = await asyncpg.connect(os.environ.get('DATABASE_URL', 'postgresql://matcha:matcha_dev@localhost:5432/matcha'))
    rows = await conn.fetch('''
        SELECT category, COUNT(*) as total,
               SUM(CASE WHEN metadata ? '\"'\"'penalties'\"'\"' THEN 1 ELSE 0 END) as has_penalty
        FROM jurisdiction_requirements WHERE status = '\"'\"'active'\"'\"'
        GROUP BY category ORDER BY total DESC
    ''')
    print(f'{\"Category\":<30} {\"Total\":>8} {\"Has Penalty\":>12} {\"Coverage\":>10}')
    print('-' * 65)
    for r in rows:
        pct = (r['has_penalty'] / r['total'] * 100) if r['total'] > 0 else 0
        print(f'{r[\"category\"]:<30} {r[\"total\"]:>8} {r[\"has_penalty\"]:>12} {pct:>9.0f}%')
    await conn.close()
asyncio.run(main())
"
```

## Step 3: Research missing penalties via web search

For categories with 0% coverage after seeding, use **WebSearch** to find authoritative penalty information:

**Search pattern per category:**
- `"<category> violation penalty amount 2025 2026"`
- `"<enforcing_agency> civil monetary penalties <category>"`
- `"<statute_citation> penalty provisions"`

**Authoritative sources to prioritize:**
- Federal Register (federalregister.gov) — annual inflation adjustments
- Agency enforcement pages (oig.hhs.gov, osha.gov/penalties, dol.gov/agencies/whd/penalties)
- State labor department penalty schedules

For each requirement found:
1. Identify the enforcing agency
2. Find the civil penalty range (min/max per violation)
3. Check for annual caps
4. Note criminal penalties if applicable
5. Write a one-line summary

## Step 4: Update the database

For requirements where you found penalty data, update the metadata JSONB:

```sql
UPDATE jurisdiction_requirements
SET metadata = COALESCE(metadata, '{}'::jsonb) || '{"penalties": {"enforcing_agency": "...", "summary": "..."}}'::jsonb,
    updated_at = NOW()
WHERE category = '<category>' AND status = 'active'
  AND (metadata IS NULL OR NOT (metadata ? 'penalties'));
```

## Step 5: Re-embed affected requirements

After updating penalty data, re-embed so RAG can find penalty info:

```bash
cd /Users/finch/Documents/github/matcha-recruit/server && ./venv/bin/python -c "
import asyncio
from app.config import load_settings
from app.database import init_pool, close_pool, get_pool
from app.core.services.compliance_embedding_pipeline import embed_requirements
load_settings()
async def main():
    await init_pool()
    pool = get_pool()
    async with pool.acquire() as conn:
        count = await embed_requirements(conn)
        print(f'Re-embedded {count} requirements')
    await close_pool()
asyncio.run(main())
"
```

## Step 6: Report results

Tell the user:
1. How many categories were seeded from hardcoded data
2. How many requirements were updated
3. Coverage percentage after seeding
4. Any categories that still need manual research
