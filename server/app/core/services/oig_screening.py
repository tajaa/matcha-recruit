"""OIG LEIE Exclusion Screening Service.

Downloads and caches the OIG List of Excluded Individuals/Entities (LEIE)
and screens individuals against it. Federal requirement for all healthcare
employers — must screen at hire and monthly thereafter.

LEIE CSV columns:
  LASTNAME, FIRSTNAME, MIDNAME, BUSNAME, GENERAL, SPECIALTY,
  UPIN, NPI, DOB, ADDRESS, CITY, STATE, ZIP,
  EXCLTYPE, EXCLDATE, REINDATE, WAIVERDATE, WVRSTATE
"""

import csv
import io
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

LEIE_URL = "https://oig.hhs.gov/exclusions/downloadables/UPDATED.csv"
CACHE_TTL_SECONDS = 86400 * 7  # 7 days — LEIE updates monthly


@dataclass
class LEIEEntry:
    last_name: str
    first_name: str
    mid_name: str
    bus_name: str
    npi: str
    state: str
    excl_type: str
    excl_date: str
    rein_date: str
    general: str
    specialty: str


@dataclass
class ScreeningResult:
    matched: bool
    confidence: str  # "definitive" | "high" | "possible" | "none"
    matches: list[dict]  # list of matched entries with details

    @property
    def status(self) -> str:
        if not self.matched:
            return "cleared"
        if self.confidence == "definitive":
            return "excluded"
        return "review_needed"


class OIGScreeningService:
    """Downloads LEIE data, caches it, and screens individuals."""

    def __init__(self):
        self._entries: list[LEIEEntry] = []
        self._by_last_name: dict[str, list[int]] = {}
        self._by_npi: dict[str, int] = {}
        self._loaded_at: float = 0
        self._loading: bool = False

    @property
    def is_loaded(self) -> bool:
        return len(self._entries) > 0 and (time.time() - self._loaded_at) < CACHE_TTL_SECONDS

    async def ensure_loaded(self):
        """Download and parse LEIE if not cached or stale."""
        if self.is_loaded or self._loading:
            return
        self._loading = True
        try:
            logger.info("Downloading OIG LEIE data from %s", LEIE_URL)
            async with httpx.AsyncClient() as client:
                resp = await client.get(LEIE_URL, timeout=60.0, follow_redirects=True)
                resp.raise_for_status()

            text = resp.text
            reader = csv.DictReader(io.StringIO(text))

            entries: list[LEIEEntry] = []
            by_last: dict[str, list[int]] = {}
            by_npi: dict[str, int] = {}

            for row in reader:
                # Skip reinstated individuals (they're no longer excluded)
                rein = (row.get("REINDATE") or "").strip()
                if rein and rein != "00000000":
                    continue

                entry = LEIEEntry(
                    last_name=_norm(row.get("LASTNAME", "")),
                    first_name=_norm(row.get("FIRSTNAME", "")),
                    mid_name=_norm(row.get("MIDNAME", "")),
                    bus_name=_norm(row.get("BUSNAME", "")),
                    npi=(row.get("NPI") or "").strip(),
                    state=(row.get("STATE") or "").strip().upper(),
                    excl_type=(row.get("EXCLTYPE") or "").strip(),
                    excl_date=(row.get("EXCLDATE") or "").strip(),
                    rein_date=rein,
                    general=(row.get("GENERAL") or "").strip(),
                    specialty=(row.get("SPECIALTY") or "").strip(),
                )

                idx = len(entries)
                entries.append(entry)

                # Index by normalized last name
                if entry.last_name:
                    by_last.setdefault(entry.last_name, []).append(idx)

                # Index by NPI (skip placeholder zeros)
                if entry.npi and entry.npi != "0000000000":
                    by_npi[entry.npi] = idx

            self._entries = entries
            self._by_last_name = by_last
            self._by_npi = by_npi
            self._loaded_at = time.time()
            logger.info("Loaded %d active LEIE exclusions (%d with NPI)", len(entries), len(by_npi))

        except Exception:
            logger.exception("Failed to download/parse OIG LEIE data")
        finally:
            self._loading = False

    async def screen_individual(
        self,
        first_name: str,
        last_name: str,
        npi: Optional[str] = None,
        state: Optional[str] = None,
    ) -> ScreeningResult:
        """Screen an individual against the LEIE.

        Returns ScreeningResult with match confidence:
        - definitive: NPI match (unique identifier)
        - high: exact first + last name match
        - possible: last name match with partial first name
        - none: no match
        """
        await self.ensure_loaded()

        if not self._entries:
            logger.warning("LEIE data not available — cannot screen")
            return ScreeningResult(matched=False, confidence="none", matches=[])

        matches: list[dict] = []
        best_confidence = "none"

        # Phase 1: NPI lookup (definitive)
        if npi and npi in self._by_npi:
            entry = self._entries[self._by_npi[npi]]
            matches.append(_entry_to_match(entry, "definitive", "NPI match"))
            best_confidence = "definitive"

        # Phase 2: Name-based lookup
        norm_last = _norm(last_name)
        norm_first = _norm(first_name)

        if norm_last in self._by_last_name:
            for idx in self._by_last_name[norm_last]:
                entry = self._entries[idx]

                # Skip if already matched by NPI
                if npi and entry.npi == npi:
                    continue

                # Optional state filter
                if state and entry.state and entry.state != state.upper():
                    continue

                if entry.first_name == norm_first:
                    # Exact first + last name
                    confidence = "high"
                    reason = "Exact name match"
                    if _confidence_rank(confidence) > _confidence_rank(best_confidence):
                        best_confidence = confidence
                    matches.append(_entry_to_match(entry, confidence, reason))

                elif norm_first and entry.first_name and entry.first_name.startswith(norm_first[:3]):
                    # Partial first name match (first 3 chars)
                    confidence = "possible"
                    reason = f"Partial name match ({entry.first_name} {entry.last_name})"
                    if _confidence_rank(confidence) > _confidence_rank(best_confidence):
                        best_confidence = confidence
                    matches.append(_entry_to_match(entry, confidence, reason))

        return ScreeningResult(
            matched=len(matches) > 0,
            confidence=best_confidence,
            matches=matches[:10],  # cap at 10 matches
        )


def _norm(s: str) -> str:
    """Normalize a name for comparison."""
    return s.strip().upper().replace(".", "").replace(",", "").replace("-", " ")


def _confidence_rank(c: str) -> int:
    return {"none": 0, "possible": 1, "high": 2, "definitive": 3}.get(c, 0)


def _entry_to_match(entry: LEIEEntry, confidence: str, reason: str) -> dict:
    excl_date = None
    if entry.excl_date and entry.excl_date != "00000000":
        try:
            excl_date = datetime.strptime(entry.excl_date, "%Y%m%d").strftime("%Y-%m-%d")
        except ValueError:
            excl_date = entry.excl_date

    return {
        "confidence": confidence,
        "reason": reason,
        "last_name": entry.last_name,
        "first_name": entry.first_name,
        "mid_name": entry.mid_name,
        "bus_name": entry.bus_name,
        "npi": entry.npi if entry.npi != "0000000000" else None,
        "state": entry.state,
        "exclusion_type": entry.excl_type,
        "exclusion_date": excl_date,
        "general": entry.general,
        "specialty": entry.specialty,
    }


# ── Singleton ────────────────────────────────────────────────────────────────

_service: Optional[OIGScreeningService] = None


def get_oig_screening_service() -> OIGScreeningService:
    global _service
    if _service is None:
        _service = OIGScreeningService()
    return _service
