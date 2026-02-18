from __future__ import annotations

import logging
import os
from pathlib import Path
import sys
import threading
import time
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy.orm import Session

from app import crud, schemas
from app.config import get_settings
from app.db import get_db, init_db
from app.redis_client import (
    clear_pattern,
    clear_user_recs_cache,
    get_cache_json,
    get_redis_client,
    set_cache_json,
)
from app.services.ingest import ingest_takeout_entries, ingest_takeout_json_bytes, ingest_takeout_zip_bytes
from app.services.recommend import generate_recommendations

logger = logging.getLogger(__name__)
settings = get_settings()
WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(
    title="YouTube Recommendation API",
    version="1.0.0",
    description="Content-based YouTube recommender with FastAPI, Postgres, and Redis.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if WEB_DIR.exists():
    app.mount("/ui", StaticFiles(directory=str(WEB_DIR), html=True), name="ui")


def get_redis() -> Redis:
    return get_redis_client()


DbDep = Annotated[Session, Depends(get_db)]
RedisDep = Annotated[Redis, Depends(get_redis)]


def ensure_takeout_import_enabled() -> None:
    if not settings.enable_takeout_import:
        raise HTTPException(status_code=404, detail="Google Takeout import is disabled by configuration.")


def _restart_current_process(delay_seconds: float) -> None:
    time.sleep(max(delay_seconds, 0.0))
    args = [sys.executable, *sys.argv]
    logger.warning("Restarting process via execv: %s", " ".join(args))
    os.execv(sys.executable, args)


def schedule_process_restart(delay_seconds: float) -> None:
    thread = threading.Thread(target=_restart_current_process, args=(delay_seconds,), daemon=True)
    thread.start()


@app.on_event("startup")
def on_startup() -> None:
    try:
        init_db()
        logger.info("Database initialized successfully.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Database initialization failed: %s", exc)

    try:
        get_redis_client().ping()
        logger.info("Redis connection established.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis connection failed: %s", exc)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "API is running", "docs": "/docs", "health": "/health"}


@app.get("/redis-ping")
def redis_ping(redis: RedisDep) -> dict[str, bool]:
    try:
        return {"redis": bool(redis.ping())}
    except RedisError as exc:
        raise HTTPException(status_code=503, detail=f"Redis unavailable: {exc}") from exc


@app.post("/admin/restart")
def restart_server(
    x_restart_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    if not settings.enable_self_restart:
        raise HTTPException(
            status_code=403,
            detail="Self restart is disabled. Set ENABLE_SELF_RESTART=true to enable this endpoint.",
        )

    provided_token = x_restart_token
    if not provided_token and authorization and authorization.lower().startswith("bearer "):
        provided_token = authorization[7:].strip()

    if settings.self_restart_token and provided_token != settings.self_restart_token:
        raise HTTPException(status_code=401, detail="Invalid restart token.")

    schedule_process_restart(settings.self_restart_delay_seconds)
    return {
        "status": "accepted",
        "message": "Restart scheduled.",
    }


@app.post("/channels/upsert", response_model=schemas.ChannelOut)
def upsert_channel(payload: schemas.ChannelUpsert, db: DbDep) -> schemas.ChannelOut:
    channel = crud.upsert_channel(db, payload)
    return schemas.ChannelOut.model_validate(channel)


@app.post("/videos/upsert", response_model=schemas.VideoOut)
def upsert_video(payload: schemas.VideoUpsert, db: DbDep, redis: RedisDep) -> schemas.VideoOut:
    video = crud.upsert_video(db, payload)
    try:
        clear_pattern(redis, "api:videos:*")
        clear_pattern(redis, "recs:*")
    except RedisError:
        logger.debug("Failed to invalidate Redis caches after video upsert.")
    return schemas.VideoOut.model_validate(video)


@app.get("/videos", response_model=list[schemas.VideoOut])
def list_videos(
    db: DbDep,
    redis: RedisDep,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[schemas.VideoOut]:
    cache_key = f"api:videos:{limit}"
    cached = get_cache_json(redis, cache_key)
    if cached is not None:
        return [schemas.VideoOut.model_validate(item) for item in cached]

    videos = crud.list_videos(db, limit=limit)
    result = [schemas.VideoOut.model_validate(v).model_dump(mode="json") for v in videos]
    set_cache_json(redis, cache_key, result, ttl_seconds=settings.api_cache_ttl_seconds)
    return [schemas.VideoOut.model_validate(item) for item in result]


@app.post("/interactions", response_model=schemas.InteractionOut)
def create_interaction(
    payload: schemas.InteractionCreate,
    db: DbDep,
    redis: RedisDep,
) -> schemas.InteractionOut:
    if not crud.video_exists(db, payload.video_id):
        raise HTTPException(status_code=404, detail="video_id does not exist")

    interaction = crud.create_interaction(db, payload)
    try:
        clear_user_recs_cache(redis, payload.user_id)
    except RedisError:
        logger.debug("Failed to clear recommendation cache for user_id=%s", payload.user_id)
    return schemas.InteractionOut.model_validate(interaction)


@app.get("/recommendations", response_model=schemas.RecommendationResponse)
def get_recommendations(
    db: DbDep,
    redis: RedisDep,
    user_id: str = Query(..., min_length=1),
    k: int = Query(default=20, ge=1, le=100),
) -> schemas.RecommendationResponse:
    cache_key = f"recs:{user_id}:{k}"
    cached = get_cache_json(redis, cache_key)
    if cached is not None:
        return schemas.RecommendationResponse.model_validate(cached)

    items = generate_recommendations(db=db, user_id=user_id, k=k)
    response_obj = schemas.RecommendationResponse(user_id=user_id, k=k, items=items)
    set_cache_json(
        redis,
        cache_key,
        response_obj.model_dump(mode="json"),
        ttl_seconds=settings.recommendation_cache_ttl_seconds,
    )
    return response_obj


@app.post("/cache/clear")
def clear_cache(user_id: str, redis: RedisDep) -> dict[str, str]:
    cleared = clear_user_recs_cache(redis, user_id)
    return {"status": "ok", "message": f"Cleared {cleared} recommendation cache keys for {user_id}"}


@app.post("/ingest/google-takeout", response_model=schemas.GoogleTakeoutImportResponse)
def ingest_google_takeout_json(
    payload: schemas.GoogleTakeoutImportRequest,
    db: DbDep,
    redis: RedisDep,
) -> schemas.GoogleTakeoutImportResponse:
    ensure_takeout_import_enabled()
    try:
        summary = ingest_takeout_entries(
            db=db,
            user_id=payload.user_id,
            rows=payload.rows,
            source_file=payload.source_file,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    clear_user_recs_cache(redis, payload.user_id)
    clear_pattern(redis, "api:videos:*")
    return schemas.GoogleTakeoutImportResponse(**summary.as_dict())


@app.post("/ingest/google-takeout/file", response_model=schemas.GoogleTakeoutImportResponse)
async def ingest_google_takeout_file(
    request: Request,
    db: DbDep,
    redis: RedisDep,
    user_id: str = Query(..., min_length=1),
    source_file: str | None = Query(default=None),
) -> schemas.GoogleTakeoutImportResponse:
    ensure_takeout_import_enabled()
    payload = await request.body()
    if not payload:
        raise HTTPException(status_code=400, detail="Request body is empty.")

    try:
        summary = ingest_takeout_json_bytes(
            db=db,
            user_id=user_id,
            raw_bytes=payload,
            source_file=source_file,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    clear_user_recs_cache(redis, user_id)
    clear_pattern(redis, "api:videos:*")
    return schemas.GoogleTakeoutImportResponse(**summary.as_dict())


@app.post("/ingest/google-takeout/zip", response_model=schemas.GoogleTakeoutImportResponse)
async def ingest_google_takeout_zip(
    request: Request,
    db: DbDep,
    redis: RedisDep,
    user_id: str = Query(..., min_length=1),
    source_file: str | None = Query(default=None),
) -> schemas.GoogleTakeoutImportResponse:
    ensure_takeout_import_enabled()
    payload = await request.body()
    if not payload:
        raise HTTPException(status_code=400, detail="Request body is empty.")

    try:
        summary = ingest_takeout_zip_bytes(
            db=db,
            user_id=user_id,
            raw_bytes=payload,
            source_file=source_file,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    clear_user_recs_cache(redis, user_id)
    clear_pattern(redis, "api:videos:*")
    return schemas.GoogleTakeoutImportResponse(**summary.as_dict())

