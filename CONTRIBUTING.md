# Contributing to Script2Reel

Thank you for your interest in contributing.

The project is intentionally designed to be modular so contributors can add new providers or workflow components without modifying the existing architecture.

---

# Development Setup

Clone the repository.

```bash
git clone ...

cd Script2Reel
```

Create a virtual environment.

```bash
python -m venv .venv

source .venv/bin/activate
```

Install dependencies.

```bash
pip install -r requirements.txt
```

Run the application.

```bash
streamlit run app.py
```

---

# Project Structure

```
services/

workflows/

prompts/

ui/

assets/
```

---

# Adding a New LLM Provider

Create a provider implementation.

Example

```python
class ClaudeProvider(LLMProvider):
    ...
```

Register it.

```python
registry.register(
    "llm",
    "claude",
    lambda: ClaudeProvider()
)
```

Update configuration if required.

No workflow changes are necessary.

---

# Adding an Image Provider

Implement

```python
class FluxProvider(ImageProvider):
```

Register

```python
registry.register(
    "image",
    "flux",
    lambda: FluxProvider()
)
```

Done.

---

# Adding a Voice Provider

Implement

```python
class KokoroProvider(VoiceProvider):
```

Register it.

No workflow changes required.

---

# Adding a Video Provider

Implement

```python
class WanProvider(VideoProvider):
```

Register it.

Done.

---

# Adding a New Agent

Create the new agent function.

Register it inside the LangGraph workflow.

Connect it using edges.

Keep each agent focused on a single responsibility.

---

# Coding Guidelines

- Keep agents independent.
- Avoid provider-specific logic inside workflow nodes.
- Register providers instead of modifying factory code.
- Preserve structured outputs whenever possible.
- Record telemetry for long-running operations.

---

# Pull Requests

Before opening a pull request

- Run the application
- Verify the workflow
- Update documentation if required

---

# Future Contributions

Areas where contributions are especially welcome:

- Image-to-video providers
- New LLM providers
- New TTS providers
- Additional telemetry
- UI improvements
- Prompt engineering
- Performance optimisations
- Automated benchmarking

---

# Philosophy

Script2Reel is intended to be a reusable AI orchestration framework rather than a project tied to a single AI model.

Contributions should preserve this modular philosophy whenever possible.