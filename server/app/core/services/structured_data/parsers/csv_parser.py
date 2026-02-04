"""CSV parser for structured data sources like UC Berkeley Labor Center."""

import csv
import io
from typing import Optional

import httpx

from .base import BaseParser, ParsedRequirement


class CSVParser(BaseParser):
    """Parser for CSV-formatted compliance data."""

    async def fetch_and_parse(
        self, source_url: str, parser_config: dict
    ) -> list[ParsedRequirement]:
        """
        Fetch and parse a CSV file containing compliance data.

        Args:
            source_url: URL to the CSV file
            parser_config: Configuration dict with keys:
                - encoding: File encoding (default: utf-8)
                - skip_rows: Number of header rows to skip
                - columns: Mapping of semantic names to column names/indices

        Returns:
            List of parsed requirements
        """
        # Fetch the CSV content
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(source_url, follow_redirects=True)
                response.raise_for_status()
                content = response.text
        except httpx.HTTPError as e:
            print(f"[CSV Parser] HTTP error fetching {source_url}: {e}")
            return []
        except Exception as e:
            print(f"[CSV Parser] Error fetching {source_url}: {e}")
            return []

        return self._parse_csv_content(content, source_url, parser_config)

    def _parse_csv_content(
        self, content: str, source_url: str, parser_config: dict
    ) -> list[ParsedRequirement]:
        """Parse CSV content into requirements."""
        encoding = parser_config.get("encoding", "utf-8")
        skip_rows = parser_config.get("skip_rows", 0)
        column_map = parser_config.get("columns", {})

        requirements = []

        try:
            # Handle BOM if present
            if content.startswith("\ufeff"):
                content = content[1:]

            reader = csv.DictReader(io.StringIO(content))

            for i, row in enumerate(reader):
                if i < skip_rows:
                    continue

                req = self._parse_row(row, source_url, column_map, parser_config)
                if req:
                    requirements.append(req)

        except Exception as e:
            print(f"[CSV Parser] Error parsing CSV: {e}")

        print(f"[CSV Parser] Parsed {len(requirements)} requirements from {source_url}")
        return requirements

    def _parse_row(
        self,
        row: dict,
        source_url: str,
        column_map: dict,
        parser_config: dict,
    ) -> Optional[ParsedRequirement]:
        """Parse a single CSV row into a ParsedRequirement."""
        try:
            # Get column values using the mapping
            jurisdiction_name = self._get_column_value(row, column_map.get("jurisdiction"))
            state_raw = self._get_column_value(row, column_map.get("state"))
            current_wage = self._get_column_value(row, column_map.get("current_wage"))
            effective_date_str = self._get_column_value(row, column_map.get("effective_date"))
            next_wage = self._get_column_value(row, column_map.get("next_wage"))
            next_date_str = self._get_column_value(row, column_map.get("next_date"))
            notes = self._get_column_value(row, column_map.get("notes"))

            if not jurisdiction_name or not state_raw:
                return None

            # Normalize state
            state = self.normalize_state(state_raw)
            if not state:
                print(f"[CSV Parser] Unknown state: {state_raw}")
                return None

            # Determine jurisdiction level
            level = self.determine_jurisdiction_level(jurisdiction_name, "city_county")

            # Create jurisdiction key
            jurisdiction_key = self.normalize_jurisdiction_key(jurisdiction_name, state, level)

            # Parse dates
            effective_date = self.parse_date(effective_date_str)
            next_scheduled_date = self.parse_date(next_date_str)

            # Extract numeric value
            numeric_value = self.extract_numeric_value(current_wage)

            # Get rate type from config or default
            rate_type = parser_config.get("rate_type", "general")

            return ParsedRequirement(
                jurisdiction_key=jurisdiction_key,
                jurisdiction_name=jurisdiction_name,
                jurisdiction_level=level,
                state=state,
                category="minimum_wage",
                rate_type=rate_type,
                current_value=current_wage or "",
                numeric_value=numeric_value,
                effective_date=effective_date,
                next_scheduled_date=next_scheduled_date,
                next_scheduled_value=next_wage,
                source_url=source_url,
                notes=notes,
                raw_data=dict(row),
            )

        except Exception as e:
            print(f"[CSV Parser] Error parsing row: {e}")
            return None

    @staticmethod
    def _get_column_value(row: dict, column_name: Optional[str]) -> Optional[str]:
        """Get value from row by column name, handling missing columns gracefully."""
        if not column_name:
            return None

        # Try exact match first
        if column_name in row:
            value = row[column_name]
            return value.strip() if isinstance(value, str) else value

        # Try case-insensitive match
        lower_name = column_name.lower()
        for key, value in row.items():
            if key.lower() == lower_name:
                return value.strip() if isinstance(value, str) else value

        return None
