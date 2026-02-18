from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class VideoSeed:
    video_id: str
    channel_id: str
    title: str
    description: str
    tags: list[str]
    duration_seconds: int


VIDEOS: list[VideoSeed] = [
    VideoSeed(
        video_id="VID_ML_001",
        channel_id="UC_ML_01",
        title="Intro to Recommender Systems",
        description="Overview of collaborative and content based methods.",
        tags=["recommender", "ml", "intro"],
        duration_seconds=600,
    ),
    VideoSeed(
        video_id="VID_ML_002",
        channel_id="UC_ML_01",
        title="TF-IDF for Content Ranking",
        description="Using tfidf vectors for ranking videos.",
        tags=["tfidf", "nlp", "ranking"],
        duration_seconds=720,
    ),
    VideoSeed(
        video_id="VID_ML_003",
        channel_id="UC_ML_01",
        title="Cosine Similarity Explained",
        description="Vector similarity for recommendation and retrieval.",
        tags=["cosine", "vectors", "ml"],
        duration_seconds=540,
    ),
    VideoSeed(
        video_id="VID_ML_004",
        channel_id="UC_ML_01",
        title="FastAPI Production Patterns",
        description="Production backend patterns and deployment strategy.",
        tags=["fastapi", "backend", "deploy"],
        duration_seconds=800,
    ),
    VideoSeed(
        video_id="VID_ML_005",
        channel_id="UC_ML_02",
        title="Postgres Indexing Deep Dive",
        description="Database indexing strategies for low-latency systems.",
        tags=["postgres", "database", "indexing"],
        duration_seconds=900,
    ),
    VideoSeed(
        video_id="VID_ML_006",
        channel_id="UC_ML_02",
        title="Redis Caching for APIs",
        description="Cache patterns and invalidation techniques.",
        tags=["redis", "cache", "api"],
        duration_seconds=670,
    ),
]


def request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> Any:
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = Request(url=url, method=method, data=body, headers=headers)
    try:
        with urlopen(req, timeout=30) as response:
            raw = response.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {details}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot connect to API at {url}: {exc}") from exc


def upsert_channels(base_url: str) -> None:
    channels = [
        {"channel_id": "UC_ML_01", "title": "ML Core"},
        {"channel_id": "UC_ML_02", "title": "Data Infra"},
    ]
    for channel in channels:
        request_json("POST", f"{base_url}/channels/upsert", channel)


def upsert_videos(base_url: str) -> None:
    for video in VIDEOS:
        payload = {
            "video_id": video.video_id,
            "channel_id": video.channel_id,
            "title": video.title,
            "description": video.description,
            "tags": video.tags,
            "duration_seconds": video.duration_seconds,
        }
        request_json("POST", f"{base_url}/videos/upsert", payload)


def create_interactions(base_url: str, user_id: str) -> None:
    interactions = [
        {"user_id": user_id, "video_id": "VID_ML_001", "event_type": "watch", "watch_seconds": 420},
        {"user_id": user_id, "video_id": "VID_ML_002", "event_type": "watch", "watch_seconds": 510},
        {"user_id": user_id, "video_id": "VID_ML_003", "event_type": "like"},
        {"user_id": user_id, "video_id": "VID_ML_006", "event_type": "click"},
    ]
    for interaction in interactions:
        request_json("POST", f"{base_url}/interactions", interaction)


def print_recommendations(base_url: str, user_id: str, k: int) -> None:
    data = request_json("GET", f"{base_url}/recommendations?user_id={user_id}&k={k}")
    print(json.dumps(data, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed demo data and fetch recommendations.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--user-id", default="AbhiKanani07", help="User id for seeded interactions")
    parser.add_argument("--k", type=int, default=10, help="Number of recommendations")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")

    try:
        health = request_json("GET", f"{base_url}/health")
        if not isinstance(health, dict) or health.get("status") != "ok":
            raise RuntimeError(f"Unexpected /health response: {health}")

        upsert_channels(base_url)
        upsert_videos(base_url)
        create_interactions(base_url, args.user_id)
        print_recommendations(base_url, args.user_id, args.k)
    except Exception as exc:  # noqa: BLE001
        print(str(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
