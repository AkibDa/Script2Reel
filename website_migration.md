# Script2Reel — Streamlit → Website Migration Plan

Goal: replace the single Streamlit script with a real frontend + backend web app.
Keep design basic (it just needs to look clean and functional), but make the
architecture proper: a stateless-ish frontend, an API backend, background job
processing, and a pluggable model layer that can run against cloud APIs or
local models depending on config — no code changes required to switch.

---

## 1. Why Streamlit doesn't fit anymore

Streamlit re-runs the whole script top-to-bottom on every interaction and blocks
the UI thread while `reel_app.invoke(...)` runs. That's fine for a demo, but it
means: no real concurrent users, no "leave the page and come back to check
progress," and no separation between "the thing that generates reels" and
"the thing that displays them." A website with a backend API fixes all three.

---

## 2. Target architecture

```
┌─────────────────┐        HTTP/JSON         ┌──────────────────────┐
│   Frontend       │ ───────────────────────▶│   Backend (FastAPI)  │
│  (React or plain │◀─────────────────────── │                       │
│  HTML/JS)        │   polling or WebSocket   │  /jobs   /jobs/{id}   │
└─────────────────┘                          │  /jobs/{id}/download  │
                                              └──────────┬────────────┘
                                                         │
                                                         ▼
                                              ┌──────────────────────┐
                                              │  Background worker    │
                                              │  runs your existing   │
                                              │  LangGraph pipeline   │
                                              └──────────┬────────────┘
                                                         │
                                     ┌───────────────────┼───────────────────┐
                                     ▼                   ▼                   ▼
                              LLM Provider         Image Provider      Voice Provider
                             (cloud/local)         (cloud/local)      (cloud/local)
```

Your existing `graph.py`, `video_builder.py`, and provider files barely change —
they get called from an API endpoint + background task instead of from a
Streamlit button handler.

---

## 3. Backend

**Framework: FastAPI** (already your planned choice; async support and background
tasks are built in, so this fits naturally).

### 3.1 Folder structure
```
backend/
├── main.py                  # FastAPI app, routes
├── jobs.py                  # Job store + status tracking
├── workflows/
│     graph.py               # existing LangGraph pipeline (unchanged)
├── services/
│     llm_provider.py        # NEW: cloud/local LLM switch
│     image_provider.py      # existing, extend with cloud option
│     voice_provider.py      # existing (ElevenLabs/gTTS), extend with local option
│     video_builder.py       # existing (unchanged)
├── models.py                 # Pydantic request/response schemas
├── config.py                  # env-driven provider selection
└── requirements.txt
```

### 3.2 Core API endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/jobs` | Start a new reel generation job. Body = the same fields your sidebar currently collects (prompt, duration, style, platform, voice, keys). Returns `{ "job_id": "..." }` immediately. |
| `GET` | `/api/jobs/{job_id}` | Poll job status: `{ "status": "running", "stage": "Generating images...", "progress": 45 }` or `"status": "done"` / `"failed"`. |
| `GET` | `/api/jobs/{job_id}/video` | Stream/download the finished `.mp4`. |
| `GET` | `/api/jobs/{job_id}/subtitles` | Download the `.srt`. |
| `GET` | `/api/jobs/{job_id}/agent-outputs` | Return the intermediate scene JSON (replaces your "View Agent Outputs" expander). |
| `DELETE` | `/api/jobs/{job_id}` | Optional cleanup endpoint to delete a run's files. |

### 3.3 Background execution — pick one

**Option A (recommended to start): FastAPI `BackgroundTasks`**
Simplest possible option. Good enough for a small number of concurrent users / a
class project / an early product.
```python
@app.post("/api/jobs")
async def create_job(req: JobRequest, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued"}
    background_tasks.add_task(run_pipeline, job_id, req)
    return {"job_id": job_id}
```
Limitation: tasks run in the same process, so a server restart loses in-flight
jobs, and there's no retry/dead-letter handling.

**Option B (once you outgrow A): Celery + Redis, or RQ**
A real task queue. Jobs survive server restarts, can be retried automatically,
and you can scale workers separately from the API. Worth moving to this if you
expect multiple simultaneous users or want production reliability.

### 3.4 Progress reporting

Two options, pick based on how "live" you want the UI:

- **Polling (simplest):** frontend calls `GET /api/jobs/{id}` every 2–3 seconds.
  Update `jobs[job_id]["stage"]` inside each LangGraph node (or between
  pipeline steps) so the endpoint has something fresh to report.
- **WebSocket (nicer, a bit more work):** open a socket per job, push stage
  updates as they happen instead of polling. Only worth it if you want a
  snappier feel; polling is perfectly fine for this project.

### 3.5 Job storage

Store job metadata + status in a `dict` (single-process, fine for now) or
SQLite (`jobs.db`) if you want it to survive server restarts. A full database
(Postgres) is overkill until you have real multi-user traffic.

### 3.6 File storage

Keep your existing `run_dir` pattern (`assets/{job_id}/...`) — it already
maps cleanly onto `job_id` as your directory key. No change needed there,
just swap `thread_id` → `job_id` as the naming source.

---

## 4. Frontend

Design should be **basic but clean** — a single-page app is enough, no need
for routing/multiple pages.

### 4.1 Option A — Plain HTML/CSS/JS (fastest to build)
Good if you want to avoid a build step entirely. One `index.html`, one `app.js`,
one `style.css`. `fetch()` calls to the FastAPI backend, `setInterval` for
polling job status. This is enough for "looks good and does the job."

### 4.2 Option B — React (if you want it to feel more like a real product)
Use plain React (no heavy framework needed) or Next.js if you also want
server-side rendering / easy deployment to Vercel. Recommended only if you're
already comfortable with React — don't add framework overhead just for its
own sake on a project this size.

### 4.3 Minimum UI (either option)

- Form: prompt textarea, duration/style/platform/voice dropdowns, API key
  inputs (Gemini required, ElevenLabs optional), music upload, volume slider —
  same fields as your current sidebar.
- "Generate Reel" button → `POST /api/jobs` → store `job_id` in state.
- Progress area: poll `GET /api/jobs/{id}`, show a progress bar + current
  stage text (mirrors your current `progress_bar` / `status_text`).
- On completion: `<video>` tag pointing at `/api/jobs/{id}/video`, plus
  download buttons for MP4 and SRT.
- On failure: show the error message, keep a "Retry" button that re-hits
  `POST /api/jobs` with the same `job_id` semantics your checkpointing
  already supports.

### 4.4 Styling
Keep it simple: one CSS file, a dark theme (matches your current Streamlit
look), a centered card layout, basic responsive breakpoints so it's usable on
mobile. No component library needed unless you're using React, in which case
plain CSS or Tailwind (utility classes, no build complexity) both work fine.

---

## 5. Cloud vs. Local model switching

This is the key new capability to design for. The goal: **one config value
per model type**, no code branching scattered across the app.

### 5.1 Central config (`.env` + `config.py`)

```env
# .env
LLM_PROVIDER=cloud        # cloud | local
IMAGE_PROVIDER=cloud      # cloud | local
VOICE_PROVIDER=cloud      # cloud | local

GOOGLE_API_KEY=...
FAL_API_KEY=...           # or REPLICATE_API_KEY
ELEVENLABS_API_KEY=...

LOCAL_LLM_MODEL=llama3.1:8b        # if using Ollama locally
LOCAL_IMAGE_MODEL=RunDiffusion/Juggernaut-X-v10
LOCAL_TTS_ENGINE=kokoro             # kokoro | piper
```

```python
# config.py
import os
from dotenv import load_dotenv
load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "cloud")
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "cloud")
VOICE_PROVIDER = os.getenv("VOICE_PROVIDER", "cloud")
```

### 5.2 Provider abstraction pattern (apply to all three: LLM, image, voice)

Use a small factory so the rest of the pipeline never checks provider type
directly — it just calls `.generate(...)` / `.invoke(...)` on whatever object
the factory handed back.

```python
# services/image_provider.py
from typing import Protocol
import config

class ImageProvider(Protocol):
    def generate(self, prompt: str, run_dir: str, filename: str) -> str: ...

class CloudFluxProvider:
    """Calls fal.ai / Replicate FLUX endpoint."""
    def generate(self, prompt, run_dir, filename):
        ...  # HTTP call, save result, return path

class LocalSDXLProvider:
    """Your existing diffusers-based implementation — unchanged."""
    def generate(self, prompt, run_dir, filename):
        ...

def get_image_provider() -> ImageProvider:
    if config.IMAGE_PROVIDER == "cloud":
        return CloudFluxProvider()
    return LocalSDXLProvider()
```

Do the same shape for:
- **LLM provider** — `cloud` = `ChatGoogleGenerativeAI` (your current Gemini
  setup), `local` = an Ollama-backed LangChain chat model (e.g.
  `langchain_ollama.ChatOllama(model=config.LOCAL_LLM_MODEL)`) if you want a
  fully local option with no Gemini key at all.
- **Voice provider** — `cloud` = ElevenLabs (existing), `local` = Kokoro/Piper
  (existing gTTS fallback can stay as a third "no-key" tier, or be folded into
  `local`).

### 5.3 Wiring into `graph.py`

Replace direct instantiation (`ChatGoogleGenerativeAI(...)`, `LocalSDXLProvider()`)
with calls to `get_llm_provider()` / `get_image_provider()` / `get_voice_provider()`.
Nothing else in your agent functions needs to change — they already just call
`.invoke()` / `.generate()` on whatever object they're given.

### 5.4 Exposing the choice to the user (optional)

If you want end users to pick cloud vs. local per-request (not just per-deployment):
add `llm_provider`, `image_provider`, `voice_provider` fields to the job-creation
request body, and have the factory functions accept an override parameter that
falls back to the `.env` default when not specified. Only do this if you actually
want users toggling it — otherwise, a deployment-level `.env` setting is simpler
and is enough for a college project or small-scale production use.

---

## 6. Deployment notes

- **Cloud-provider mode:** backend can run anywhere lightweight — a small VM,
  Render, Railway, Fly.io — since there's no GPU requirement when everything
  is API calls.
- **Local-model mode:** backend needs to run on a machine with a GPU
  (your college infra, or a rented GPU instance) since `LocalSDXLProvider`
  and local TTS/LLM need real compute. Keep this as a config flip, not a
  separate codebase, so the same deployment can be moved between college GPU
  hardware and a cheap cloud VM depending on which providers are active.
- **Frontend:** static hosting is enough (Vercel, Netlify, or just served by
  FastAPI itself via `StaticFiles` if you want a single deployable unit).

---

## 7. Suggested build order

1. Wrap the existing pipeline in a FastAPI endpoint using `BackgroundTasks`
   (Section 3.3, Option A) — get `POST /api/jobs` + `GET /api/jobs/{id}`
   working against your current cloud-only providers first.
2. Build the minimal frontend (Section 4) against those two endpoints.
3. Add video/subtitle download endpoints, confirm the full loop works
   end-to-end through the new website instead of Streamlit.
4. Introduce the provider abstraction (Section 5) and confirm `local` mode
   works for at least image generation (the most GPU-dependent, most likely
   piece to run locally).
5. Only then consider Celery/Redis (Section 3.3, Option B) if you actually
   need job durability/scaling — don't add it preemptively.