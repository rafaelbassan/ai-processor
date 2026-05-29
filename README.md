# VectoSports AI Processor

Part of the [VectoSports](https://vectosports.com) platform — AI-powered biomechanical analysis for athletes.

## What it does

This service receives athlete video and pose data, runs it through a multi-agent AI pipeline built on **Google ADK + Gemini**, and returns structured biomechanical analysis reports. It is consumed by the VectoSports backend via RabbitMQ / Google Pub-Sub.

```
Incoming job (RabbitMQ)
        │
        ▼
  Root Agent (Gemini)
        │
   ┌────┴─────────────────────┐
   │                          │
Swimming Workflow       Running Workflow       Generic Workflow
   │                          │
Analyst → Reviewer → Coach  Analyst → Reviewer → Coach
```

Each workflow is a `SequentialAgent` chain:
1. **Analyst** — reads video frames and pose JSON, produces raw biomechanical observations
2. **Reviewer** — validates and formats the report
3. **Coach** — generates actionable tips for the athlete

Additional specialists: Performance Analyst, Nutritionist, Comparison Agent.

## Stack

| Layer | Technology |
|---|---|
| AI framework | [Google ADK](https://google.github.io/adk-docs/) |
| LLM | Gemini (via Vertex AI or API key) |
| API server | FastAPI + Uvicorn |
| Message queue | RabbitMQ |
| Storage | Google Cloud Storage |
| Runtime | Docker / Google Cloud Run |

## Setup

```bash
cp .env.example .env
# Fill in the required values in .env
```

```bash
# Docker
docker compose up

# Local
pip install -r api/requirements.txt
python api/worker.py
```

See [`.env.example`](.env.example) for all configuration options.

## Part of VectoSports

[vectosports.com](https://vectosports.com) uses computer vision and AI to help coaches and athletes improve technique through detailed biomechanical feedback.

This repository contains the AI processing backend. Other components (pose estimation, mobile app, dashboard) are maintained separately.
