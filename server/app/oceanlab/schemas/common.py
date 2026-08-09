from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


def no_duplicates(v: list[UUID]) -> list[UUID]:
    if len(set(v)) != len(v):
        raise ValueError("list must not contain duplicates")
    return v
