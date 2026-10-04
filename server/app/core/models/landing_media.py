"""Scheduling commercial settings and bounded browser-upload requests."""
from typing import Literal
from pydantic import BaseModel, Field, model_validator

CommercialSlot = Literal['desktop_video', 'mobile_video', 'desktop_poster', 'mobile_poster', 'captions']


class SchedulingCommercial(BaseModel):
    enabled: bool = False
    # True: visitors can start the film with sound and get a Sound off/on button.
    # False: the film only ever plays silently (no sound controls are shown).
    sound_enabled: bool = True
    desktop_video_url: str | None = Field(default=None, max_length=2048)
    mobile_video_url: str | None = Field(default=None, max_length=2048)
    desktop_poster_url: str | None = Field(default=None, max_length=2048)
    mobile_poster_url: str | None = Field(default=None, max_length=2048)
    captions_url: str | None = Field(default=None, max_length=2048)

    @model_validator(mode='after')
    def require_desktop(self):
        if self.enabled and not self.desktop_video_url:
            raise ValueError('Upload a desktop video before enabling the commercial.')
        return self


class CommercialUploadRequest(BaseModel):
    slot: CommercialSlot
    filename: str = Field(min_length=1, max_length=200)
    content_type: str = Field(min_length=1, max_length=100)
    size: int = Field(gt=0, le=150 * 1024 * 1024)


class CommercialUploadComplete(CommercialUploadRequest):
    asset_url: str = Field(min_length=1, max_length=2048)
