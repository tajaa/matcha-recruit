"""Request/response shapes for the AI-connector routes
(`app/matcha/routes/matcha_work/connectors.py`)."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


ConnectorKind = Literal["claude", "chatgpt", "claude_code", "other"]


class ConnectorGrant(BaseModel):
    client_id: str
    client_name: str
    kind: ConnectorKind
    connected_at: Optional[str] = None
    last_used_at: Optional[str] = None


class ConnectorsResponse(BaseModel):
    mcp_url: str
    grants: list[ConnectorGrant]
    connected: dict[str, bool]
    claude_code_command: str


class ConsentDescription(BaseModel):
    client_name: str
    client_kind: ConnectorKind
    redirect_host: str
    scopes: list[str]


class ConsentDecision(BaseModel):
    request: str = Field(..., min_length=1, max_length=8000)
    approve: bool


class ConsentResult(BaseModel):
    redirect_url: str


class ResearchLaunchRequest(BaseModel):
    client: Literal["claude", "chatgpt", "claude_code"]


class ResearchLaunchResponse(BaseModel):
    client: str
    url: Optional[str] = None
    prompt: str
    command: Optional[str] = None
