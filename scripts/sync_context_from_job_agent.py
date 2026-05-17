#!/usr/bin/env python3
"""Sync career bot context from job-agent (resume_master.yaml + knowledge_base.md)."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Install PyYAML: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
JOB_AGENT = ROOT.parent / "job-agent"
JOB_AGENT_YAML = JOB_AGENT / "data" / "resume_master.yaml"
JOB_AGENT_KB = JOB_AGENT / "data" / "knowledge_base.md"
ME_DIR = ROOT / "me"


def _write_summary(data: dict) -> None:
    summary_parts = []
    personal = data.get("personal_information") or {}
    if isinstance(personal, dict):
        name = f"{personal.get('name', '')} {personal.get('surname', '')}".strip()
        loc = ", ".join(
            x for x in (personal.get("city"), personal.get("country")) if x
        )
        if name or loc:
            summary_parts.append(f"Name: {name}\nLocation: {loc}".strip())

    for key in ("professional_summary", "role_narrative", "recent_focus"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            summary_parts.append(val.strip())
        elif isinstance(val, list):
            summary_parts.append("\n".join(f"- {item}" for item in val if item))

    skills = data.get("skills") or {}
    if isinstance(skills, dict) and skills:
        lines = ["KEY SKILLS:"]
        for group, items in skills.items():
            if isinstance(items, list) and items:
                label = str(group).replace("_", " ").title()
                lines.append(f"  {label}: {', '.join(str(i) for i in items[:12])}")
        summary_parts.append("\n".join(lines))

    (ME_DIR / "summary.txt").write_text(
        "\n\n".join(summary_parts).strip() + "\n", encoding="utf-8"
    )


def _write_projects(data: dict) -> None:
    projects_out = []
    for p in data.get("projects") or []:
        if not isinstance(p, dict):
            continue
        name = (p.get("name") or "").strip()
        if not name:
            continue
        desc = (p.get("description") or p.get("desc") or "").strip()
        link = (p.get("link") or "").strip()
        projects_out.append({"name": name, "desc": desc, "link": link})

    (ME_DIR / "projects.json").write_text(
        json.dumps(projects_out, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"  projects.json ({len(projects_out)} projects)")


def _write_experience(data: dict) -> None:
    lines = ["EXPERIENCE (from resume_master.yaml):\n"]
    for job in data.get("experience_details") or []:
        if not isinstance(job, dict):
            continue
        pos = job.get("position", "")
        company = job.get("company", "")
        period = job.get("employment_period", "")
        lines.append(f"- {pos} @ {company} ({period})")
        highlights = job.get("key_achievements") or job.get("highlights") or []
        if isinstance(highlights, list):
            for h in highlights[:6]:
                if h:
                    lines.append(f"    • {h}")
        streams = job.get("work_streams")
        if isinstance(streams, dict):
            for k, v in list(streams.items())[:4]:
                if isinstance(v, dict) and v.get("description"):
                    lines.append(f"    • {k}: {v['description'][:200]}")
    (ME_DIR / "experience.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    if not JOB_AGENT_YAML.is_file():
        print(f"Not found: {JOB_AGENT_YAML}", file=sys.stderr)
        sys.exit(1)

    ME_DIR.mkdir(parents=True, exist_ok=True)
    data = yaml.safe_load(JOB_AGENT_YAML.read_text(encoding="utf-8")) or {}

    _write_summary(data)
    print("  summary.txt")
    _write_projects(data)
    _write_experience(data)
    print("  experience.txt")

    if JOB_AGENT_KB.is_file():
        shutil.copy2(JOB_AGENT_KB, ME_DIR / "knowledge_base.md")
        print("  knowledge_base.md (from job-agent)")
    else:
        print("  (skipped knowledge_base.md — not found in job-agent)", file=sys.stderr)

    print("Done. Restart the career app to load new context.")


if __name__ == "__main__":
    main()
