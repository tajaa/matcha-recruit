"""HTML table parser for structured data sources like DOL, NCSL, EPI."""

from typing import Optional

import httpx

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

from ..http_utils import fetch_with_retry
from .base import BaseParser, ParsedRequirement


class HTMLTableParser(BaseParser):
    """Parser for HTML table-formatted compliance data."""

    async def fetch_and_parse(
        self, source_url: str, parser_config: dict
    ) -> list[ParsedRequirement]:
        """
        Fetch and parse an HTML page containing compliance data tables.

        Args:
            source_url: URL to the HTML page
            parser_config: Configuration dict with keys:
                - table_selector: CSS selector for the target table
                - rate_type: Type of wage rate (general, tipped, etc.)
                - columns: Mapping of semantic names to column indices

        Returns:
            List of parsed requirements
        """
        if BeautifulSoup is None:
            print("[HTML Parser] beautifulsoup4 not installed, skipping HTML parse")
            return []

        # Fetch the HTML content with retry logic
        try:
            response = await fetch_with_retry(
                source_url,
                timeout=60.0,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; MatchaComplianceBot/1.0)"
                },
            )

            # Validate content-type
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" not in content_type and "application/xhtml" not in content_type:
                # Allow if URL ends in .html or .htm regardless of content-type
                if not any(source_url.lower().endswith(ext) for ext in [".html", ".htm"]):
                    print(f"[HTML Parser] Unexpected content-type '{content_type}' for {source_url}")
                    return []

            content = response.text
        except httpx.HTTPError as e:
            print(f"[HTML Parser] HTTP error fetching {source_url}: {e}")
            return []
        except Exception as e:
            print(f"[HTML Parser] Error fetching {source_url}: {e}")
            return []

        return self._parse_html_content(content, source_url, parser_config)

    def _parse_html_content(
        self, content: str, source_url: str, parser_config: dict
    ) -> list[ParsedRequirement]:
        """Parse HTML content into requirements."""
        table_selector = parser_config.get("table_selector", "table")
        column_map = parser_config.get("columns", {})
        rate_type = parser_config.get("rate_type", "general")

        requirements = []

        try:
            soup = BeautifulSoup(content, "html.parser")

            # Find the target table
            tables = soup.select(table_selector)
            if not tables:
                # Fallback to any table
                tables = soup.find_all("table")

            if not tables:
                print(f"[HTML Parser] No tables found in {source_url}")
                return []

            # Parse the first matching table (or all if needed)
            for table in tables[:1]:  # Usually just need the first table
                reqs = self._parse_table(table, source_url, column_map, rate_type)
                requirements.extend(reqs)

        except Exception as e:
            print(f"[HTML Parser] Error parsing HTML: {e}")

        print(f"[HTML Parser] Parsed {len(requirements)} requirements from {source_url}")
        return requirements

    def _parse_table(
        self,
        table,
        source_url: str,
        column_map: dict,
        rate_type: str,
    ) -> list[ParsedRequirement]:
        """Parse a single HTML table into requirements."""
        requirements = []

        # Find all rows
        rows = table.find_all("tr")
        if not rows:
            return []

        # Skip header row(s)
        data_rows = rows[1:]  # Assume first row is header

        for row in data_rows:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            req = self._parse_row(cells, source_url, column_map, rate_type)
            if req:
                requirements.append(req)

        return requirements

    def _parse_row(
        self,
        cells: list,
        source_url: str,
        column_map: dict,
        rate_type: str,
    ) -> Optional[ParsedRequirement]:
        """Parse a single table row into a ParsedRequirement."""
        try:
            # Get column indices
            state_col = column_map.get("state", 0)
            wage_col = column_map.get("current_wage")
            cash_wage_col = column_map.get("cash_wage")
            total_col = column_map.get("total")
            effective_col = column_map.get("effective_date")
            next_wage_col = column_map.get("next_wage")
            next_date_col = column_map.get("next_date")
            future_col = column_map.get("future_changes")

            # Get cell values
            state_raw = self._get_cell_value(cells, state_col)
            if not state_raw:
                return None

            # Normalize state
            state = self.normalize_state(state_raw)
            if not state:
                # Skip rows that aren't state data (e.g., headers, notes)
                return None

            # Get wage value based on source type
            if wage_col is not None:
                current_wage = self._get_cell_value(cells, wage_col)
            elif cash_wage_col is not None and rate_type == "tipped":
                # For tipped wages, use cash wage as the current value
                current_wage = self._get_cell_value(cells, cash_wage_col)
            elif total_col is not None:
                current_wage = self._get_cell_value(cells, total_col)
            else:
                # Try column 1 as default
                current_wage = self._get_cell_value(cells, 1)

            if not current_wage:
                return None

            # Parse dates
            effective_date_str = self._get_cell_value(cells, effective_col) if effective_col is not None else None
            next_date_str = self._get_cell_value(cells, next_date_col) if next_date_col is not None else None
            next_wage_str = self._get_cell_value(cells, next_wage_col) if next_wage_col is not None else None

            # Handle future_changes column (combines next wage and date)
            future_changes = self._get_cell_value(cells, future_col) if future_col is not None else None
            if future_changes and not next_wage_str:
                # Try to parse combined future changes text
                next_wage_str, next_date_str = self._parse_future_changes(future_changes)

            effective_date = self.parse_date(effective_date_str) if effective_date_str else None
            next_scheduled_date = self.parse_date(next_date_str) if next_date_str else None

            # Get full state name for display
            from ..sources import CODE_TO_STATE
            jurisdiction_name = CODE_TO_STATE.get(state, state_raw)

            # Create jurisdiction key
            jurisdiction_key = self.normalize_jurisdiction_key(jurisdiction_name, state, "state")

            # Extract numeric value
            numeric_value = self.extract_numeric_value(current_wage)

            # Validate wage bounds
            if numeric_value is not None:
                is_valid, error_msg = self.validate_wage_bounds(numeric_value, "minimum_wage")
                if not is_valid:
                    print(f"[HTML Parser] Rejected {jurisdiction_name}: {error_msg}")
                    return None

            # Validate effective date
            if effective_date is not None:
                is_valid, error_msg = self.validate_effective_date(effective_date)
                if not is_valid:
                    print(f"[HTML Parser] Rejected {jurisdiction_name}: {error_msg}")
                    return None

            return ParsedRequirement(
                jurisdiction_key=jurisdiction_key,
                jurisdiction_name=jurisdiction_name,
                jurisdiction_level="state",
                state=state,
                category="minimum_wage",
                rate_type=rate_type,
                current_value=current_wage,
                numeric_value=numeric_value,
                effective_date=effective_date,
                next_scheduled_date=next_scheduled_date,
                next_scheduled_value=next_wage_str,
                source_url=source_url,
                notes=None,
                raw_data={"cells": [c.get_text(strip=True) for c in cells]},
            )

        except Exception as e:
            print(f"[HTML Parser] Error parsing row: {e}")
            return None

    @staticmethod
    def _get_cell_value(cells: list, index: Optional[int]) -> Optional[str]:
        """Get text value from a cell by index."""
        if index is None or index < 0 or index >= len(cells):
            return None

        cell = cells[index]
        text = cell.get_text(strip=True)
        return text if text else None

    @staticmethod
    def _parse_future_changes(text: str) -> tuple[Optional[str], Optional[str]]:
        """
        Parse a combined future changes text into wage and date.

        Examples:
            "$15.00 on Jan 1, 2025" -> ("$15.00", "Jan 1, 2025")
            "$16.50 (effective July 1, 2025)" -> ("$16.50", "July 1, 2025")
        """
        if not text or text.lower() in ("n/a", "none", "-"):
            return None, None

        import re

        # Try to find dollar amount
        wage_match = re.search(r"\$\d+(?:\.\d{2})?", text)
        wage = wage_match.group(0) if wage_match else None

        # Try to find date
        date_patterns = [
            r"(?:on|effective|starting)\s+(.+?)(?:\)|$)",
            r"(\w+ \d{1,2},? \d{4})",
            r"(\d{1,2}/\d{1,2}/\d{2,4})",
        ]
        date_str = None
        for pattern in date_patterns:
            date_match = re.search(pattern, text, re.IGNORECASE)
            if date_match:
                date_str = date_match.group(1).strip().rstrip(")")
                break

        return wage, date_str
