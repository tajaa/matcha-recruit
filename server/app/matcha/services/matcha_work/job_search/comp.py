"""Pay facts from posting text and ATS fields. Pure: no I/O, no model.

Every value carries evidence: the exact text it was read from (`quote`), where
(`url`) and how (`origin`: google_jobs, ats_api, jsonld or page). A quote from
text is a slice of that text, so a later check can find it again; structured
fields (an ATS salary range, JSON-LD `baseSalary`) are quoted as the field and
its raw values.

A missing number is "not posted", never zero. Text scanning is deliberately
conservative:

* outside a known pay field, an amount needs a currency or a K ("$85 an
  hour", "150K"), so "12 hour days" and "24 hour on-call" are not pay;
* "401k", "403(b)" and "457(b)" are retirement plans, never a salary;
* an amount near "budget", "revenue" or "Series B" is not pay unless the
  sentence also says salary;
* a percentage is a bonus (or equity) only in the same clause as the word:
  "a 401(k) match of 4% and an annual bonus" is a mentioned bonus, not 4%.
"""
from __future__ import annotations

import re
from typing import Any

PERIOD_FACTORS = {"year": 1, "month": 12, "week": 52, "day": 260, "hour": 2080}
_SYMBOLS = {"$": "USD", "£": "GBP", "€": "EUR"}
_CODES = ("USD", "CAD", "EUR", "GBP", "AUD")
MIN_ANNUAL = 15_000
MAX_ANNUAL = 3_000_000
MAX_QUOTE = 300

_CUR = r"(?:[$£€]|(?:USD|CAD|EUR|GBP|AUD)\s?)"
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_SUF = r"[kKmM](?![a-zA-Z])"


def _amt(p: str) -> str:
    return rf"(?P<{p}cur>{_CUR})?(?P<{p}num>{_NUM})\s?(?P<{p}suf>{_SUF})?"


_PERIOD = (
    r"\s*(?:/\s*|per\s+|an?\s+|each\s+)?"
    r"(?P<period>year|yr|annum|annually|annual|month|mo|week|wk|day|hour|hr|hourly)\b"
)
_RANGE_RE = re.compile(
    _amt("a") + r"\s*(?:-|–|—|to)\s*" + _amt("b") + rf"(?:{_PERIOD})?",
)
_SINGLE_RE = re.compile(
    r"(?<![\d.,])" + _amt("a") + rf"(?:{_PERIOD})?",
)
_PERIOD_WORDS = {
    "year": "year", "yr": "year", "annum": "year", "annually": "year", "annual": "year",
    "month": "month", "mo": "month", "week": "week", "wk": "week", "day": "day",
    "hour": "hour", "hr": "hour", "hourly": "hour",
}
_PAY_WORDS = re.compile(
    r"\b(salary|salaries|base|pay|compensation|comp|wage|wages|ote|earn|earnings|range)\b", re.I,
)
_NOT_PAY = re.compile(
    r"\b(budget|revenue|revenues|arr|funding|funded|raised|series\s+[a-f]|valuation|aum|"
    r"assets under|portfolio|p&l|sales of|deal size|market cap|savings|ebitda|investment)\b",
    re.I,
)
# "20%", "20–30%", "20% to 30%", "0.5%-1.0%".
_PCT = (r"(?P<lo>\d{1,2}(?:\.\d+)?)\s?%?\s*(?:-|–|—|to)\s*(?P<hi>\d{1,2}(?:\.\d+)?)\s?%"
        r"|(?P<one>\d{1,2}(?:\.\d+)?)\s?%")
_PCT_RE = re.compile(_PCT)
_BONUS_WORD = re.compile(r"\bbonus(es)?\b|\bshort[- ]term incentive\b|\bSTI\b", re.I)
_BONUS_MENTION = re.compile(
    r"\b(annual|target|performance|discretionary|incentive|cash|quarterly|year[- ]end)\s+bonus(es)?\b"
    r"|\bbonus\s+(eligib\w*|potential|program|plan|opportunit\w*|structure|target)\b"
    r"|(?:\+|\bplus\b|&)\s*(?:an?\s+)?bonus\b"
    r"|\bshort[- ]term incentive\b",
    re.I,
)
# "Spanish is a bonus", "would be a big bonus": a nice-to-have, not pay. "Plus a
# bonus of up to 20%" is pay, so a bare "a bonus" is not excluded.
_NOT_BONUS = re.compile(
    r"\b(is|be|as|considered)\s+(a\s+)?(huge\s+|big\s+|nice\s+|real\s+|definite\s+|strong\s+)?bonus\b"
    r"|\bbonus points?\b",
    re.I,
)
# Between a percentage and its word: a clause break or another benefit means
# the number belongs to something else.
_CLAUSE_BREAK = re.compile(
    r"[,;.\n•]|\b(and|or|match|matching|401|403|457|pto|vacation|discount|travel|commission|raise|"
    r"equity|bonus|options|stock)\b",
    re.I,
)
_RETIREMENT = re.compile(r"(?:401|403|457)\s?\(?[kKbB]\)?")
_SIGNING = re.compile(r"\b(sign(ing)?[- ]on|signing)\b", re.I)
_EQUITY_WORD = re.compile(
    r"\bequity\b|\bstock options?\b|\boptions\b|\bRSUs?\b|\brestricted stock\b|\bprofits? interests?\b"
    r"|\bownership\b|\bshares\b",
    re.I,
)
_EQUITY_MENTION = re.compile(
    r"\bequity\s+(package|grant|grants|compensation|incentive|participation|award|awards|stake|"
    r"component|upside|plan|ownership)\b"
    r"|\b(meaningful|significant|generous|competitive)\s+equity\b"
    r"|\bstock options?\b|\bRSUs?\b|\brestricted stock\b|\bprofits? interests?\b|\bownership stake\b"
    r"|(?:\+|\bplus\b|&|\band\b|,)\s*equity\b",
    re.I,
)
_NOT_EQUITY_BEFORE = re.compile(
    r"(private|pay|health|diversity,?|racial|home|brand|gender|social|educational)\s*$", re.I,
)
_NOT_EQUITY_AFTER = re.compile(
    r"^\s*(-?backed|firm|firms|partners|fund|funds|sponsor|sponsors|portfolio|investor|investors|"
    r"group|capital|,?\s*(and|&)\s*inclusion|research|analyst|markets?)\b",
    re.I,
)


def _amount(match: re.Match, p: str) -> tuple[float | None, str | None, bool]:
    """(value, currency, had_suffix) for one named amount in a match.

    Millions ("$40M", "$5M ARR") are company figures, never a salary.
    """
    raw = match.group(f"{p}num")
    if raw is None:
        return None, None, False
    try:
        value = float(raw.replace(",", ""))
    except ValueError:
        return None, None, False
    suffix = (match.group(f"{p}suf") or "").lower()
    if suffix == "m":
        return None, None, False
    if _RETIREMENT.match(match.string, match.start(f"{p}num")):
        return None, None, False  # "401k" is a retirement plan, not $401,000
    if suffix == "k":
        value *= 1_000
    cur = (match.group(f"{p}cur") or "").strip()
    currency = _SYMBOLS.get(cur) or (cur.upper() if cur.upper() in _CODES else None)
    return value, currency, bool(suffix)


def _window(text: str, start: int, end: int, span: int = 90) -> str:
    return text[max(0, start - span): min(len(text), end + span)]


def quote_around(text: str, start: int, end: int, limit: int = MAX_QUOTE) -> str:
    """The sentence holding text[start:end], trimmed to `limit`. Always a slice of `text`."""
    left = max(0, start - 120)
    for mark in (". ", "\n", "• ", "; "):
        i = text.rfind(mark, left, start)
        if i != -1:
            left = max(left, i + len(mark))
    right = min(len(text), end + 120)
    for mark in (". ", "\n", " •", "; "):
        i = text.find(mark, end, right)
        if i != -1:
            right = min(right, i + 1)
    if right - left > limit:
        left = max(left, end - limit) if end - left > limit else left
        right = min(right, left + limit)
    return text[left:right].strip()


def _period(match: re.Match) -> str | None:
    word = (match.groupdict().get("period") or "").lower()
    return _PERIOD_WORDS.get(word)


def _base_finding(text: str, match: re.Match, lo: float, hi: float, currency: str | None,
                  period: str | None, *, origin: str, url: str | None,
                  known_pay: bool = False) -> dict | None:
    explicit = period is not None or known_pay
    if period is None:
        if lo < 1_000:
            return None  # "$85" with no period could be anything
        period = "year"
    factor = PERIOD_FACTORS[period]
    annual_lo, annual_hi = lo * factor, hi * factor
    if annual_lo < MIN_ANNUAL or annual_hi > MAX_ANNUAL:
        return None
    if not known_pay:
        # Right next to the amount, "budget" or "revenue" wins over any "salary"
        # elsewhere in the sentence; further out, a pay word outweighs it.
        if _NOT_PAY.search(_window(text, match.start(), match.end(), 25)):
            return None
        window = _window(text, match.start(), match.end())
        has_pay_word = bool(_PAY_WORDS.search(window))
        if not explicit and not has_pay_word:
            return None
        if _NOT_PAY.search(window) and not has_pay_word:
            return None
    return {
        "component": "base",
        "status": "posted",
        "min": lo, "max": hi,
        "currency": currency or "USD",
        "period": period,
        "annual_min": round(annual_lo), "annual_max": round(annual_hi),
        "evidence": {"quote": quote_around(text, match.start(), match.end()), "origin": origin, "url": url},
    }


def _priced(currency: str | None, suffix: bool, period: str | None, known_pay: bool) -> bool:
    """Whether an amount is written like money. A known pay field may say
    "85–95 an hour"; free text must say "$85" or "85K"."""
    if known_pay:
        return bool(currency or suffix or period)
    return bool(currency or suffix)


def scan_base(text: str, *, origin: str, url: str | None = None,
              known_pay: bool = False) -> list[dict]:
    """Base-pay ranges and amounts stated in `text`.

    `known_pay`: the whole text is a pay field (Google Jobs' `salary`), so no
    "salary" word is needed next to the number.
    """
    if not text:
        return []
    found: list[dict] = []
    taken: list[tuple[int, int]] = []
    for match in _RANGE_RE.finditer(text):
        lo, cur_a, suf_a = _amount(match, "a")
        hi, cur_b, suf_b = _amount(match, "b")
        if lo is None or hi is None:
            continue
        currency = cur_a or cur_b
        if not _priced(currency, suf_a or suf_b, _period(match), known_pay):
            continue
        # "150-200K": the K on the second amount applies to the first.
        if suf_b and not suf_a and lo < 1_000:
            lo *= 1_000
        if lo > hi:
            lo, hi = hi, lo
        if lo <= 0 or hi / lo > 5:
            continue
        finding = _base_finding(text, match, lo, hi, currency, _period(match), origin=origin,
                                url=url, known_pay=known_pay)
        if finding:
            found.append(finding)
            taken.append((match.start(), match.end()))
    for match in _SINGLE_RE.finditer(text):
        if any(a <= match.start() < b for a, b in taken):
            continue
        value, currency, suffix = _amount(match, "a")
        if value is None or not _priced(currency, suffix, _period(match), known_pay):
            continue
        finding = _base_finding(text, match, value, value, currency, _period(match), origin=origin,
                                url=url, known_pay=known_pay)
        if finding:
            found.append(finding)
    return found


def _pct_tied(text: str, word: re.Pattern, *, max_pct: float,
              gap: int = 30) -> list[tuple[re.Match, float, float, str]]:
    """Percentages in the same clause as `word`: (match, lo, hi, the text
    between them). "Bonus target of 40%" and "a 30% target bonus" are tied;
    "a 401(k) match of 4% and an annual bonus" is not."""
    out = []
    for match in _PCT_RE.finditer(text):
        lo = float(match.group("lo") or match.group("one"))
        hi = float(match.group("hi") or lo)
        if lo > hi:
            lo, hi = hi, lo
        if hi > max_pct or lo <= 0:
            continue
        start = max(0, match.start() - gap)
        for found in word.finditer(text, start, min(len(text), match.end() + gap)):
            between = (text[found.end():match.start()] if found.end() <= match.start()
                       else text[match.end():found.start()])
            if found.start() < match.end() and found.end() > match.start():
                continue  # overlapping: not a word next to the number
            if len(between) <= gap and not _CLAUSE_BREAK.search(between):
                out.append((match, lo, hi, between))
                break
    return out


def scan_bonus(text: str, *, origin: str, url: str | None = None) -> list[dict]:
    if not text:
        return []
    found = []
    for match, lo, hi, _between in _pct_tied(text, _BONUS_WORD, max_pct=100):
        around = _window(text, match.start(), match.end(), 45)
        if _NOT_BONUS.search(around):
            continue
        found.append({
            "component": "bonus", "status": "posted",
            "kind": "signing" if _SIGNING.search(around) else "annual",
            "pct_min": lo, "pct_max": hi,
            "evidence": {"quote": quote_around(text, match.start(), match.end()), "origin": origin, "url": url},
        })
    if not found:
        for match in _BONUS_MENTION.finditer(text):
            around = _window(text, match.start(), match.end(), 30)
            if _NOT_BONUS.search(around):
                continue
            found.append({
                "component": "bonus", "status": "mentioned",
                "kind": "signing" if _SIGNING.search(around) else "annual",
                "evidence": {"quote": quote_around(text, match.start(), match.end()), "origin": origin, "url": url},
            })
            break
    return found


def _comp_equity(text: str, start: int, end: int) -> bool:
    """Whether the "equity" at text[start:end] is pay, not "private equity-backed"."""
    if _NOT_EQUITY_BEFORE.search(text[max(0, start - 25): start]):
        return False
    return not _NOT_EQUITY_AFTER.search(text[end: end + 30])


def scan_equity(text: str, *, origin: str, url: str | None = None) -> list[dict]:
    if not text:
        return []
    found = []
    for match, lo, hi, _between in _pct_tied(text, _EQUITY_WORD, max_pct=20):
        around = text[max(0, match.start() - 35): match.end() + 35]
        offset = max(0, match.start() - 35)
        word = _EQUITY_WORD.search(around)
        if word is None or not _comp_equity(text, offset + word.start(), offset + word.end()):
            continue
        found.append({
            "component": "equity", "status": "posted", "kind": "percent",
            "pct_min": lo, "pct_max": hi,
            "evidence": {"quote": quote_around(text, match.start(), match.end()), "origin": origin, "url": url},
        })
    if not found:
        for match in _EQUITY_MENTION.finditer(text):
            span = re.search(r"equity|stock|RSU|restricted|profits?|ownership", match.group(0), re.I)
            s = match.start() + (span.start() if span else 0)
            e = match.start() + (span.end() if span else len(match.group(0)))
            if not _comp_equity(text, s, e):
                continue
            found.append({
                "component": "equity", "status": "mentioned", "kind": "unspecified",
                "evidence": {"quote": quote_around(text, match.start(), match.end()), "origin": origin, "url": url},
            })
            break
    return found


def scan_text(text: str, *, origin: str, url: str | None = None) -> list[dict]:
    """Every base, bonus and equity finding in `text`."""
    return [
        *scan_base(text, origin=origin, url=url),
        *scan_bonus(text, origin=origin, url=url),
        *scan_equity(text, origin=origin, url=url),
    ]


# ── structured sources ───────────────────────────────────────────────────────

def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").strip())
        except ValueError:
            return None
    return None


def period_of(unit: Any) -> str | None:
    """'year' from "YEAR", "1 YEAR", "per-year-salary", "yearly", "HOUR"..."""
    text = str(unit or "").lower()
    for word, period in (("hour", "hour"), ("day", "day"), ("week", "week"),
                         ("month", "month"), ("year", "year"), ("annual", "year")):
        if word in text:
            return period
    return None


def structured_base(lo: Any, hi: Any, currency: Any, unit: Any, *, quote: str,
                    origin: str, url: str | None) -> dict | None:
    lo_v, hi_v = _num(lo), _num(hi)
    if lo_v is None and hi_v is None:
        return None
    lo_v = lo_v if lo_v is not None else hi_v
    hi_v = hi_v if hi_v is not None else lo_v
    if lo_v <= 0 or hi_v <= 0:
        return None
    if lo_v > hi_v:
        lo_v, hi_v = hi_v, lo_v
    period = period_of(unit) or ("year" if lo_v >= 1_000 else None)
    if period is None:
        return None
    factor = PERIOD_FACTORS[period]
    if lo_v * factor < MIN_ANNUAL or hi_v * factor > MAX_ANNUAL:
        return None
    code = str(currency or "USD").strip().upper()[:3] or "USD"
    return {
        "component": "base", "status": "posted",
        "min": lo_v, "max": hi_v, "currency": code, "period": period,
        "annual_min": round(lo_v * factor), "annual_max": round(hi_v * factor),
        "evidence": {"quote": quote[:MAX_QUOTE], "origin": origin, "url": url},
    }


def _fmt(value: Any) -> str:
    number = _num(value)
    if number is None:
        return str(value)
    return f"{number:,.0f}" if number == int(number) else f"{number:,.2f}"


def from_jsonld(base_salary: Any, *, url: str | None) -> list[dict]:
    """schema.org `baseSalary`: MonetaryAmount with a QuantitativeValue."""
    if not isinstance(base_salary, dict):
        return []
    value = base_salary.get("value")
    currency = base_salary.get("currency")
    if isinstance(value, dict):
        lo = value.get("minValue", value.get("value"))
        hi = value.get("maxValue", value.get("value"))
        unit = value.get("unitText")
    else:
        lo = hi = value
        unit = base_salary.get("unitText")
    quote = f"baseSalary: {_fmt(lo)}–{_fmt(hi)} {currency or ''} per {unit or 'unspecified'}".replace("  ", " ")
    finding = structured_base(lo, hi, currency, unit, quote=quote, origin="jsonld", url=url)
    return [finding] if finding else []


def from_lever(posting: dict, *, url: str | None) -> list[dict]:
    found = []
    salary = posting.get("salaryRange") if isinstance(posting.get("salaryRange"), dict) else None
    described = str(posting.get("salaryDescriptionPlain") or "").strip()
    if salary:
        quote = (
            f"salaryRange: {_fmt(salary.get('min'))}–{_fmt(salary.get('max'))} "
            f"{salary.get('currency') or ''} {salary.get('interval') or ''}"
        ).strip()
        finding = structured_base(
            salary.get("min"), salary.get("max"), salary.get("currency"), salary.get("interval"),
            quote=quote, origin="ats_api", url=url,
        )
        if finding:
            found.append(finding)
    if described:
        found.extend(f for f in scan_text(described, origin="ats_api", url=url)
                     if f["component"] != "base" or not found)
    return found


def from_greenhouse(pay_ranges: Any, *, url: str | None) -> list[dict]:
    found = []
    for item in pay_ranges if isinstance(pay_ranges, list) else []:
        if not isinstance(item, dict):
            continue
        lo, hi = _num(item.get("min_cents")), _num(item.get("max_cents"))
        if lo is None and hi is None:
            continue
        title = str(item.get("title") or "")
        unit = "hour" if re.search(r"hour", title, re.I) else "year"
        quote = (
            f"pay range{(' (' + title + ')') if title else ''}: "
            f"{_fmt((lo or hi) / 100)}–{_fmt((hi or lo) / 100)} {item.get('currency_type') or 'USD'}"
        )
        finding = structured_base(
            (lo or hi) / 100, (hi or lo) / 100, item.get("currency_type"), unit,
            quote=quote, origin="ats_api", url=url,
        )
        if finding:
            found.append(finding)
            break
    return found


def from_ashby(compensation: Any, *, url: str | None) -> list[dict]:
    """Ashby's `compensation` (with `includeCompensation=true`): salary, bonus and equity."""
    if not isinstance(compensation, dict):
        return []
    tiers = compensation.get("compensationTiers") or []
    components = []
    for tier in tiers if isinstance(tiers, list) else []:
        if isinstance(tier, dict) and isinstance(tier.get("components"), list):
            components = tier["components"]
            break
    if not components and isinstance(compensation.get("summaryComponents"), list):
        components = compensation["summaryComponents"]
    found = []
    base = None
    for comp in components:
        if not isinstance(comp, dict):
            continue
        kind = str(comp.get("compensationType") or "")
        lo, hi = comp.get("minValue"), comp.get("maxValue")
        currency, interval = comp.get("currencyCode"), comp.get("interval")
        quote = f"{kind}: {_fmt(lo)}–{_fmt(hi)} {currency or ''} {interval or ''}".strip()
        if kind == "Salary" and base is None:
            base = structured_base(lo, hi, currency, interval, quote=quote, origin="ats_api", url=url)
            if base:
                found.append(base)
        elif kind == "EquityPercentage":
            lo_v, hi_v = _num(lo), _num(hi)
            if lo_v is not None or hi_v is not None:
                lo_v = lo_v if lo_v is not None else hi_v
                hi_v = hi_v if hi_v is not None else lo_v
                found.append({
                    "component": "equity", "status": "posted", "kind": "percent",
                    "pct_min": lo_v, "pct_max": hi_v,
                    "evidence": {"quote": quote, "origin": "ats_api", "url": url},
                })
        elif kind == "EquityCashValue":
            lo_v, hi_v = _num(lo), _num(hi)
            if lo_v is not None or hi_v is not None:
                found.append({
                    "component": "equity", "status": "posted", "kind": "cash_value",
                    "min": lo_v if lo_v is not None else hi_v, "max": hi_v if hi_v is not None else lo_v,
                    "currency": str(currency or "USD").upper()[:3],
                    "evidence": {"quote": quote, "origin": "ats_api", "url": url},
                })
        elif kind == "Bonus":
            lo_v, hi_v = _num(lo), _num(hi)
            if lo_v is not None or hi_v is not None:
                lo_v = lo_v if lo_v is not None else hi_v
                hi_v = hi_v if hi_v is not None else lo_v
                item = {
                    "component": "bonus", "status": "posted", "kind": "annual",
                    "evidence": {"quote": quote, "origin": "ats_api", "url": url},
                }
                if currency:
                    item |= {"min": lo_v, "max": hi_v, "currency": str(currency).upper()[:3]}
                else:
                    item |= {"pct_min": lo_v, "pct_max": hi_v}
                found.append(item)
    summary = str(compensation.get("compensationTierSummary") or "").strip()
    if summary and not found:
        found.extend(scan_text(summary, origin="ats_api", url=url))
    return found


# ── combining ────────────────────────────────────────────────────────────────

_ORIGIN_RANK = {"ats_api": 0, "jsonld": 1, "google_jobs": 2, "page": 3}


def _better(a: dict | None, b: dict) -> bool:
    """Whether finding `b` should replace `a` for the same component."""
    if a is None:
        return True
    if (a.get("status") == "posted") != (b.get("status") == "posted"):
        return b.get("status") == "posted"
    rank_a = _ORIGIN_RANK.get((a.get("evidence") or {}).get("origin"), 9)
    rank_b = _ORIGIN_RANK.get((b.get("evidence") or {}).get("origin"), 9)
    if rank_a != rank_b:
        return rank_b < rank_a
    # Same source: an annual bonus over a signing bonus, a range over a point.
    if b.get("kind") == "annual" and a.get("kind") == "signing":
        return True
    return (b.get("max", 0) or 0) > (b.get("min", 0) or 0) and (a.get("max") == a.get("min"))


def combine(findings: list[dict], existing: dict | None = None) -> dict:
    """The best finding per component: posted over mentioned, then ATS, JSON-LD,
    Google Jobs, page text."""
    comp = {k: v for k, v in (existing or {}).items() if k in ("base", "bonus", "equity") and v}
    for finding in findings:
        key = finding.get("component")
        if key not in ("base", "bonus", "equity"):
            continue
        if _better(comp.get(key), finding):
            comp[key] = {k: v for k, v in finding.items() if k != "component"}
    return comp


def comp_status(comp: dict) -> str:
    base = comp.get("base") or {}
    if base.get("status") == "posted":
        return "posted"
    if any(comp.get(k) for k in ("base", "bonus", "equity")):
        return "mentioned"
    return "not_disclosed"


def annual_range(comp: dict) -> tuple[float | None, float | None, str | None]:
    base = comp.get("base") or {}
    if base.get("status") != "posted":
        return None, None, None
    return base.get("annual_min"), base.get("annual_max"), base.get("currency")


def bonus_pct(comp: dict) -> float | None:
    """The annual bonus as a percent of base, when either is stated that way."""
    bonus = comp.get("bonus") or {}
    if bonus.get("status") != "posted" or bonus.get("kind") == "signing":
        return None
    if bonus.get("pct_min") is not None:
        return (float(bonus["pct_min"]) + float(bonus.get("pct_max") or bonus["pct_min"])) / 2
    lo, hi, currency = annual_range(comp)
    if bonus.get("min") is not None and lo and currency == bonus.get("currency"):
        mid_bonus = (float(bonus["min"]) + float(bonus.get("max") or bonus["min"])) / 2
        return round(100 * mid_bonus / ((lo + hi) / 2), 1)
    return None


def equity_pct(comp: dict) -> float | None:
    equity = comp.get("equity") or {}
    if equity.get("status") != "posted" or equity.get("pct_min") is None:
        return None
    return (float(equity["pct_min"]) + float(equity.get("pct_max") or equity["pct_min"])) / 2


# ── checking a model's claim (used by the model phases) ──────────────────────

def _norm(text: str) -> str:
    return " ".join(str(text or "").split()).casefold()


def verify_quote(quote: str, source: str) -> bool:
    q = _norm(quote)
    return len(q) >= 8 and q in _norm(source)


def amounts_in(text: str) -> list[float]:
    out = []
    for match in re.finditer(rf"(?P<num>{_NUM})\s?(?P<suf>{_SUF})?", text or ""):
        try:
            value = float(match.group("num").replace(",", ""))
        except ValueError:
            continue
        suffix = (match.group("suf") or "").lower()
        out.append(value * (1_000 if suffix == "k" else 1_000_000 if suffix == "m" else 1))
    return out


def numbers_supported(values: list[float | None], quote: str) -> bool:
    """Every given number is written in `quote` ("180000" ~ "$180,000" ~ "180K")."""
    stated = amounts_in(quote)
    for value in values:
        if value is None:
            continue
        if not any(abs(s - float(value)) <= max(0.5, abs(float(value)) * 0.005) for s in stated):
            return False
    return True
