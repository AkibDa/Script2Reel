<div align="center">

# 🎬 Script2Reel

### A Provider-Agnostic Multi-Agent AI Framework for Short-Form Video Generation

Transform a single prompt into a fully narrated short-form video using specialized AI agents, interchangeable AI providers, and an extensible workflow.

---

**Built with**

LangGraph • Streamlit • Python • Gemini • OpenAI • Stable Diffusion XL • ElevenLabs • Edge-TTS

</div>

---

# Overview

Script2Reel is an AI-powered content generation framework that automatically converts a single text prompt into a narrated short-form video suitable for Instagram Reels, YouTube Shorts, or TikTok.

Unlike traditional text-to-video systems that rely on one large prompt, Script2Reel decomposes the problem into multiple specialized AI agents.

Each agent has a single responsibility:

- understand the prompt
- write the screenplay
- plan scenes
- review consistency
- generate visual prompts
- generate images
- generate narration
- assemble the final video

This modular workflow makes the system easier to improve, debug and extend.

---

# Features

## Multi-Agent Workflow

- Intent Classification
- Creative Director
- Educational Writer
- Screenwriter
- Scene Planner
- Consistency Reviewer
- Subject Extractor
- Visual Director
- Image Generation
- Voice Generation
- Video Assembly

---

## Provider Agnostic

Supports interchangeable AI providers.

Current implementations:

| Category | Providers |
|----------|-----------|
| LLM | Gemini, OpenAI |
| Image | Local SDXL, OpenAI, Mock |
| Voice | ElevenLabs, Edge-TTS |
| Video | Local, Mock |

The workflow is completely independent of the underlying provider.

---

## Intelligent Infrastructure

- Provider Registry
- Automatic Provider Discovery
- Automatic Provider Selection
- Automatic Fallback
- Provider Capability Metadata
- Startup Health Checks
- Runtime Telemetry
- Benchmark Recommendations

---

# Workflow

```
User Prompt
      │
      ▼
Intent Classification
      │
      ▼
Creative / Educational Route
      │
      ▼
Screenwriter
      │
      ▼
Scene Planner
      │
      ▼
Consistency Review
      │
      ▼
Subject Extraction
      │
      ▼
Visual Director
      │
      ▼
Image Generation
      │
      ▼
Voice Generation
      │
      ▼
Video Assembly
      │
      ▼
Final MP4
```

---

# Architecture

```
                 LangGraph Workflow
                         │
                         ▼
              AI Agent Pipeline
                         │
                         ▼
               Provider Abstraction
        ┌────────┬────────┬────────┬────────┐
        │  LLM   │ Image  │ Voice  │ Video  │
        └────────┴────────┴────────┴────────┘
                         │
                         ▼
            Local or Cloud AI Providers
```

---

# Why this architecture?

Instead of tightly coupling the workflow to one model provider, Script2Reel separates:

- workflow orchestration
- AI providers
- rendering
- configuration

This allows providers to be swapped without modifying the workflow itself.

---

# Screenshots

## 🚀 Landing Page

The application starts with a simple interface where users can create AI-generated reels from a single prompt.

![Landing Page](demo_image/landing.png)

## ✍️ Reel Configuration

Users can configure the prompt, duration, style, platform, voice, and generation mode.

![Create Reel](demo_image/create-reel.png)

## 🤖 Multi-Agent Workflow

During generation, every AI agent executes independently.

The progress tracker exposes each stage of the pipeline.

![Generation Progress](demo_image/progress.png)

## 🎬 Final Reel

The generated reel can be previewed, downloaded, and inspected.

![Final Reel](demo_image/result.png)

---

# Quick Start

## Clone

```bash
git clone https://github.com/AkibDa/Script2Reel.git

cd Script2Reel
```

## Install

```bash
python -m venv .venv

source .venv/bin/activate

pip install -r requirements.txt
```

---

## Environment Variables

```env
GOOGLE_API_KEY=

OPENAI_API_KEY=

ELEVENLABS_API_KEY=

FLUX_API_KEY=

OLLAMA_HOST=
```

Only configure the providers you intend to use.

---

## Run

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

---

# Documentation

- 📖 ARCHITECTURE.md
- 🤝 CONTRIBUTING.md

---

# Roadmap

- Image-to-video generation
- Temporal scene animation
- Kokoro TTS
- FLUX support
- Wan2.1 support
- Veo support
- Additional provider implementations
- Scene editing interface

---

# License

MIT License