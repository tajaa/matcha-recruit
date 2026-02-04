"""Base parser class and shared utilities for structured data parsing."""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from ..sources import STATE_CODES


@dataclass
class ParsedRequirement:
    """Normalized requirement data extracted from a structured source."""

    jurisdiction_key: str  # e.g., "san_francisco_ca" or "california"
    jurisdiction_name: str  # e.g., "San Francisco" or "California"
    jurisdiction_level: str  # 'city', 'county', 'state'
    state: str  # 2-letter state code
    category: str  # e.g., "minimum_wage"
    rate_type: Optional[str]  # e.g., "general", "tipped", "large_employer"
    current_value: str  # e.g., "$16.50/hour"
    numeric_value: Optional[float]  # e.g., 16.50
    effective_date: Optional[date]
    next_scheduled_date: Optional[date]
    next_scheduled_value: Optional[str]
    source_url: str
    notes: Optional[str]
    raw_data: dict = field(default_factory=dict)


class BaseParser(ABC):
    """Abstract base class for structured data parsers."""

    @abstractmethod
    async def fetch_and_parse(
        self, source_url: str, parser_config: dict
    ) -> list[ParsedRequirement]:
        """
        Fetch data from source URL and parse into normalized requirements.

        Args:
            source_url: URL to fetch data from
            parser_config: Parser-specific configuration

        Returns:
            List of parsed requirements
        """
        pass

    @staticmethod
    def normalize_jurisdiction_key(
        name: str, state: str, level: str
    ) -> str:
        """
        Create a normalized jurisdiction key from name and state.

        Examples:
            ("San Francisco", "CA", "city") -> "san_francisco_ca"
            ("Los Angeles County", "CA", "county") -> "los_angeles_county_ca"
            ("California", "CA", "state") -> "california"
        """
        # Clean and lowercase the name
        clean_name = name.lower().strip()

        # Remove common suffixes for cleaner keys
        for suffix in [", city", ", county", " city", " county"]:
            if clean_name.endswith(suffix) and level != "county":
                clean_name = clean_name[: -len(suffix)]

        # Replace spaces and special chars with underscores
        clean_name = re.sub(r"[^a-z0-9]+", "_", clean_name)
        clean_name = clean_name.strip("_")

        # For state-level, just use the state name
        if level == "state":
            return clean_name

        # For city/county, append state code
        state_code = state.lower()
        return f"{clean_name}_{state_code}"

    @staticmethod
    def extract_numeric_value(value: str) -> Optional[float]:
        """
        Extract numeric wage value from a string.

        Examples:
            "$16.50" -> 16.50
            "$16.50/hour" -> 16.50
            "16.50" -> 16.50
            "$7.25 (federal)" -> 7.25
            "N/A" -> None
        """
        if not value:
            return None

        # Remove common non-numeric text
        clean = value.lower()
        if "n/a" in clean or "none" in clean or "no minimum" in clean:
            return None

        # Extract the first number pattern (dollars and cents)
        match = re.search(r"\$?(\d+(?:\.\d{2})?)", value)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass

        return None

    @staticmethod
    def parse_date(date_str: str) -> Optional[date]:
        """
        Parse a date string into a date object.

        Handles various formats:
            "January 1, 2024"
            "1/1/2024"
            "2024-01-01"
            "Jan 1, 2024"
        """
        if not date_str:
            return None

        date_str = date_str.strip()
        if not date_str or date_str.lower() in ("n/a", "none", "-", "tbd"):
            return None

        formats = [
            "%B %d, %Y",  # January 1, 2024
            "%b %d, %Y",  # Jan 1, 2024
            "%m/%d/%Y",  # 1/1/2024
            "%Y-%m-%d",  # 2024-01-01
            "%m/%d/%y",  # 1/1/24
            "%B %Y",  # January 2024 (assume 1st)
            "%b %Y",  # Jan 2024
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.date()
            except ValueError:
                continue

        # Try to find a year at minimum
        year_match = re.search(r"20\d{2}", date_str)
        if year_match:
            # Found a year, try to extract month
            month_names = [
                "january", "february", "march", "april", "may", "june",
                "july", "august", "september", "october", "november", "december",
                "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
            ]
            lower_str = date_str.lower()
            for i, month in enumerate(month_names[:12]):
                if month in lower_str:
                    return date(int(year_match.group()), i + 1, 1)
            for i, month in enumerate(month_names[12:]):
                if month in lower_str:
                    return date(int(year_match.group()), i + 1, 1)
            # Just use January 1 of that year
            return date(int(year_match.group()), 1, 1)

        return None

    @staticmethod
    def normalize_state(state_str: str) -> Optional[str]:
        """
        Normalize state to 2-letter code.

        Args:
            state_str: State name or code

        Returns:
            2-letter state code or None if not recognized
        """
        if not state_str:
            return None

        state_str = state_str.strip()

        # Already a 2-letter code
        if len(state_str) == 2 and state_str.upper() in STATE_CODES.values():
            return state_str.upper()

        # Look up full name
        lower = state_str.lower()
        if lower in STATE_CODES:
            return STATE_CODES[lower]

        return None

    @staticmethod
    def determine_jurisdiction_level(
        name: str, coverage_scope: str
    ) -> str:
        """
        Determine jurisdiction level from name and coverage scope.

        Args:
            name: Jurisdiction name
            coverage_scope: Source coverage scope ('state', 'city_county')

        Returns:
            Jurisdiction level: 'state', 'county', or 'city'
        """
        if coverage_scope == "state":
            return "state"

        lower_name = name.lower()
        if "county" in lower_name or "parish" in lower_name:
            return "county"

        return "city"
