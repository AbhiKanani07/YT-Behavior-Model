import io
import json
import zipfile
from datetime import UTC

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import models
from app.db import Base
from app.services.ingest import (
    extract_channel_id,
    extract_video_id,
    ingest_takeout_zip_bytes,
    infer_event_type,
    parse_event_time,
)


def test_extract_video_id_from_watch_url() -> None:
    value = extract_video_id("https://www.youtube.com/watch?v=abc123xyz")
    assert value == "abc123xyz"


def test_extract_video_id_from_shorts_url() -> None:
    value = extract_video_id("https://www.youtube.com/shorts/short123")
    assert value == "short123"


def test_extract_video_id_from_youtu_be_url() -> None:
    value = extract_video_id("https://youtu.be/xyz987")
    assert value == "xyz987"


def test_extract_channel_id_from_channel_url() -> None:
    value = extract_channel_id("https://www.youtube.com/channel/UC_TEST_123")
    assert value == "UC_TEST_123"


def test_extract_channel_id_from_handle_url() -> None:
    value = extract_channel_id("https://www.youtube.com/@mychannel")
    assert value == "handle:@mychannel"


def test_infer_event_type_watch() -> None:
    row = {"title": "Watched Building Recommenders"}
    assert infer_event_type(row) == "watch"


def test_infer_event_type_like() -> None:
    row = {"title": "Liked Building Recommenders"}
    assert infer_event_type(row) == "like"


def test_parse_event_time_returns_timezone_aware_datetime() -> None:
    dt = parse_event_time("2025-01-04T17:28:31.000Z")
    assert dt.tzinfo == UTC


def test_ingest_takeout_zip_bytes_imports_relevant_json() -> None:
    rows = [
        {
            "header": "YouTube",
            "title": "Watched Recommender Systems 101",
            "titleUrl": "https://www.youtube.com/watch?v=vid123",
            "subtitles": [{"name": "ML Channel", "url": "https://www.youtube.com/channel/UCML"}],
            "time": "2025-01-04T17:28:31.000Z",
            "products": ["YouTube"],
            "activityControls": ["YouTube watch history"],
        }
    ]

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Takeout/My Activity/YouTube/MyActivity.json", json.dumps(rows))
        zf.writestr("Takeout/Maps/MapsActivity.json", json.dumps([{"foo": "bar"}]))

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        summary = ingest_takeout_zip_bytes(
            db=db,
            user_id="user-zip-1",
            raw_bytes=archive_buffer.getvalue(),
            source_file="takeout.zip",
        )
        assert summary.imported_rows == 1
        assert summary.watch_events == 1
        assert "Takeout/My Activity/YouTube/MyActivity.json" in summary.processed_files

        interactions = db.execute(select(models.Interaction)).scalars().all()
        assert len(interactions) == 1
        assert interactions[0].event_type == "watch"


def test_ingest_takeout_zip_bytes_rejects_zip_without_relevant_rows() -> None:
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Takeout/Other/data.json", json.dumps([{"foo": "bar"}]))

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        with pytest.raises(ValueError, match="No relevant YouTube activity JSON files"):
            ingest_takeout_zip_bytes(
                db=db,
                user_id="user-zip-2",
                raw_bytes=archive_buffer.getvalue(),
                source_file="takeout.zip",
            )
