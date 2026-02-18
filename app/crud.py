from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app import models, schemas


def upsert_channel(db: Session, payload: schemas.ChannelUpsert) -> models.Channel:
    channel = db.get(models.Channel, payload.channel_id)
    if channel is None:
        channel = models.Channel(
            channel_id=payload.channel_id,
            title=payload.title,
        )
        db.add(channel)
    else:
        channel.title = payload.title

    db.commit()
    db.refresh(channel)
    return channel


def upsert_video(db: Session, payload: schemas.VideoUpsert) -> models.Video:
    channel = db.get(models.Channel, payload.channel_id)
    if channel is None:
        channel = models.Channel(channel_id=payload.channel_id, title=f"Channel {payload.channel_id}")
        db.add(channel)
        db.flush()

    video = db.get(models.Video, payload.video_id)
    if video is None:
        video = models.Video(
            video_id=payload.video_id,
            channel_id=payload.channel_id,
            title=payload.title,
            description=payload.description or "",
            published_at=payload.published_at,
            duration_seconds=payload.duration_seconds,
            tags=payload.tags,
        )
        db.add(video)
    else:
        video.channel_id = payload.channel_id
        video.title = payload.title
        video.description = payload.description or ""
        video.published_at = payload.published_at
        video.duration_seconds = payload.duration_seconds
        video.tags = payload.tags

    db.commit()
    db.refresh(video)
    return video


def list_videos(db: Session, limit: int = 200) -> list[models.Video]:
    stmt = select(models.Video).order_by(desc(models.Video.created_at)).limit(limit)
    return list(db.scalars(stmt).all())


def get_all_videos(db: Session) -> list[models.Video]:
    stmt = select(models.Video).order_by(desc(models.Video.created_at))
    return list(db.scalars(stmt).all())


def video_exists(db: Session, video_id: str) -> bool:
    return db.get(models.Video, video_id) is not None


def create_interaction(db: Session, payload: schemas.InteractionCreate) -> models.Interaction:
    interaction = models.Interaction(
        user_id=payload.user_id,
        video_id=payload.video_id,
        event_type=payload.event_type,
        watch_seconds=payload.watch_seconds,
        metadata_json=payload.metadata,
    )
    db.add(interaction)
    db.commit()
    db.refresh(interaction)
    return interaction


def get_user_interactions(db: Session, user_id: str, limit: int = 2000) -> list[models.Interaction]:
    stmt = (
        select(models.Interaction)
        .where(models.Interaction.user_id == user_id)
        .order_by(desc(models.Interaction.event_time))
        .limit(limit)
    )
    return list(db.scalars(stmt).all())
