#!/usr/bin/env python3
"""Generate me/summary.txt and me/projects.json from job-agent resume_master.yaml."""
from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Install PyYAML: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
JOB_AGENT_YAML = ROOT.parent / "job-agent" / "data" / "resume_master.yaml"
ME_DIR = ROOT / "me"


def main() -> None:
    if not JOB_AGENT_YAML.is_file():
        print(f"Not found: {JOB_AGENT_YAML}", file=sys.stderr)
        sys.exit(1)

    data = yaml.safe_load(JOB_AGENT_YAML.read_text(encoding="utf-8")) or {}
    ME_DIR.mkdir(parents=True, exist_ok=True)

    summary_parts = []
    for key in ("professional_summary", "role_narrative", "recent_focus"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            summary_parts.append(val.strip())
        elif isinstance(val, list):
            summary_parts.append("\n".join(f"- {item}" for item in val if item))

    summary_path = ME_DIR / "summary.txt"
    summary_path.write_text("\n\n".join(summary_parts).strip() + "\n", encoding="utf-8")
    print(f"Wrote {summary_path}")

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

    projects_path = ME_DIR / "projects.json"
    projects_path.write_text(
        json.dumps(projects_out, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {projects_path} ({len(projects_out)} projects)")


if __name__ == "__main__":
    main()
