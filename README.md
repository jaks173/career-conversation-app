---
title: Akshay Career Conversation AI
emoji: 💼
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: "4.44.0"
app_file: app.py
pinned: false
---

# Akshay Career Conversation AI

Personal career conversation assistant powered by OpenAI. It answers questions about my background, experience, projects, and interests using resume, LinkedIn export, summary, and project data in `me/`.

**Stack:** Python, Gradio, OpenAI (`gpt-4o-mini`), optional Pushover notifications.

## Run locally

```bash
cd workspace/career-conversation-app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add OPENAI_API_KEY
./run.sh
```

Gradio opens on a free port (or set `PORT=7860` in `.env`).

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENAI_API_KEY` | Yes | OpenAI API access |
| `PUSHOVER_TOKEN`, `PUSHOVER_USER` | No | Alerts for leads and urgent unknown questions |
| `PORT` | No | Gradio port (default: random free port) |
| `DEBUG` | No | Set to `1` for verbose message logging |

## `me/` folder

Populate on a fresh clone (not all files are in git):

| File | Purpose |
|------|---------|
| `resume.pdf` | Resume text for context |
| `linkedin.pdf` | LinkedIn export |
| `summary.txt` | Short professional summary |
| `projects.json` | Project list (`name`, `desc`, `link`) |
| `avatar.jpg` | Header avatar |

Sync from job-agent (optional):

```bash
python scripts/sync_context_from_job_agent.py
```

## Deploy (Hugging Face Spaces)

1. Create a Gradio Space and connect this repo (or upload files).
2. Set Space secrets: `OPENAI_API_KEY`, optional Pushover vars.
3. Ensure `me/` assets are present on the Space (upload or sync script).

## Tools

- `record_user_details` — records visitor email (Pushover alert)
- `record_unknown_question` — logs questions outside available context

Unknown questions are appended to `unknown_questions.log` (gitignored).
