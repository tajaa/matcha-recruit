from datetime import datetime
from typing import Optional, Any
from uuid import UUID

from pydantic import BaseModel


class Candidate(BaseModel):
    id: UUID
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    resume_text: Optional[str] = None
    resume_file_path: Optional[str] = None
    skills: Optional[list[str]] = None
    experience_years: Optional[int] = None
    education: Optional[list[dict[str, Any]]] = None
    parsed_data: Optional[dict[str, Any]] = None
    created_at: datetime


class CandidateResponse(BaseModel):
    id: UUID
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    skills: Optional[list[str]] = None
    experience_years: Optional[int] = None
    education: Optional[list[dict[str, Any]]] = None
    created_at: datetime


class CandidateDetail(BaseModel):
    id: UUID
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    resume_text: Optional[str] = None
    skills: Optional[list[str]] = None
    experience_years: Optional[int] = None
    education: Optional[list[dict[str, Any]]] = None
    parsed_data: Optional[dict[str, Any]] = None
    created_at: datetime
