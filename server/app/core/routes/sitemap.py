"""Sitemap + robots.txt for Google/Bing/Anthropic crawlers.

Mounted at the FastAPI app root (no /api prefix) — crawlers expect
/sitemap.xml at the canonical domain root.
"""

from datetime import datetime, timezone
from xml.sax.saxutils import escape

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response

from ...database import get_connection

router = APIRouter()

CANONICAL_HOST = "hey-matcha.com"


# ── Static public routes ────────────────────────────────────────────────────
# Mirror App.tsx public routes. Auth-gated routes (/app/*, /admin/*, /broker/*,
# /work/*, /resources/templates, /resources/states/*, /resources/audit) are
# excluded — those go behind RequireBusinessAccount and shouldn't be indexed.

STATIC_ROUTES: list[tuple[str, str, float]] = [
    # path, changefreq, priority
    ("/", "weekly", 1.0),
    ("/matcha-work", "monthly", 0.8),
    ("/matcha-lite", "monthly", 0.8),
    ("/services", "monthly", 0.7),
    ("/blog", "weekly", 0.7),
    ("/resources", "weekly", 0.9),
    ("/resources/glossary", "monthly", 0.8),
    ("/resources/templates/job-descriptions", "weekly", 0.9),
    ("/resources/calculators", "monthly", 0.8),
    ("/resources/calculators/pto-accrual", "monthly", 0.7),
    ("/resources/calculators/turnover-cost", "monthly", 0.7),
    ("/resources/calculators/overtime", "monthly", 0.7),
    ("/resources/calculators/total-comp", "monthly", 0.7),
    ("/signup", "yearly", 0.5),
    ("/login", "yearly", 0.3),
]


# ── Glossary slugs — mirror client/src/pages/landing/resources/glossaryData.ts ─

GLOSSARY_SLUGS: list[str] = [
    "flsa", "fmla", "ada", "adaaa", "aca", "cobra", "hipaa", "eeoc", "osha",
    "dol", "nlrb", "title-vii", "adea", "owbpa", "gina", "pda", "pwfa",
    "pump-act", "erisa", "fcra", "warn", "userra", "i-9", "w-2", "w-4",
    "1099", "fica", "futa", "suta", "eeo-1", "ofccp", "exempt", "overtime",
    "minimum-wage", "at-will-employment", "wrongful-termination",
    "constructive-discharge", "disparate-treatment", "disparate-impact",
    "hostile-work-environment", "quid-pro-quo", "reasonable-accommodation",
    "retaliation", "protected-class", "ban-the-box", "bfoq", "pip", "pto",
    "paid-family-leave", "crown-act", "pay-transparency", "equal-pay-act",
    "misclassification",
]


# ── Job description slugs — mirror jobDescriptionsData.ts (62 entries) ──────

JD_SLUGS: list[str] = [
    "front-desk-agent", "housekeeper", "housekeeping-supervisor", "concierge",
    "event-coordinator", "registered-nurse", "lvn-lpn", "medical-assistant",
    "cna", "phlebotomist", "medical-receptionist", "behavioral-health-technician",
    "home-health-aide", "retail-sales-associate", "cashier", "store-manager",
    "assistant-store-manager", "visual-merchandiser", "stock-associate",
    "line-cook", "prep-cook", "server", "bartender", "host", "dishwasher",
    "shift-leader", "general-manager-restaurant", "delivery-driver",
    "electrician", "plumber", "hvac-technician", "carpenter",
    "project-superintendent", "safety-officer", "production-operator",
    "forklift-operator", "warehouse-associate", "shipping-receiving-clerk",
    "maintenance-technician", "quality-inspector", "hr-generalist",
    "hr-business-partner", "recruiter", "office-manager", "executive-assistant",
    "accountant", "bookkeeper", "payroll-specialist", "paralegal",
    "software-engineer", "senior-software-engineer", "product-manager",
    "designer", "devops-engineer", "data-analyst", "it-support-specialist",
    "account-executive", "sdr", "customer-success-manager", "marketing-manager",
    "content-marketer", "social-media-manager",
]


def _canonical_base(request: Request) -> str:
    """Resolve canonical https origin for absolute sitemap URLs.

    Always emit hey-matcha.com (or www.hey-matcha.com) for crawlers — never
    leak localhost or internal hostnames into the indexed sitemap.
    """
    host = request.headers.get("host", "")
    if host in ("hey-matcha.com", "www.hey-matcha.com"):
        return f"https://{host}"
    if host.startswith("localhost") or host.startswith("127.0.0.1") or not host:
        return f"https://{CANONICAL_HOST}"
    return f"https://{CANONICAL_HOST}"


def _xml_url(loc: str, lastmod: str, changefreq: str, priority: float) -> str:
    return (
        "  <url>\n"
        f"    <loc>{escape(loc)}</loc>\n"
        f"    <lastmod>{lastmod}</lastmod>\n"
        f"    <changefreq>{changefreq}</changefreq>\n"
        f"    <priority>{priority:.1f}</priority>\n"
        "  </url>\n"
    )


@router.get("/sitemap.xml")
async def sitemap(request: Request):
    base = _canonical_base(request)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Pull dynamic blog post slugs (only published)
    blog_entries: list[tuple[str, str]] = []
    try:
        async with get_connection() as conn:
            rows = await conn.fetch(
                "SELECT slug, COALESCE(updated_at, published_at, created_at) AS lastmod "
                "FROM blog_posts WHERE status = 'published' "
                "ORDER BY COALESCE(updated_at, published_at, created_at) DESC"
            )
            for r in rows:
                lm = r["lastmod"]
                lm_str = lm.strftime("%Y-%m-%d") if lm else today
                blog_entries.append((r["slug"], lm_str))
    except Exception:
        # If DB is unreachable or table doesn't exist yet, still emit the rest.
        blog_entries = []

    parts: list[str] = []
    parts.append('<?xml version="1.0" encoding="UTF-8"?>\n')
    parts.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')

    for path, changefreq, priority in STATIC_ROUTES:
        parts.append(_xml_url(f"{base}{path}", today, changefreq, priority))

    for slug in JD_SLUGS:
        parts.append(_xml_url(
            f"{base}/resources/templates/job-descriptions/{slug}",
            today, "monthly", 0.8,
        ))

    for slug in GLOSSARY_SLUGS:
        parts.append(_xml_url(
            f"{base}/resources/glossary/{slug}",
            today, "monthly", 0.6,
        ))

    for slug, lm in blog_entries:
        parts.append(_xml_url(
            f"{base}/blog/{slug}", lm, "weekly", 0.7,
        ))

    parts.append("</urlset>\n")

    return Response(
        content="".join(parts),
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots(request: Request):
    base = _canonical_base(request)
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /app/\n"
        "Disallow: /admin/\n"
        "Disallow: /broker/\n"
        "Disallow: /work/\n"
        "Disallow: /api/\n"
        "Disallow: /auth/\n"
        "Disallow: /sso/\n"
        "Disallow: /reset-password\n"
        "Disallow: /register/\n"
        "Disallow: /candidate-interview/\n"
        "Disallow: /report/\n"
        "Disallow: /s/\n"
        "Disallow: /resources/templates\n"
        "Disallow: /resources/states\n"
        "Disallow: /resources/audit\n"
        "\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )
