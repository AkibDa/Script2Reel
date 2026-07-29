# Script2Reel Architecture

This document explains how Script2Reel is designed internally.

---

# Design Goals

The project was built around five principles.

1. Separation of Responsibilities

Each AI agent performs one specific task.

2. Extensibility

New AI providers can be added without modifying the workflow.

3. Reliability

Fallback providers prevent complete pipeline failures.

4. Observability

Telemetry records execution times and provider usage.

5. Local + Cloud Compatibility

The framework should work with local models, cloud APIs, or a combination of both.

---

# High-Level Architecture

```
                        User
                          │
                          ▼
                    Streamlit UI
                          │
                          ▼
                  LangGraph Workflow
                          │
      ┌───────────────────┴────────────────────┐
      ▼                                        ▼
 Creative Route                         Educational Route
      │                                        │
      └───────────────────┬────────────────────┘
                          ▼
                    Scene Planning
                          ▼
                 Consistency Review
                          ▼
                  Subject Extraction
                          ▼
                   Visual Direction
                          ▼
                  Provider Layer
                          ▼
      ┌──────────┬──────────┬──────────┬──────────┐
      │   LLM    │  Image   │  Voice   │  Video   │
      └──────────┴──────────┴──────────┴──────────┘
                          ▼
                   Video Builder
                          ▼
                     Final Reel
```

---

# AI Agent Pipeline

## Intent Classifier

Determines whether the user's request should follow an educational or creative workflow.

---

## Creative Director

Produces a creative brief including:

- analogy
- setting
- visual style
- originality

---

## Educational Writer

Creates a factual educational script.

---

## Screenwriter

Generates the screenplay used by later stages.

---

## Scene Planner

Splits the screenplay into multiple scenes.

Each scene contains

- narration
- duration
- visual description
- camera effect

---

## Consistency Reviewer

Verifies that generated scenes remain faithful to the original creative brief.

If inconsistencies are detected, feedback is returned for revision.

---

## Subject Extractor

Extracts structured visual entities from every scene.

Example

- subject
- action
- setting
- emotion

---

## Visual Director

Transforms structured scene data into image prompts.

The prompts also include

- inference steps
- CFG scale
- negative prompts
- random seed

---

## Image Generation

Creates scene artwork using the selected image provider.

Production mode generates multiple candidates.

An image critic selects the best candidate.

---

## Voice Generation

Produces narration using the selected voice provider.

---

## Video Builder

Combines

- images/videos
- narration
- subtitles
- transitions
- background music

into the final MP4.

---

# Provider Architecture

The workflow never communicates directly with external APIs.

Instead every interaction passes through provider interfaces.

```
Workflow

↓

Provider

↓

Implementation

↓

Model/API
```

Examples

LLM

- Gemini
- OpenAI

Image

- Local SDXL
- OpenAI

Voice

- ElevenLabs
- Edge-TTS

Video

- Local
- Mock

---

# Provider Registry

Each provider registers itself automatically.

```
registry.register(
    kind,
    provider_name,
    factory
)
```

The workflow never imports provider implementations directly.

---

# Provider Capabilities

Each provider exposes metadata describing its abilities.

Example

- supports_json
- supports_video
- supports_seed
- supports_streaming
- max_resolution

This allows future workflow decisions based on provider features rather than provider names.

---

# Automatic Fallback

If a provider fails during execution,

```
Primary

↓

Failure

↓

Fallback

↓

Fallback

↓

Success
```

The workflow continues automatically.

---

# Configuration

Provider selection is controlled through environment variables.

Overrides are also supported.

---

# Telemetry

Every execution records

- stage durations
- providers used
- runtime metadata

This information is written to

```
telemetry.json
```

for later analysis.

---

# Future Work

The architecture has been intentionally designed to support future additions including:

- Image-to-video generation
- Multi-language narration
- Additional cloud providers
- Additional local providers
- Temporal animation
- Cloud deployment