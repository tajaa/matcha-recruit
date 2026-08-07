from pydantic import BaseModel


class IsrcConfigRead(BaseModel):
    registrant_prefix: str
    year_digits: str
    next_designation: int


class IsrcConfigUpdate(BaseModel):
    registrant_prefix: str


class UpcAddIn(BaseModel):
    codes: list[str]


class UpcAddResult(BaseModel):
    added: int
    rejected: list[str]


class AssignIsrcResult(BaseModel):
    isrc: str


class AssignUpcResult(BaseModel):
    upc: str
