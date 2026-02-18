# YouTube Recommendations API

Production-style baseline recommendation service for YouTube-like video discovery.  
The system logs user interactions, builds a TF-IDF user profile from watched/clicked/liked content, and serves recommendations through a FastAPI REST API.

## Tech Stack

- Python 3.11
- FastAPI + Uvicorn
- PostgreSQL (source of truth) with SQLAlchemy 2.0 ORM
- Redis (recommendation caching + API response caching)
- Scikit-learn (TF-IDF + cosine similarity)
- Docker Compose (local Postgres + Redis)

## Project Structure

```text
app/
  main.py
  config.py
  db.py
  redis_client.py
  models.py
  schemas.py
  crud.py
  services/
    recommend.py
    ingest.py
tests/
  test_smoke.py
scripts/
  seed_demo.py
requirements.txt
Dockerfile
docker-compose.yml
.gitignore
README.md
```

## Environment Variables

- `DATABASE_URL` (required in non-local deployments)
  - Example: `postgresql+psycopg://postgres:postgres@localhost:5432/youtube_recs`
- `REDIS_URL` (required in non-local deployments)
  - Example: `redis://localhost:6379/0`
- `CORS_ORIGINS` (comma-separated string)
  - Example: `http://localhost:3000,http://localhost:5173`
  - Local quick value: `*` or `["*"]`
- `YOUTUBE_API_KEY` (optional; used by future ingest workflow)
- `ENABLE_TAKEOUT_IMPORT` (optional, default `true`; set `false` to disable all Takeout import endpoints)

## Local Setup

1. Start Postgres and Redis:

```bash
docker-compose up -d
```

2. Create and activate a virtual environment:

```bash
python -m venv .venv
```

Windows (PowerShell):
```powershell
.venv\Scripts\Activate.ps1
```

macOS/Linux:
```bash
source .venv/bin/activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Set env vars (example):

Windows (PowerShell):
```powershell
$env:DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/youtube_recs"
$env:REDIS_URL="redis://localhost:6379/0"
$env:CORS_ORIGINS="*"
$env:ENABLE_TAKEOUT_IMPORT="false"
```

macOS/Linux:
```bash
export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/youtube_recs"
export REDIS_URL="redis://localhost:6379/0"
export CORS_ORIGINS="*"
export ENABLE_TAKEOUT_IMPORT="false"
```

5. Run API:

```bash
uvicorn app.main:app --reload
```

Or use one command on Windows PowerShell:

```powershell
.\run_local.ps1
```

Optional flags:
- `.\run_local.ps1 -SkipCompose` (if services already running)
- `.\run_local.ps1 -SkipInstall` (if dependencies already installed)
- `.\run_local.ps1 -NoRun` (setup only, do not start API)
- `.\run_local.ps1 -EnableTakeoutImport false` (disable Takeout import endpoints)

## Replicate Setup (Windows PowerShell)

Use this exact sequence to reproduce the working local setup:

1. Open PowerShell in repo root:

```powershell
cd C:\Users\arkan\Documents\Projects\youtube-recs
```

2. Allow script execution for current shell session only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

3. Start local API using SQLite fallback (works without local Postgres):

```powershell
$env:DATABASE_URL="sqlite:///./youtube_recs.db"
$env:REDIS_URL="redis://localhost:6379/0"
$env:CORS_ORIGINS='["*"]'
$env:ENABLE_TAKEOUT_IMPORT="false"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

4. In a second terminal, verify connectivity:

```powershell
Test-NetConnection 127.0.0.1 -Port 8000
Invoke-RestMethod "http://127.0.0.1:8000/health"
```

5. Expected:
- `TcpTestSucceeded : True`
- `/health` response with `status = ok`

## Seed Demo Data (One Command)

With the API running, seed demo videos/interactions and fetch recommendations:

```powershell
.\.venv\Scripts\python.exe scripts\seed_demo.py --user-id AbhiKanani07 --k 20
```

Optional:

```powershell
.\.venv\Scripts\python.exe scripts\seed_demo.py --base-url http://127.0.0.1:8000 --user-id demo-user --k 10
```

This script:
- upserts two channels
- upserts six videos
- logs interactions for the provided user
- prints recommendation output JSON

## PowerShell Request Note

In PowerShell, prefer `Invoke-RestMethod` for JSON POSTs. `curl.exe -d` often needs heavy escaping and can cause `422` JSON decode errors.

6. Open docs:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

## API Endpoints

- `GET /health`
- `GET /redis-ping`
- `POST /channels/upsert`
- `POST /videos/upsert`
- `GET /videos?limit=200`
- `POST /interactions`
- `GET /recommendations?user_id=<id>&k=20`
- `POST /cache/clear?user_id=<id>`
- `POST /ingest/google-takeout` (JSON body import)
- `POST /ingest/google-takeout/file?user_id=<id>&source_file=<name>` (raw JSON file import)
- `POST /ingest/google-takeout/zip?user_id=<id>&source_file=<name>` (raw ZIP import; auto-selects relevant JSON files)
  - These three endpoints are disabled when `ENABLE_TAKEOUT_IMPORT=false`.

### cURL Examples

Create/Update channel:
```bash
curl -X POST "http://127.0.0.1:8000/channels/upsert" \
  -H "Content-Type: application/json" \
  -d '{
    "channel_id": "UC001",
    "title": "ML Insights"
  }'
```

Create/Update video:
```bash
curl -X POST "http://127.0.0.1:8000/videos/upsert" \
  -H "Content-Type: application/json" \
  -d '{
    "video_id": "VID001",
    "channel_id": "UC001",
    "title": "TF-IDF Recommenders Explained",
    "description": "Learn content-based recommendation systems.",
    "tags": ["ml", "recommender", "tfidf"],
    "duration_seconds": 540
  }'
```

Log interaction:
```bash
curl -X POST "http://127.0.0.1:8000/interactions" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-123",
    "video_id": "VID001",
    "event_type": "watch",
    "watch_seconds": 300,
    "metadata": {"source": "homepage"}
  }'
```

Get recommendations:
```bash
curl "http://127.0.0.1:8000/recommendations?user_id=user-123&k=20"
```

Import Google Takeout JSON (raw rows in JSON body):
```bash
curl -X POST "http://127.0.0.1:8000/ingest/google-takeout" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user-123",
    "source_file": "watch-history.json",
    "rows": [
      {
        "header": "YouTube",
        "title": "Watched TF-IDF Recommenders Explained",
        "titleUrl": "https://www.youtube.com/watch?v=VID001",
        "subtitles": [{"name": "ML Insights", "url": "https://www.youtube.com/channel/UC001"}],
        "time": "2025-01-04T17:28:31.000Z",
        "products": ["YouTube"],
        "activityControls": ["YouTube watch history"]
      }
    ]
  }'
```

Import Google Takeout JSON file directly:
```bash
curl -X POST "http://127.0.0.1:8000/ingest/google-takeout/file?user_id=user-123&source_file=watch-history.json" \
  -H "Content-Type: application/json" \
  --data-binary "@watch-history.json"
```

Import full Google Takeout ZIP directly:
```bash
curl -X POST "http://127.0.0.1:8000/ingest/google-takeout/zip?user_id=user-123&source_file=takeout-2026-02-17.zip" \
  -H "Content-Type: application/zip" \
  --data-binary "@takeout-2026-02-17.zip"
```

## How Recommendations Work

- Build corpus from `title + description`.
- Fit TF-IDF (`stop_words="english"`, `max_features=25000`).
- Build user profile as weighted mean of vectors from `watch`/`click`/`like` events.
- Score all videos using cosine similarity against user profile.
- Exclude already interacted videos.
- Cold start fallback uses metadata richness (`TF-IDF non-zero count`) and recency.
- Results include explanation reasons and optional overlapping keywords.

## Caching Strategy

- Recommendation cache key: `recs:{user_id}:{k}` with TTL = 1800 seconds.
- Video list API cache key: `api:videos:{limit}` with TTL = 300 seconds.
- Placeholder reserved for YouTube API response cache keys: `yt_cache:*`.
- Google Takeout imports automatically clear user recommendation cache keys.
- ZIP imports report `processed_files`, `skipped_files`, and `parse_errors` for observability.

## Running Tests

```bash
pytest -q
```

Smoke tests cover core availability endpoints.

## Render Deployment

1. Push repository to GitHub.
2. In Render, create:
   - Web Service (Python)
   - Managed PostgreSQL
   - Managed Redis
3. Set environment variables in Web Service:
   - `DATABASE_URL=postgresql+psycopg://<user>:<pass>@<host>:<port>/<db>`
   - `REDIS_URL=redis://default:<pass>@<host>:<port>`
   - `CORS_ORIGINS=https://your-frontend.example.com`
   - `YOUTUBE_API_KEY=<optional>`
4. Build command:
   - `pip install -r requirements.txt`
5. Start command:
   - `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
6. Deploy and validate:
   - `GET /health`
   - `GET /redis-ping`

## Future Improvements

- Hybrid recommender (content + collaborative filtering)
- ALS/implicit matrix factorization for personalization at scale
- Embedding-based semantic retrieval + ANN index
- Offline evaluation (Precision@K, Recall@K, NDCG)
- Real-time feature pipelines and event streaming
