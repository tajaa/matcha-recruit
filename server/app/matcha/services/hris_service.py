"""HRIS integration service for pulling employee data from ADP/Gusto-style systems."""

import base64
import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

PROVIDER_HRIS = "hris"
GUSTO_BASE_URL = "https://api.gusto.com"


class HRISProvisioningError(Exception):
    """Error during HRIS sync operations."""
    def __init__(self, code: str, message: str, *, needs_action: bool = False):
        super().__init__(message)
        self.code = code
        self.needs_action = needs_action


class HRISService:
    """Client for ADP-style HRIS API. Fetches and normalizes employee data."""

    def __init__(self, *, timeout_seconds: float = 30.0):
        self.timeout_seconds = timeout_seconds

    async def test_connection(self, config: dict, secrets: dict) -> tuple[bool, Optional[str]]:
        """Test connectivity to the HRIS endpoint."""
        mode = config.get("mode", "mock")
        if mode == "mock":
            return True, None

        base_url = config.get("base_url", "").rstrip("/")
        if not base_url:
            return False, "No base_url configured"

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.get(f"{base_url}/health")
                if resp.status_code == 200:
                    return True, None
                return False, f"Health check returned {resp.status_code}"
        except Exception as e:
            return False, f"Connection failed: {str(e)}"

    async def authenticate(self, config: dict, secrets: dict) -> str:
        """Authenticate with the HRIS and return a bearer token."""
        mode = config.get("mode", "mock")
        if mode == "mock":
            return "mock-token"

        base_url = config.get("base_url", "").rstrip("/")
        client_id = secrets.get("client_id", "")
        client_secret = secrets.get("client_secret", "")

        if not all([base_url, client_id, client_secret]):
            raise HRISProvisioningError("auth_config_missing", "Missing base_url, client_id, or client_secret", needs_action=True)

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(
                    f"{base_url}/auth/token",
                    json={"client_id": client_id, "client_secret": client_secret},
                )
                if resp.status_code != 200:
                    raise HRISProvisioningError("auth_failed", f"Authentication failed: {resp.status_code} {resp.text}")
                data = resp.json()
                return data["access_token"]
        except HRISProvisioningError:
            raise
        except Exception as e:
            raise HRISProvisioningError("auth_error", f"Authentication error: {str(e)}")

    async def fetch_workers(self, config: dict, secrets: dict) -> list[dict]:
        """Fetch all workers from the HRIS API with pagination."""
        token = await self.authenticate(config, secrets)
        base_url = config.get("base_url", "").rstrip("/")

        workers = []
        skip = 0
        top = 100

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                while True:
                    resp = await client.get(
                        f"{base_url}/hr/v2/workers",
                        params={"$top": top, "$skip": skip},
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if resp.status_code != 200:
                        raise HRISProvisioningError("fetch_failed", f"Failed to fetch workers: {resp.status_code}")

                    data = resp.json()
                    batch = data.get("workers", [])
                    if not batch:
                        break
                    workers.extend(batch)

                    # If we got fewer than requested, we're done
                    if len(batch) < top:
                        break
                    skip += top
        except HRISProvisioningError:
            raise
        except Exception as e:
            raise HRISProvisioningError("fetch_error", f"Error fetching workers: {str(e)}")

        logger.info("[HRIS] Fetched %d workers from %s", len(workers), base_url)
        return workers

    @staticmethod
    def normalize_worker(adp_worker: dict) -> dict:
        """Convert an ADP worker record to flat Matcha employee format.

        Returns dict with keys matching the employees table columns plus
        a nested 'credentials' dict for employee_credentials.
        """
        person = adp_worker.get("person", {})
        legal_name = person.get("legalName", {})
        comm = person.get("communication", {})

        # Extract emails
        emails = comm.get("emails", [])
        work_email = emails[0]["emailUri"] if emails else None
        personal_email = emails[1]["emailUri"] if len(emails) > 1 else None

        # Extract phone
        mobiles = comm.get("mobiles", [])
        phone = mobiles[0]["dialNumber"] if mobiles else None

        # Extract work assignment
        assignments = adp_worker.get("workAssignments", [])
        assignment = assignments[0] if assignments else {}

        # Extract department
        org_units = assignment.get("homeOrganizationalUnits", [])
        department = None
        for unit in org_units:
            if unit.get("typeCode", {}).get("codeValue") == "Department":
                department = unit.get("nameCode", {}).get("codeValue")
                break

        # Extract location
        location = assignment.get("homeWorkLocation", {}).get("address", {})
        work_state = location.get("countrySubdivisionLevel1", {}).get("codeValue")
        work_city = location.get("cityName")

        # Extract worker type
        worker_type_code = assignment.get("workerTypeCode", {}).get("codeValue", "")
        employment_type = "full_time"
        if "part" in worker_type_code.lower():
            employment_type = "part_time"
        elif "contract" in worker_type_code.lower():
            employment_type = "contract"

        # Extract custom fields (credentials)
        custom = adp_worker.get("customFieldGroup", {})
        string_fields = {f["nameCode"]["codeValue"]: f["stringValue"] for f in custom.get("stringFields", [])}
        date_fields = {f["nameCode"]["codeValue"]: f["dateValue"] for f in custom.get("dateFields", [])}

        credentials = {}
        if string_fields.get("license_type"):
            credentials["license_type"] = string_fields["license_type"]
        if string_fields.get("license_number"):
            credentials["license_number"] = string_fields["license_number"]
        if string_fields.get("npi_number"):
            credentials["npi_number"] = string_fields["npi_number"]
        if string_fields.get("dea_number"):
            credentials["dea_number"] = string_fields["dea_number"]
        if string_fields.get("board_certification"):
            credentials["board_certification"] = string_fields["board_certification"]
        if string_fields.get("malpractice_carrier"):
            credentials["malpractice_carrier"] = string_fields["malpractice_carrier"]
        if string_fields.get("malpractice_policy_number"):
            credentials["malpractice_policy_number"] = string_fields["malpractice_policy_number"]
        if string_fields.get("clinical_specialty"):
            credentials["clinical_specialty"] = string_fields["clinical_specialty"]
        if date_fields.get("license_expiration"):
            credentials["license_expiration"] = date_fields["license_expiration"]
        if date_fields.get("dea_expiration"):
            credentials["dea_expiration"] = date_fields["dea_expiration"]
        if date_fields.get("board_cert_expiration"):
            credentials["board_cert_expiration"] = date_fields["board_cert_expiration"]
        if date_fields.get("malpractice_expiration"):
            credentials["malpractice_expiration"] = date_fields["malpractice_expiration"]

        # Worker status
        status_code = adp_worker.get("workerStatus", {}).get("statusCode", {}).get("codeValue", "Active")

        return {
            "hris_id": adp_worker.get("associateOID"),
            "first_name": legal_name.get("givenName"),
            "last_name": legal_name.get("familyName1"),
            "email": work_email,
            "personal_email": personal_email,
            "phone": phone,
            "job_title": assignment.get("positionTitle"),
            "department": department,
            "employment_type": employment_type,
            "work_state": work_state,
            "work_city": work_city,
            "start_date": assignment.get("hireDate"),
            "is_manager": assignment.get("managementPosition", False),
            "status": "active" if status_code == "Active" else "inactive",
            "credentials": credentials if credentials else None,
        }


class GustoHRISService:
    """Client for the Gusto API. Fetches and normalizes employee data."""

    def __init__(self, *, timeout_seconds: float = 30.0):
        self.timeout_seconds = timeout_seconds

    async def test_connection(self, config: dict, secrets: dict) -> tuple[bool, Optional[str]]:
        mode = config.get("mode", "mock")
        if mode == "mock":
            return True, None
        try:
            token = await self.authenticate(config, secrets)
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.get(
                    f"{GUSTO_BASE_URL}/v1/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code == 200:
                    return True, None
                return False, f"Gusto /v1/me returned {resp.status_code}"
        except HRISProvisioningError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Connection failed: {str(e)}"

    async def authenticate(self, config: dict, secrets: dict) -> str:
        mode = config.get("mode", "mock")
        if mode == "mock":
            return "mock-gusto-token"

        # OAuth flow: use access_token from secrets if available
        if secrets.get("access_token"):
            return secrets["access_token"]

        # Legacy: client_credentials flow with client_id + client_secret
        # client_id is stored in config (not a secret); support legacy secrets location too
        client_id = config.get("client_id", "") or secrets.get("client_id", "")
        client_secret = secrets.get("client_secret", "")

        if not all([client_id, client_secret]):
            raise HRISProvisioningError("auth_config_missing", "Missing Gusto client_id or client_secret", needs_action=True)

        credentials = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(
                    f"{GUSTO_BASE_URL}/oauth/token",
                    headers={"Authorization": f"Basic {credentials}"},
                    data={"grant_type": "client_credentials"},
                )
                if resp.status_code != 200:
                    logger.error(f"[Gusto Auth] {resp.status_code}: {resp.text}")
                    raise HRISProvisioningError("auth_failed", f"Gusto auth failed: {resp.status_code} {resp.text[:300]}")
                return resp.json()["access_token"]
        except HRISProvisioningError:
            raise
        except Exception as e:
            raise HRISProvisioningError("auth_error", f"Gusto auth error: {str(e)}")

    async def resolve_company_uuid(self, config: dict, secrets: dict) -> tuple[Optional[str], Optional[str]]:
        """Call /v1/me and extract the company UUID. Returns (uuid, error)."""
        try:
            token = await self.authenticate(config, secrets)
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.get(
                    f"{GUSTO_BASE_URL}/v1/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
                if resp.status_code != 200:
                    return None, f"/v1/me returned {resp.status_code}"
                data = resp.json()
                companies = (
                    data.get("roles", {})
                        .get("payroll_admin", {})
                        .get("companies", [])
                )
                if len(companies) == 1:
                    return companies[0].get("uuid"), None
                if len(companies) > 1:
                    return None, "Multiple Gusto companies found — enter company UUID manually"
                return None, "No company found in Gusto account"
        except HRISProvisioningError as e:
            return None, str(e)
        except Exception as e:
            return None, f"Company auto-discovery failed: {str(e)}"

    async def fetch_workers(self, config: dict, secrets: dict) -> list[dict]:
        gusto_company_id = config.get("gusto_company_id", "")

        if not gusto_company_id and config.get("mode") != "mock":
            raise HRISProvisioningError("config_missing", "gusto_company_id not configured", needs_action=True)

        # Mock mode: return a small representative set (no auth needed)
        if config.get("mode") == "mock":
            return _GUSTO_MOCK_EMPLOYEES

        token = await self.authenticate(config, secrets)

        workers: list[dict] = []
        url: Optional[str] = (
            f"{GUSTO_BASE_URL}/v1/companies/{gusto_company_id}/employees"
            "?include=all&per_page=200"
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                while url:
                    resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
                    if resp.status_code != 200:
                        raise HRISProvisioningError("fetch_failed", f"Gusto fetch failed: {resp.status_code}")
                    batch = resp.json()
                    if not isinstance(batch, list):
                        raise HRISProvisioningError("fetch_failed", f"Gusto returned unexpected response shape: {type(batch).__name__}")
                    workers.extend(batch)
                    # Follow Link: <url>; rel="next" pagination
                    link_header = resp.headers.get("Link", "")
                    next_match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
                    url = next_match.group(1) if next_match else None
        except HRISProvisioningError:
            raise
        except Exception as e:
            raise HRISProvisioningError("fetch_error", f"Gusto fetch error: {str(e)}")

        logger.info("[Gusto] Fetched %d employees for company %s", len(workers), gusto_company_id)
        return workers

    @staticmethod
    def normalize_worker(gusto_employee: dict) -> dict:
        """Convert a Gusto employee record to flat Matcha employee format."""
        jobs = gusto_employee.get("jobs") or []
        primary_job = next((j for j in jobs if j.get("primary")), jobs[0] if jobs else {})

        home_addr = gusto_employee.get("home_address") or {}
        work_addr = gusto_employee.get("work_address") or home_addr

        # Prefer work_email; fall back to personal email field
        email = gusto_employee.get("work_email") or gusto_employee.get("email")

        # Employment type from payment_unit
        payment_unit = (primary_job.get("current_compensation") or {}).get("payment_unit", "")
        employment_type = "part_time" if payment_unit == "Hour" else "full_time"

        # Department: Gusto returns it as a string or nested object
        dept = gusto_employee.get("department")
        if isinstance(dept, dict):
            dept = dept.get("title") or dept.get("name")

        terminated = gusto_employee.get("terminated", False)

        return {
            "hris_id": gusto_employee.get("uuid"),
            "first_name": gusto_employee.get("first_name"),
            "last_name": gusto_employee.get("last_name"),
            "email": email,
            "personal_email": gusto_employee.get("email") if gusto_employee.get("work_email") else None,
            "phone": gusto_employee.get("phone"),
            "job_title": primary_job.get("title"),
            "department": dept,
            "employment_type": employment_type,
            "work_state": work_addr.get("state"),
            "work_city": work_addr.get("city"),
            "start_date": primary_job.get("hire_date"),
            "is_manager": False,
            "status": "inactive" if terminated else "active",
            "credentials": None,
        }


# ---------------------------------------------------------------------------
# Small mock dataset for Gusto mode (dev / demo)
# ---------------------------------------------------------------------------

_GUSTO_MOCK_EMPLOYEES: list[dict] = [
    {
        "uuid": "gusto-mock-001",
        "first_name": "Alex",
        "last_name": "Rivera",
        "work_email": "alex.rivera@example.com",
        "email": "alex.rivera@example.com",
        "phone": "555-0101",
        "department": "Engineering",
        "terminated": False,
        "jobs": [{"title": "Software Engineer", "hire_date": "2023-03-01", "primary": True,
                  "current_compensation": {"payment_unit": "Year"}}],
        "home_address": {"state": "CA", "city": "San Francisco"},
    },
    {
        "uuid": "gusto-mock-002",
        "first_name": "Morgan",
        "last_name": "Chen",
        "work_email": "morgan.chen@example.com",
        "email": "morgan.chen@example.com",
        "phone": "555-0102",
        "department": "Operations",
        "terminated": False,
        "jobs": [{"title": "Operations Manager", "hire_date": "2022-06-15", "primary": True,
                  "current_compensation": {"payment_unit": "Year"}}],
        "home_address": {"state": "CA", "city": "Oakland"},
    },
    {
        "uuid": "gusto-mock-003",
        "first_name": "Jordan",
        "last_name": "Patel",
        "work_email": "jordan.patel@example.com",
        "email": "jordan.patel@example.com",
        "phone": "555-0103",
        "department": "HR",
        "terminated": False,
        "jobs": [{"title": "HR Coordinator", "hire_date": "2023-09-01", "primary": True,
                  "current_compensation": {"payment_unit": "Year"}}],
        "home_address": {"state": "NY", "city": "New York"},
    },
]


def get_hris_service(provider: str) -> "HRISService | GustoHRISService":
    """Return the appropriate HRIS service for the given provider/mode."""
    if provider == "gusto":
        return GustoHRISService()
    return HRISService()
