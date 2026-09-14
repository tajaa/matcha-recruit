"""Validated request/response contracts for Matcha S&C account setup."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


CompanySize = Literal["1-10", "11-50", "51-100", "101-250", "251-500", "501+"]


class ScOnboardingModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class ScCompanySetup(ScOnboardingModel):
    # `industry` is deliberately absent: signup already captures it from the
    # shared INDUSTRY_OPTIONS vocabulary (values align with
    # compliance_registry industry_tag sub-keys).  A free-text re-ask here
    # would overwrite that controlled value and silently break industry-tag
    # resolution downstream.
    company_size: CompanySize
    naics_code: str = Field(pattern=r"^\d{2,6}$")


class ScLocationImport(ScOnboardingModel):
    name: str = Field(min_length=1, max_length=255)
    address: str = Field(min_length=1, max_length=500)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(pattern=r"^[A-Za-z]{2}$")
    zipcode: str = Field(pattern=r"^\d{5}(?:-\d{4})?$")


class ScEmployeeImport(ScOnboardingModel):
    email: EmailStr
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    work_state: str = Field(pattern=r"^[A-Za-z]{2}$")
    job_title: str = Field(min_length=1, max_length=150)
    department: str = Field(min_length=1, max_length=100)


class ScCertificateSetup(ScOnboardingModel):
    name: str = Field(min_length=1, max_length=200)
    is_required: bool = True
    schedule_blocking: bool = True

    @model_validator(mode="after")
    def blocking_must_be_required(self):
        if self.schedule_blocking and not self.is_required:
            raise ValueError("A schedule-blocking certificate must be mandatory")
        return self


class ScJobSetup(ScOnboardingModel):
    name: str = Field(min_length=1, max_length=150)
    credential_grace_days: int = Field(default=7, ge=0, le=365)
    # The wizard requires at least one certificate per job; keeping the server
    # contract identical stops the two validators from drifting apart.
    certificates: list[ScCertificateSetup] = Field(min_length=1, max_length=50)


class ScOnboardingComplete(ScOnboardingModel):
    company: ScCompanySetup
    locations: list[ScLocationImport] = Field(default_factory=list, max_length=500)
    employees: list[ScEmployeeImport] = Field(default_factory=list, max_length=500)
    jobs: list[ScJobSetup] = Field(min_length=1, max_length=100)


class ScOnboardingStatus(ScOnboardingModel):
    company_name: str
    completed: bool
    completed_at: str | None = None
    # The expected CSV headers, so the wizard renders the server's own columns
    # instead of a second copy that can drift out of step with the parser.
    csv_columns: dict[str, list[str]] = Field(default_factory=dict)


class ScOnboardingCsvParse(ScOnboardingModel):
    rows: list[ScLocationImport] | list[ScEmployeeImport]


class ScOnboardingResult(ScOnboardingModel):
    already_completed: bool
    completed_at: str
