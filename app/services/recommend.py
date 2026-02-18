from __future__ import annotations

from datetime import datetime
from math import log1p

import numpy as np
from scipy.sparse import csr_matrix, vstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy.orm import Session

from app import crud, models, schemas

POSITIVE_EVENTS = {"watch", "click", "like"}
EVENT_BASE_WEIGHTS = {"watch": 2.0, "click": 1.0, "like": 3.0}


def generate_recommendations(db: Session, user_id: str, k: int = 20) -> list[schemas.RecommendationItem]:
    videos = crud.get_all_videos(db)
    if not videos:
        return []

    interactions = crud.get_user_interactions(db, user_id=user_id)
    interacted_video_ids = {item.video_id for item in interactions}

    corpus = [_video_text(item) for item in videos]
    vectorizer = TfidfVectorizer(stop_words="english", max_features=25000)
    matrix = vectorizer.fit_transform(corpus)
    idx_by_video_id = {video.video_id: idx for idx, video in enumerate(videos)}

    positive_interactions = [
        item for item in interactions if item.event_type in POSITIVE_EVENTS and item.video_id in idx_by_video_id
    ]
    if not positive_interactions:
        return _cold_start_recommendations(videos, matrix, interacted_video_ids, k)

    profile = _build_user_profile(matrix, idx_by_video_id, positive_interactions)
    if profile is None:
        return _cold_start_recommendations(videos, matrix, interacted_video_ids, k)

    scores = cosine_similarity(profile, matrix).flatten()
    for video_id in interacted_video_ids:
        idx = idx_by_video_id.get(video_id)
        if idx is not None:
            scores[idx] = -1.0

    ranked_indices = np.argsort(scores)[::-1]
    items: list[schemas.RecommendationItem] = []
    for idx in ranked_indices:
        if len(items) >= k:
            break
        score = float(scores[idx])
        if score < 0:
            continue
        video = videos[idx]
        reasons = ["Similar to your recent watched content"]
        keyword_reason = _keyword_overlap_reason(vectorizer, profile, matrix[idx])
        if keyword_reason:
            reasons.append(keyword_reason)
        items.append(
            schemas.RecommendationItem(
                video_id=video.video_id,
                score=round(score, 6),
                reasons=reasons,
            )
        )
    return items


def _video_text(video: models.Video) -> str:
    return f"{video.title or ''} {video.description or ''}".strip()


def _watch_weight(watch_seconds: int | None) -> float:
    if watch_seconds is None or watch_seconds <= 0:
        return 1.0
    return 1.0 + min(log1p(watch_seconds), 5.0)


def _build_user_profile(
    matrix: csr_matrix,
    idx_by_video_id: dict[str, int],
    interactions: list[models.Interaction],
) -> csr_matrix | None:
    row_mats = []
    weights = []

    for interaction in interactions:
        idx = idx_by_video_id.get(interaction.video_id)
        if idx is None:
            continue
        base_weight = EVENT_BASE_WEIGHTS.get(interaction.event_type, 1.0)
        weight = base_weight * _watch_weight(interaction.watch_seconds)
        row_mats.append(matrix[idx])
        weights.append(weight)

    if not row_mats:
        return None

    stacked = vstack(row_mats)
    weight_arr = np.array(weights, dtype=np.float64)
    weighted = stacked.multiply(weight_arr[:, np.newaxis])
    summed = weighted.sum(axis=0)
    total_weight = float(weight_arr.sum())
    if total_weight <= 0:
        return None
    return csr_matrix(summed / total_weight)


def _cold_start_recommendations(
    videos: list[models.Video],
    matrix: csr_matrix,
    interacted_video_ids: set[str],
    k: int,
) -> list[schemas.RecommendationItem]:
    candidate_indices = [idx for idx, video in enumerate(videos) if video.video_id not in interacted_video_ids]
    if not candidate_indices:
        return []

    nnz_arr = matrix.getnnz(axis=1)

    def recency_key(video: models.Video) -> datetime:
        if video.published_at is not None:
            return video.published_at
        return video.created_at

    sorted_candidates = sorted(
        candidate_indices,
        key=lambda idx: (int(nnz_arr[idx]), recency_key(videos[idx])),
        reverse=True,
    )
    max_nnz = max(int(nnz_arr[idx]) for idx in sorted_candidates) or 1

    items: list[schemas.RecommendationItem] = []
    for idx in sorted_candidates[:k]:
        video = videos[idx]
        score = int(nnz_arr[idx]) / max_nnz
        items.append(
            schemas.RecommendationItem(
                video_id=video.video_id,
                score=round(float(score), 6),
                reasons=[
                    "Cold start recommendation based on rich metadata",
                    "Prioritized by metadata richness and recency",
                ],
            )
        )
    return items


def _keyword_overlap_reason(
    vectorizer: TfidfVectorizer,
    user_profile: csr_matrix,
    candidate_vec: csr_matrix,
    max_terms: int = 3,
) -> str | None:
    overlap = user_profile.multiply(candidate_vec)
    if overlap.nnz == 0:
        return None

    feature_names = vectorizer.get_feature_names_out()
    data = overlap.data
    indices = overlap.indices
    order = np.argsort(data)[::-1][:max_terms]
    keywords = [feature_names[indices[pos]] for pos in order if data[pos] > 0]
    if not keywords:
        return None
    return f"Overlapping keywords: {', '.join(keywords)}"
