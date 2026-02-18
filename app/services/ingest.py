from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

from sqlalchemy.orm import Session

from app import models

TAKEOUT_SOURCE = "google_takeout"
UNKNOWN_CHANNEL_ID = "unknown_channel"
UNKNOWN_CHANNEL_TITLE = "Unknown Channel"
MAX_JSON_FILES_PER_ZIP = 400
MAX_JSON_FILE_BYTES = 50 * 1024 * 1024


@dataclass
class TakeoutImportSummary:
    source_file: str | None
    total_rows: int = 0
    imported_rows: int = 0
    skipped_rows: int = 0
    watch_events: int = 0
    click_events: int = 0
    like_events: int = 0
    skip_events: int = 0
    processed_files: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)

    def merge(self, other: "TakeoutImportSummary") -> None:
        self.total_rows += other.total_rows
        self.imported_rows += other.imported_rows
        self.skipped_rows += other.skipped_rows
        self.watch_events += other.watch_events
        self.click_events += other.click_events
        self.like_events += other.like_events
        self.skip_events += other.skip_events
        self.processed_files.extend(other.processed_files)
        self.skipped_files.extend(other.skipped_files)
        self.parse_errors.extend(other.parse_errors)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "total_rows": self.total_rows,
            "imported_rows": self.imported_rows,
            "skipped_rows": self.skipped_rows,
            "watch_events": self.watch_events,
            "click_events": self.click_events,
            "like_events": self.like_events,
            "skip_events": self.skip_events,
            "processed_files": self.processed_files,
            "skipped_files": self.skipped_files,
            "parse_errors": self.parse_errors,
        }


def ingest_takeout_json_bytes(
    db: Session,
    user_id: str,
    raw_bytes: bytes,
    source_file: str | None = None,
) -> TakeoutImportSummary:
    payload = _load_json_bytes(raw_bytes)
    rows = _extract_rows(payload)
    if rows is None:
        raise ValueError("Google Takeout payload must be a JSON array of activity objects.")
    return ingest_takeout_entries(db=db, user_id=user_id, rows=rows, source_file=source_file)


def ingest_takeout_zip_bytes(
    db: Session,
    user_id: str,
    raw_bytes: bytes,
    source_file: str | None = None,
) -> TakeoutImportSummary:
    if not raw_bytes:
        raise ValueError("Uploaded ZIP payload is empty.")

    try:
        archive = zipfile.ZipFile(io.BytesIO(raw_bytes))
    except zipfile.BadZipFile as exc:
        raise ValueError("Invalid ZIP file. Upload a valid Google Takeout archive.") from exc

    summary = TakeoutImportSummary(source_file=source_file)
    channel_cache: dict[str, models.Channel] = {}
    video_cache: dict[str, models.Video] = {}

    with archive as zf:
        json_infos = [item for item in zf.infolist() if not item.is_dir() and item.filename.lower().endswith(".json")]
        if not json_infos:
            raise ValueError("No JSON files found in ZIP archive.")

        sorted_infos = sorted(
            json_infos,
            key=lambda item: (_json_file_relevance(item.filename), item.filename.lower()),
            reverse=True,
        )

        candidates_processed = 0
        for info in sorted_infos:
            if candidates_processed >= MAX_JSON_FILES_PER_ZIP:
                summary.parse_errors.append(
                    f"Reached processing limit ({MAX_JSON_FILES_PER_ZIP} JSON files). Remaining files skipped."
                )
                break
            candidates_processed += 1

            if info.file_size > MAX_JSON_FILE_BYTES:
                summary.skipped_files.append(info.filename)
                summary.parse_errors.append(
                    f"Skipped {info.filename}: file too large ({info.file_size} bytes)."
                )
                continue

            try:
                file_bytes = zf.read(info)
                payload = _load_json_bytes(file_bytes)
            except (KeyError, ValueError) as exc:
                summary.skipped_files.append(info.filename)
                summary.parse_errors.append(f"Skipped {info.filename}: {exc}")
                continue

            rows = _extract_rows(payload)
            if rows is None:
                summary.skipped_files.append(info.filename)
                continue
            if not _looks_like_takeout_rows(rows):
                summary.skipped_files.append(info.filename)
                continue

            file_summary = ingest_takeout_entries(
                db=db,
                user_id=user_id,
                rows=rows,
                source_file=info.filename,
                commit=False,
                channel_cache=channel_cache,
                video_cache=video_cache,
            )
            file_summary.processed_files.append(info.filename)
            summary.merge(file_summary)

    if not summary.processed_files:
        raise ValueError(
            "No relevant YouTube activity JSON files were found in ZIP. "
            "Expected files similar to My Activity/YouTube/*.json."
        )

    db.commit()
    return summary


def ingest_takeout_entries(
    db: Session,
    user_id: str,
    rows: list[dict[str, Any]],
    source_file: str | None = None,
    commit: bool = True,
    channel_cache: dict[str, models.Channel] | None = None,
    video_cache: dict[str, models.Video] | None = None,
) -> TakeoutImportSummary:
    summary = TakeoutImportSummary(
        source_file=source_file,
        total_rows=len(rows),
    )

    local_channel_cache = channel_cache if channel_cache is not None else {}
    local_video_cache = video_cache if video_cache is not None else {}

    for row in rows:
        if not isinstance(row, dict):
            summary.skipped_rows += 1
            continue

        video_id = extract_video_id(row.get("titleUrl"))
        if not video_id:
            summary.skipped_rows += 1
            continue

        channel_id, channel_title = extract_channel(row)
        channel = _get_or_create_channel(
            db=db,
            cache=local_channel_cache,
            channel_id=channel_id,
            channel_title=channel_title,
        )
        _get_or_create_video(
            db=db,
            cache=local_video_cache,
            video_id=video_id,
            channel_id=channel.channel_id,
            video_title=extract_video_title(row),
        )

        event_type = infer_event_type(row)
        event_time = parse_event_time(row.get("time"))
        watch_seconds = extract_watch_seconds(row.get("details"))

        db.add(
            models.Interaction(
                user_id=user_id,
                video_id=video_id,
                event_time=event_time,
                event_type=event_type,
                watch_seconds=watch_seconds,
                metadata_json={
                    "source": TAKEOUT_SOURCE,
                    "source_file": source_file,
                    "raw_title": row.get("title"),
                    "title_url": row.get("titleUrl"),
                    "products": row.get("products"),
                    "activity_controls": row.get("activityControls"),
                },
            )
        )

        summary.imported_rows += 1
        if event_type == "watch":
            summary.watch_events += 1
        elif event_type == "click":
            summary.click_events += 1
        elif event_type == "like":
            summary.like_events += 1
        elif event_type == "skip":
            summary.skip_events += 1

    if commit:
        db.commit()
    return summary


def infer_event_type(row: dict[str, Any]) -> str:
    title = str(row.get("title", "")).lower()
    controls = [str(item).lower() for item in row.get("activityControls", []) if isinstance(item, str)]

    if title.startswith("watched "):
        return "watch"
    if title.startswith("liked "):
        return "like"
    if title.startswith("disliked "):
        return "skip"
    if "watch history" in " ".join(controls):
        return "watch"
    return "click"


def extract_video_id(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()

    if "youtube.com" in host:
        if parsed.path == "/watch":
            value = parse_qs(parsed.query).get("v", [None])[0]
            if value:
                return value.strip()

        if parsed.path.startswith("/shorts/"):
            return parsed.path.split("/shorts/", 1)[1].split("/", 1)[0].strip() or None

        if parsed.path.startswith("/live/"):
            return parsed.path.split("/live/", 1)[1].split("/", 1)[0].strip() or None

    if "youtu.be" in host:
        return parsed.path.strip("/").split("/", 1)[0].strip() or None

    return None


def extract_video_title(row: dict[str, Any]) -> str:
    raw = str(row.get("title", "")).strip()
    for prefix in ("Watched ", "Liked ", "Disliked "):
        if raw.startswith(prefix):
            return raw[len(prefix) :].strip()
    return raw or "Untitled Video"


def extract_channel(row: dict[str, Any]) -> tuple[str, str]:
    subtitles = row.get("subtitles")
    if isinstance(subtitles, list) and subtitles:
        first = subtitles[0] if isinstance(subtitles[0], dict) else None
        if first:
            name = str(first.get("name") or UNKNOWN_CHANNEL_TITLE).strip() or UNKNOWN_CHANNEL_TITLE
            channel_url = first.get("url")
            channel_id = extract_channel_id(channel_url)
            return channel_id or UNKNOWN_CHANNEL_ID, name
    return UNKNOWN_CHANNEL_ID, UNKNOWN_CHANNEL_TITLE


def extract_channel_id(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    if not path:
        return None

    segments = path.split("/")
    if len(segments) >= 2 and segments[0] == "channel":
        return segments[1]
    if segments[0].startswith("@"):
        return f"handle:{segments[0].lower()}"
    return None


def parse_event_time(raw_time: Any) -> datetime:
    if isinstance(raw_time, str) and raw_time.strip():
        clean = raw_time.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(clean)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            pass
    return datetime.now(tz=UTC)


def extract_watch_seconds(details: Any) -> int | None:
    if not isinstance(details, list):
        return None

    for item in details:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).lower()
        if "watch time" not in name and "watched for" not in name:
            continue
        text = str(item.get("value", "")).lower()
        seconds = _parse_duration_to_seconds(text)
        if seconds is not None:
            return seconds
    return None


def _parse_duration_to_seconds(raw: str) -> int | None:
    cleaned = raw.replace(",", " ").replace("and", " ").strip()
    if not cleaned:
        return None

    total = 0
    tokens = cleaned.split()
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if not token.isdigit():
            idx += 1
            continue
        value = int(token)
        if idx + 1 >= len(tokens):
            return total or None
        unit = tokens[idx + 1].lower()
        if unit.startswith("hour"):
            total += value * 3600
        elif unit.startswith("minute"):
            total += value * 60
        elif unit.startswith("second"):
            total += value
        idx += 2
    return total or None


def _get_or_create_channel(
    db: Session,
    cache: dict[str, models.Channel],
    channel_id: str,
    channel_title: str,
) -> models.Channel:
    cached = cache.get(channel_id)
    if cached is not None:
        if channel_title and cached.title != channel_title:
            cached.title = channel_title
        return cached

    channel = db.get(models.Channel, channel_id)
    if channel is None:
        channel = models.Channel(channel_id=channel_id, title=channel_title or UNKNOWN_CHANNEL_TITLE)
        db.add(channel)
    else:
        if channel_title and channel.title != channel_title:
            channel.title = channel_title

    cache[channel_id] = channel
    return channel


def _get_or_create_video(
    db: Session,
    cache: dict[str, models.Video],
    video_id: str,
    channel_id: str,
    video_title: str,
) -> models.Video:
    cached = cache.get(video_id)
    if cached is not None:
        if video_title and cached.title != video_title:
            cached.title = video_title
        if cached.channel_id != channel_id:
            cached.channel_id = channel_id
        return cached

    video = db.get(models.Video, video_id)
    if video is None:
        video = models.Video(
            video_id=video_id,
            channel_id=channel_id,
            title=video_title or "Untitled Video",
            description="",
            tags=None,
        )
        db.add(video)
    else:
        if video_title and video.title != video_title:
            video.title = video_title
        if video.channel_id != channel_id:
            video.channel_id = channel_id

    cache[video_id] = video
    return video


def _load_json_bytes(raw_bytes: bytes) -> Any:
    try:
        text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("JSON file must be UTF-8 encoded.") from exc

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON payload: {exc}") from exc


def _extract_rows(payload: Any) -> list[dict[str, Any]] | None:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("rows", "events", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return None


def _looks_like_takeout_rows(rows: list[dict[str, Any]]) -> bool:
    for row in rows[:100]:
        if not isinstance(row, dict):
            continue
        title_url = str(row.get("titleUrl", "")).lower()
        header = str(row.get("header", "")).lower()
        title = str(row.get("title", "")).lower()
        if "youtube.com" in title_url or "youtu.be" in title_url:
            return True
        if "youtube" in header:
            return True
        if title.startswith("watched ") or title.startswith("liked ") or title.startswith("disliked "):
            return True
    return False


def _json_file_relevance(path: str) -> int:
    lowered = path.lower()
    score = 0
    if "youtube" in lowered:
        score += 5
    if "my activity" in lowered or "myactivity" in lowered:
        score += 3
    if "watch-history" in lowered or "watch history" in lowered:
        score += 8
    if "liked" in lowered:
        score += 2
    if "search" in lowered:
        score += 1
    if lowered.endswith("myactivity.json"):
        score += 2
    return score
