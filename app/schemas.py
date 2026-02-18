from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

EventType = Literal["watch", "click", "like", "skip"]


class ChannelUpsert(BaseModel):
    channel_id: str = Field(..., min_length=1, max_length=128)
    title: str = Field(..., min_length=1, max_length=512)


class ChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    channel_id: str
    title: str
    created_at: datetime


class VideoUpsert(BaseModel):
    video_id: str = Field(..., min_length=1, max_length=128)
    channel_id: str = Field(..., min_length=1, max_length=128)
    title: str = Field(..., min_length=1, max_length=1024)
    description: str = ""
    published_at: datetime | None = None
    duration_seconds: int | None = Field(default=None, ge=0)
    tags: list[str] | None = None


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    video_id: str
    channel_id: str
    title: str
    description: str
    published_at: datetime | None
    duration_seconds: int | None
    tags: list[str] | None
    created_at: datetime


class InteractionCreate(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    video_id: str = Field(..., min_length=1, max_length=128)
    event_type: EventType
    watch_seconds: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] | None = None


class InteractionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    interaction_id: UUID
    user_id: str
    video_id: str
    event_time: datetime
    event_type: EventType
    watch_seconds: int | None
    metadata: dict[str, Any] | None = Field(default=None, validation_alias="metadata_json")


class RecommendationItem(BaseModel):
    video_id: str
    score: float
    reasons: list[str]


class RecommendationResponse(BaseModel):
    user_id: str
    k: int
    items: list[RecommendationItem]


class GoogleTakeoutImportRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=128)
    rows: list[dict[str, Any]]
    source_file: str | None = None


class GoogleTakeoutImportResponse(BaseModel):
    source_file: str | None
    total_rows: int
    imported_rows: int
    skipped_rows: int
    watch_events: int
    click_events: int
    like_events: int
    skip_events: int
    processed_files: list[str] = Field(default_factory=list)
    skipped_files: list[str] = Field(default_factory=list)
    parse_errors: list[str] = Field(default_factory=list)
