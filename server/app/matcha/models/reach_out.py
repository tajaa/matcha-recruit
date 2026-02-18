"""Pydantic models for candidate reach-out email drafting and sending."""
from pydantic import BaseModel


class ReachOutDraftResponse(BaseModel):
    to_email: str
    to_name: str
    subject: str
    body: str


class ReachOutSendRequest(BaseModel):
    to_email: str
    subject: str
    body: str  # admin may have edited the AI draft


class ReachOutSendResponse(BaseModel):
    success: bool
    message: str
