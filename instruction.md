# Script2Reel (AI Reel Generator) — Build Instructions

Turn a single text prompt into a finished short vertical video reel (voice, visuals, music, subtitles) using an agentic pipeline.

**Context:** Teacher-approved college project. Not restricted to open-source. Not restricted by budget in the strict sense, but should still be practical to finish in ~48 hours. Optimize for **quality + reliability + a working demo**, not for "100% open source."

---

## 1. Overall Pipeline

```
User Prompt
     │
     ▼
Prompt Refiner Agent      → target audience, tone, hook, CTA, pacing
     │
     ▼
Screenplay Agent          → narration + scene-by-scene script
     │
     ▼
Scene Planner Agent       → structured JSON (scene, duration, visual, voice, effect)
     │
     ▼
Visual Director Agent     → turns each "visual" into a detailed image-gen prompt
     │
     ├─────────────┬─────────────┐
     ▼             ▼             ▼
 Image Gen      Voice Gen     Music Selection
     │             │          (royalty-free, volume-ducked)
     ▼             │
 Animate images     │
 (motion stage)     │
     │             │
     └──────┬───────┘
            ▼
   Video Composer (assembly)
   clips + voice + music + subtitles + transitions
            ▼
     Final Reel (.mp4)
```

All 4 reasoning agents (Refiner, Screenplay, Planner, Visual Director) can be the same LLM (Gemini) with different, focused system prompts — giving each a distinct name/responsibility is what makes the architecture "agentic" rather than one giant prompt, even though it's one model underneath.

---

## 2. Stage-by-Stage: What To Do

### Stage 1 — Input
User provides a natural-language request, e.g. *"Create a 30-second motivational reel about discipline."*
Parse/collect into a config object:
```json
{ "topic": "discipline", "duration": 30, "style": "motivational", "platform": "instagram" }
```
Also collect (via UI, not just LLM inference): voice gender, platform, duration, style — these become parameters passed into every downstream agent.

### Stage 2 — Prompt Refiner Agent
**Do:** Expand the raw prompt into target audience, tone, pacing, hook, and CTA. Feed this enriched brief — not the raw prompt — into the Screenplay Agent.
Example:
```
Raw:      Make a reel on discipline.
Refined:  30-second Instagram reel, emotional hook, 5 scenes, fast pacing, strong CTA.
```

### Stage 3 — Screenplay Agent
**Do:** Generate narration broken into scenes, each with narration text, visual description, camera angle, duration, and transition.
```
Scene 1
Narration: Everyone wants success...
Visual: Person waking up early
Duration: 5 sec
Transition: Fade
```

### Stage 4 — Scene Planner Agent
**Do:** Convert the screenplay into structured JSON — this becomes the single source of truth for every downstream stage.
```json
[
  { "scene": 1, "duration": 5, "visual": "person waking at sunrise", "voice": "Everyone wants success...", "effect": "zoom in" }
]
```

### Stage 5 — Visual Director Agent
**Do:** Rewrite each scene's short `visual` field into a detailed, model-ready image prompt. This step alone noticeably improves output quality.
```
Instead of: "Student studying"
Generate:   "A determined university student studying late at night under warm
             desk lighting, cinematic composition, shallow depth of field,
             realistic skin tones, dramatic contrast, 35mm lens, ultra detailed."
```

### Stage 6 — Image Generation
**Do:** Generate one image per scene from the Visual Director's prompt.

**Options (pick one):**
- **FLUX.1-dev** — best prompt-following, recommended if GPU access (college infra) is available.
- **SDXL / JuggernautXL / DreamShaper XL** — solid open-source fallback, lighter hardware needs.
- **FLUX.1 Kontext** — if you need image-editing/consistency across scenes, not just generation.

Libraries: `diffusers`, `transformers`, `accelerate`.

### Stage 7 — Motion / Video Generation
This is the highest-risk, most time-consuming stage. Choose deliberately.

**Options (pick one):**
- **Recommended: Ken Burns pan/zoom in MoviePy.** Animate the static images instead of using a video diffusion model. Faster, far more reliable, easier to debug, and still produces a genuine "reel." Do this first — always have this as your guaranteed fallback.
- **Video diffusion models** (Stable Video Diffusion, Wan2.1, LTX-Video, CogVideoX, HunyuanVideo — heaviest to lightest is roughly LTX/Wan < SVD < CogVideoX < HunyuanVideo): only attempt if the rest of the pipeline is already working end-to-end and you have spare time/GPU. Treat as a stretch goal, not the base plan.
- **Text-to-video APIs** (Veo, Kling, Hailuo, Runway): highest quality, but expensive, rate-limited, slower, and harder to control precisely. Only use if you already have access/budget and want a "wow" scene or two, not as the primary pipeline.

### Stage 8 — Voice Generation
**Do:** Convert each scene's narration into a `voice.wav`.

**Options (pick one):**
- **ElevenLabs** — best quality, use if budget allows; the quality gap over open-source is noticeable.
- **Kokoro TTS** — strong open-source option, good default if no budget for ElevenLabs.
- **Piper** — lighter-weight open-source alternative to Kokoro.
- **Coqui XTTS** — open-source, supports voice cloning if that becomes a feature.

### Stage 9 — Subtitle Generation
**Do:** Skip speech-to-text entirely — reuse the narration text you already generated, with timestamps derived from each scene's `duration` field. Output `subtitle.srt` using `pysrt`. Burn subtitles into the video during assembly (MoviePy or FFmpeg).

### Stage 10 — Background Music
**Options (pick one):**
- **Royalty-free library** (e.g. Pixabay) — simplest, safest, recommended default.
- **AI-generated music** (Suno/Udio) — only if licensing/permission is confirmed for your use case.
- **Local MP3** — fine for a quick demo, not for anything distributed.

In all cases: auto-duck/reduce music volume under narration.

### Stage 11 — Video Assembly
**Do:** Combine images/clips → voice → music → subtitles → transitions → export, in that order, into `output.mp4`.
Libraries: `MoviePy`, `FFmpeg`, `OpenCV` (OpenCV optional, mainly if you need custom frame-level effects).

---

## 3. Tech Stack (single recommended choice per row)

| Component | Recommendation | Alternative |
|---|---|---|
| Agent orchestration | LangGraph | — |
| LLM | Gemini Flash | Llama 3 / Qwen 3 Instruct / Mistral (if you want to stay fully open-source) |
| Image generation | FLUX.1-dev | SDXL via Diffusers |
| Motion | MoviePy pan/zoom (Ken Burns) | LTX-Video / Stable Video Diffusion (stretch only) |
| Voice | ElevenLabs | Kokoro TTS / Piper |
| Video editing | MoviePy + FFmpeg | — |
| Subtitles | pysrt + FFmpeg burn-in | — |
| Backend | FastAPI | — |
| Frontend | Streamlit | — |

---

## 4. Project Structure

```
reel-ai/
├── agents/
│     prompt_refiner.py
│     screenplay.py
│     planner.py
│     visual_director.py
├── services/
│     gemini.py
│     image_generator.py
│     tts.py
│     video_builder.py
├── workflows/
│     graph.py
├── assets/
│     images/
│     audio/
│     music/
├── output/
│     reels/
└── app.py
```

---

## 5. Caching

Don't call the LLM or regenerate media unnecessarily. Cache:
- Enhanced/refined prompt
- Screenplay
- Scene JSON
- Image prompts
- Generated images
- Voice files

Rule of thumb: if the user only changes background music, nothing upstream (screenplay, images, voice) should regenerate.

---

## 6. Making It "Agentic" (not just a prompt chain)

Give each pipeline stage a distinct agent identity with a single responsibility, even if several share the same underlying LLM call:

- **Prompt Refiner Agent** — improves/expands the user's raw prompt.
- **Screenplay Agent** — writes narration and scene structure.
- **Scene Planner Agent** — converts screenplay into structured JSON.
- **Visual Director Agent** — turns each scene's visual into a detailed image prompt.
- **Voice Director Agent** *(optional)* — picks voice characteristics (male/female, energetic/calm/emotional) per scene or per reel.

**Optional add-on: Reviewer/Quality-Control Agent** — checks narration length, hook strength, CTA presence, pacing, and scene timing against the target duration; if weak, triggers a rewrite of the screenplay rather than proceeding. This adds a genuine feedback loop but also adds latency — include only if there's slack.

Skip as separate agents (fold into the above instead, to avoid unnecessary round-trips): a standalone Research Agent, a standalone Prompt Optimizer Agent, and a standalone Quality Control Agent — their functions can live inside the Refiner/Planner/Visual Director prompts unless you specifically want the extra reasoning step as a visible pipeline stage for demo purposes.

---

## 7. Reliability & Production Features

- **Automatic retries** on generation failures (image, voice).
- **Model fallback** — e.g. try FLUX.1-dev first, fall back to SDXL if it fails or hardware is insufficient.
- **Parallel generation** of images and audio per scene, to cut total runtime.
- **Checkpointing** — allow the workflow to resume from the last completed stage instead of restarting.
- **Progress updates** surfaced to the UI ("Writing screenplay...", "Generating scene 3...").
- **Agent reasoning logs** — show each stage's output to the user for transparency and debugging.

---

## 8. Frontend

Minimum viable UI (Streamlit is sufficient — don't overbuild):
- Inputs: prompt text box, style dropdown (motivational / educational / cinematic / documentary), duration dropdown (15 / 30 / 60 sec), platform dropdown, voice dropdown (male/female).
- `[ Generate Reel ]` button.
- Live progress checklist (Prompt refined ✓ / Script generated ✓ / Images generated ✓ / Voice generated ✓ / Generating video...).
- Preview player + Download MP4 button.

A polished, working demo UI matters as much as pipeline quality for how the project is received.

---

## 9. Stretch Features (only if core pipeline is solid and stable)

- Automatic B-roll search (copyright-free stock) as an alternative to AI generation for certain scenes.
- Multiple output aspect ratios (9:16, 16:9, 1:1).
- Scene regeneration — let the user replace a single weak scene without regenerating the whole reel.
- Brand/style presets (educational, cinematic, motivational, corporate).
- Export project JSON so a reel can be re-edited later without regenerating everything from scratch.

---

## 10. Positioning for the Demo

Frame this as an **AI Creative Studio**, not just "prompt → video":

```
User Prompt → Creative Director AI → Script Writer AI → Storyboard Artist AI
→ Visual Director AI → Narration Director AI → Video Editor AI → Quality Control AI → Final Reel
```

Even though several of these agents share the same underlying LLM, giving each a clear name and responsibility demonstrates genuine agent-based design rather than a single monolithic prompt — this is the story to tell in the presentation.