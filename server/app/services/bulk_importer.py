import csv
import json
import io
from typing import Any, Optional
from uuid import UUID

from pydantic import ValidationError

from ..models.bulk_import import (
    BulkImportResult,
    BulkImportError,
    CompanyBulkRow,
    PositionBulkRow,
)


class BulkImporter:
    """Service for parsing and importing bulk data from CSV/JSON files."""

    def parse_csv(self, file_bytes: bytes) -> list[dict[str, Any]]:
        """Parse CSV file into list of dicts."""
        content = file_bytes.decode("utf-8-sig")  # Handle BOM
        reader = csv.DictReader(io.StringIO(content))
        return list(reader)

    def parse_json(self, file_bytes: bytes) -> list[dict[str, Any]]:
        """Parse JSON file into list of dicts."""
        content = file_bytes.decode("utf-8")
        data = json.loads(content)
        if not isinstance(data, list):
            raise ValueError("JSON must be an array of objects")
        return data

    def parse_file(self, file_bytes: bytes, filename: str) -> list[dict[str, Any]]:
        """Parse file based on extension."""
        if filename.endswith(".csv"):
            return self.parse_csv(file_bytes)
        elif filename.endswith(".json"):
            return self.parse_json(file_bytes)
        else:
            raise ValueError(f"Unsupported file type: {filename}. Use .csv or .json")

    def _parse_comma_separated(self, value: Optional[str]) -> Optional[list[str]]:
        """Parse comma-separated string into list."""
        if not value or value.strip() == "":
            return None
        return [item.strip() for item in value.split(",") if item.strip()]

    def _parse_bool(self, value: Any) -> bool:
        """Parse various boolean representations."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "yes", "1", "y")
        return bool(value)

    def _parse_int(self, value: Any) -> Optional[int]:
        """Parse integer from various inputs."""
        if value is None or value == "":
            return None
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None

    async def import_companies(
        self, rows: list[dict[str, Any]], conn
    ) -> BulkImportResult:
        """Import companies from parsed data."""
        success_count = 0
        errors = []
        imported_ids = []

        for i, row in enumerate(rows, start=1):
            try:
                # Validate with Pydantic
                company = CompanyBulkRow(**row)

                # Check if company already exists
                existing = await conn.fetchrow(
                    "SELECT id FROM companies WHERE name = $1",
                    company.name,
                )
                if existing:
                    errors.append(
                        BulkImportError(
                            row=i,
                            error=f"Company '{company.name}' already exists",
                            data=row,
                        )
                    )
                    continue

                # Insert company
                result = await conn.fetchrow(
                    """
                    INSERT INTO companies (name, industry, size)
                    VALUES ($1, $2, $3)
                    RETURNING id
                    """,
                    company.name,
                    company.industry,
                    company.size,
                )
                imported_ids.append(str(result["id"]))
                success_count += 1

            except ValidationError as e:
                errors.append(
                    BulkImportError(
                        row=i,
                        error=f"Validation error: {e.errors()[0]['msg']}",
                        data=row,
                    )
                )
            except Exception as e:
                errors.append(
                    BulkImportError(
                        row=i,
                        error=str(e),
                        data=row,
                    )
                )

        return BulkImportResult(
            success_count=success_count,
            error_count=len(errors),
            errors=errors,
            imported_ids=imported_ids,
        )

    async def import_positions(
        self, rows: list[dict[str, Any]], conn
    ) -> BulkImportResult:
        """Import positions from parsed data."""
        success_count = 0
        errors = []
        imported_ids = []

        # Cache company lookups
        company_cache: dict[str, UUID] = {}

        for i, row in enumerate(rows, start=1):
            try:
                # Validate with Pydantic
                position = PositionBulkRow(**row)

                # Look up or cache company
                company_name = position.company_name
                if company_name not in company_cache:
                    company_row = await conn.fetchrow(
                        "SELECT id FROM companies WHERE name = $1",
                        company_name,
                    )
                    if not company_row:
                        errors.append(
                            BulkImportError(
                                row=i,
                                error=f"Company '{company_name}' not found. Create the company first.",
                                data=row,
                            )
                        )
                        continue
                    company_cache[company_name] = company_row["id"]

                company_id = company_cache[company_name]

                # Parse comma-separated fields
                required_skills = self._parse_comma_separated(position.required_skills)
                preferred_skills = self._parse_comma_separated(position.preferred_skills)
                requirements = self._parse_comma_separated(position.requirements)
                responsibilities = self._parse_comma_separated(position.responsibilities)
                benefits = self._parse_comma_separated(position.benefits)

                # Insert position
                result = await conn.fetchrow(
                    """
                    INSERT INTO positions (
                        company_id, title, salary_min, salary_max, salary_currency,
                        location, employment_type, required_skills, preferred_skills,
                        experience_level, requirements, responsibilities, benefits,
                        department, reporting_to, remote_policy, visa_sponsorship
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
                    RETURNING id
                    """,
                    company_id,
                    position.title,
                    self._parse_int(position.salary_min),
                    self._parse_int(position.salary_max),
                    position.salary_currency or "USD",
                    position.location,
                    position.employment_type,
                    json.dumps(required_skills) if required_skills else None,
                    json.dumps(preferred_skills) if preferred_skills else None,
                    position.experience_level,
                    json.dumps(requirements) if requirements else None,
                    json.dumps(responsibilities) if responsibilities else None,
                    json.dumps(benefits) if benefits else None,
                    position.department,
                    position.reporting_to,
                    position.remote_policy,
                    self._parse_bool(position.visa_sponsorship),
                )
                imported_ids.append(str(result["id"]))
                success_count += 1

            except ValidationError as e:
                errors.append(
                    BulkImportError(
                        row=i,
                        error=f"Validation error: {e.errors()[0]['msg']}",
                        data=row,
                    )
                )
            except Exception as e:
                errors.append(
                    BulkImportError(
                        row=i,
                        error=str(e),
                        data=row,
                    )
                )

        return BulkImportResult(
            success_count=success_count,
            error_count=len(errors),
            errors=errors,
            imported_ids=imported_ids,
        )


# CSV templates
COMPANY_CSV_TEMPLATE = """name,industry,size
Acme Corp,Technology,startup
BigCo Inc,Finance,enterprise
MidSize Co,Healthcare,mid
"""

POSITION_CSV_TEMPLATE = """company_name,title,salary_min,salary_max,salary_currency,location,employment_type,required_skills,preferred_skills,experience_level,department,remote_policy,visa_sponsorship
Acme Corp,Software Engineer,80000,120000,USD,"San Francisco, CA",full-time,"Python,JavaScript,SQL","React,AWS",mid,Engineering,hybrid,false
Acme Corp,Product Manager,100000,150000,USD,"San Francisco, CA",full-time,"Product Management,Agile","Technical Background",senior,Product,remote,true
"""
