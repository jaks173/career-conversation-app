---
title: Akshay Career Conversation AI
emoji: 💼
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: "4.36.1"
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
| `summary.txt` | Short professional summary (from `resume_master.yaml`) |
| `knowledge_base.md` | Up-to-date facts from job-agent `data/knowledge_base.md` |
| `experience.txt` | Experience highlights from `resume_master.yaml` |
| `projects.json` | Project list (`name`, `desc`, `link`) |
| `avatar.jpg` | Header avatar |

**Keep context fresh** (run after updating job-agent):

```bash
source .venv/bin/activate
python scripts/sync_context_from_job_agent.py
```

## Deploy (Hugging Face Spaces)

Space: https://huggingface.co/spaces/jakshay/career-chat

1. Connect this repo to the Space (or push to `main`).
2. **Required secret:** Settings → Repository secrets → `OPENAI_API_KEY` = your OpenAI key.
3. `sdk_version` in this README must match `gradio==4.36.1` in `requirements.txt` (do not use 4.44).
4. After pushing fixes, use **Factory reboot** on the Space if the UI still shows Error.
5. Optional secrets: `PUSHOVER_TOKEN`, `PUSHOVER_USER`.

## Tools

- `record_user_details` — records visitor email (Pushover alert)
- `record_unknown_question` — logs questions outside available context

Unknown questions are appended to `unknown_questions.log` (gitignored).
