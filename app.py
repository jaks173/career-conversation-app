# app.py - Final fixes (history normalization + tool-call formatting + avatar prompt)
from dotenv import load_dotenv
from openai import OpenAI
import json
import os
import re
import requests
from pypdf import PdfReader
import gradio as gr
import gradio_client.utils as _gradio_client_utils

_orig_json_schema_to_python_type = _gradio_client_utils._json_schema_to_python_type

def _safe_json_schema_to_python_type(schema, defs):
    if not isinstance(schema, dict):
        return "Any"
    return _orig_json_schema_to_python_type(schema, defs)

_gradio_client_utils._json_schema_to_python_type = _safe_json_schema_to_python_type

import socket
import ast
import pathlib
from datetime import datetime

load_dotenv(override=True)

DEBUG = os.getenv("DEBUG", "").strip().lower() in ("1", "true", "yes")

def _require_openai_key():
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return key

# ---------- Pushover ----------
def push(text):
    token = os.getenv("PUSHOVER_TOKEN")
    user = os.getenv("PUSHOVER_USER")
    if not token or not user:
        print("Pushover not configured; skipping push.")
        return
    try:
        requests.post(
            "https://api.pushover.net/1/messages.json",
            data={"token": token, "user": user, "message": text},
            timeout=5,
        )
    except Exception as e:
        print("Pushover error:", e, flush=True)

# ---------- Tools ----------
def record_user_details(email, name="Name not provided", notes="not provided"):
    push(f"[Lead] Name: {name} | Email: {email} | Notes: {notes}")
    return {"recorded": "ok"}

UNKNOWN_LOG = pathlib.Path("unknown_questions.log")
def record_unknown_question(question):
    q = (question or "").strip()
    try:
        # Use timezone-aware in future; this is fine for logs now
        with UNKNOWN_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.utcnow().isoformat()} {q}\n")
    except Exception as e:
        print("Failed to write unknown question log:", e, flush=True)
    lower = q.lower()
    urgent_keywords = ["contact", "email", "reach", "urgent", "hire", "interview", "connect", "follow up", "follow-up", "reach out"]
    if any(k in lower for k in urgent_keywords) or len(q) > 200:
        push(f"[Unknown question needing follow-up] {q}")
        return {"recorded": "ok", "notified": True}
    else:
        return {"recorded": "ok", "notified": False}

record_user_details_json = {
    "name": "record_user_details",
    "description": "Use this tool to record that a user is interested in being in touch and provided an email address",
    "parameters": {
        "type": "object",
        "properties": {
            "email": {"type": "string"},
            "name": {"type": "string"},
            "notes": {"type": "string"}
        },
        "required": ["email"],
        "additionalProperties": False
    }
}

record_unknown_question_json = {
    "name": "record_unknown_question",
    "description": "Always use this tool to record any question that couldn't be answered",
    "parameters": {
        "type": "object",
        "properties": {
            "question": {"type": "string"}
        },
        "required": ["question"],
        "additionalProperties": False
    }
}

tools = [{"type": "function", "function": record_user_details_json},
         {"type": "function", "function": record_unknown_question_json}]

# ---------- Helpers ----------
EMAIL_RE = re.compile(r"[^@ \t\r\n]+@[^@ \t\r\n]+\.[^@ \t\r\n]+")
def is_email(text: str) -> bool:
    return bool(EMAIL_RE.search(text or ""))

def normalize(text: str) -> str:
    return (text or "").lower().strip()

def find_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port

# Robust normalizer for assistant / UI content (flattens nested structures)
def normalize_assistant_reply(reply):
    if reply is None:
        return ""
    # string: parse JSON or python literal if structured
    if isinstance(reply, str):
        s = reply.strip()
        if s.startswith("{") or s.startswith("["):
            try:
                parsed = json.loads(s)
                return normalize_assistant_reply(parsed)
            except Exception:
                pass
        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, (list, dict)):
                return normalize_assistant_reply(parsed)
        except Exception:
            pass
        return s
    # dict: prefer common text keys
    if isinstance(reply, dict):
        for key in ("text", "content", "message", "body", "answer"):
            if key in reply and reply[key] not in (None, ""):
                return normalize_assistant_reply(reply[key])
        # try nested values
        for k, v in reply.items():
            if isinstance(v, (dict, list)):
                return normalize_assistant_reply(v)
            if isinstance(v, str) and (v.strip().startswith("[") or v.strip().startswith("{")):
                try:
                    parsed = json.loads(v)
                    return normalize_assistant_reply(parsed)
                except Exception:
                    try:
                        parsed = ast.literal_eval(v)
                        return normalize_assistant_reply(parsed)
                    except Exception:
                        pass
        pieces = []
        for k, v in reply.items():
            pieces.append(f"{k}: {normalize_assistant_reply(v)}")
        return "\n".join(pieces)
    # list/tuple: flatten
    if isinstance(reply, (list, tuple)):
        parts = []
        for item in reply:
            parts.append(normalize_assistant_reply(item))
        return "\n\n".join([p for p in parts if p and p.strip()])
    # fallback
    try:
        return str(reply)
    except Exception:
        return json.dumps(reply, ensure_ascii=False, default=str)

# Sanitize messages to send to OpenAI
def _to_openai_messages(system_prompt, history, user_message):
    raw = [{"role": "system", "content": system_prompt}]
    if history:
        # history may be list-of-dicts or list-of-(user,assistant)
        if isinstance(history, list) and len(history) > 0 and isinstance(history[0], dict):
            for i, m in enumerate(history):
                if isinstance(m, dict) and "role" in m and "content" in m:
                    # ensure content is a plain string
                    content = normalize_assistant_reply(m.get("content", ""))
                    raw.append({"role": str(m["role"]), "content": content})
                else:
                    print(f"WARNING: history entry at index {i} is not a valid dict: {repr(m)}", flush=True)
        else:
            for i, pair in enumerate(history):
                if not isinstance(pair, (list, tuple)):
                    print(f"WARNING: history entry at index {i} is not a tuple/list: {repr(pair)}", flush=True)
                    continue
                user_msg = pair[0] if len(pair) > 0 else None
                bot_msg = pair[1] if len(pair) > 1 else None
                if user_msg is not None:
                    raw.append({"role": "user", "content": str(user_msg)})
                if bot_msg is not None:
                    raw.append({"role": "assistant", "content": normalize_assistant_reply(bot_msg)})
    raw.append({"role": "user", "content": str(user_message)})

    sanitized = []
    bad = []
    for idx, item in enumerate(raw):
        if isinstance(item, dict) and "role" in item and "content" in item and isinstance(item["role"], str) and isinstance(item["content"], str):
            sanitized.append({"role": item["role"], "content": item["content"]})
            continue
        bad.append((idx, repr(item)))

    if bad:
        print("=== WARNING: Found invalid entries in message list; these will be skipped ===", flush=True)
        for idx, repr_bad in bad:
            print(f"Index {idx}: {repr_bad}", flush=True)
        print("=== End invalid entries ===", flush=True)

    if DEBUG:
        print("=== DEBUG: sanitized messages to be sent to OpenAI ===", flush=True)
        for i, m in enumerate(sanitized):
            preview = m["content"][:140].replace("\n", " ")
            print(f"{i}: role={m['role']} content_preview={preview!r}", flush=True)
        print("=== END DEBUG ===", flush=True)

    return sanitized

# Project lookup
def find_project_by_query(projects, query):
    if not projects:
        return None
    q = normalize(query)
    tokens = set(re.findall(r"\w+", q))
    if not q:
        return None
    for p in projects:
        name = normalize(p.get("name", ""))
        if name and q in name:
            return p
    best = None
    best_score = 0
    for p in projects:
        name = normalize(p.get("name", ""))
        desc = normalize(p.get("desc", "") or "")
        text = name + " " + desc
        text_tokens = set(re.findall(r"\w+", text))
        if not text_tokens:
            continue
        overlap = len(tokens & text_tokens)
        if overlap > best_score:
            best_score = overlap
            best = p
    if best_score > 0:
        return best
    for p in projects:
        desc = normalize(p.get("desc", "") or "")
        if q in desc:
            return p
    return None

# ---------- Agent (Akshay) ----------
class Me:
    def __init__(self):
        self.openai = OpenAI(api_key=_require_openai_key())
        self.name = "Akshay"
        self.linkedin = ""
        self.resume_text = ""
        self.projects = []
        self.summary = ""

        # load files if present
        try:
            reader = PdfReader("me/linkedin.pdf")
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    self.linkedin += text + "\n"
        except Exception:
            pass
        try:
            reader = PdfReader("me/resume.pdf")
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    self.resume_text += text + "\n"
        except Exception:
            pass
        try:
            with open("me/summary.txt", "r", encoding="utf-8") as f:
                self.summary = f.read()
        except Exception:
            self.summary = ""
        try:
            projects_raw = open("me/projects.json", "r", encoding="utf-8").read()
            self.projects = json.loads(projects_raw)
        except Exception:
            self.projects = []

        # system prompt: explicit avatar instruction
        context_parts = []
        if self.summary:
            context_parts.append("SUMMARY:\n" + self.summary)
        if self.linkedin:
            context_parts.append("LINKEDIN:\n" + self.linkedin)
        if self.resume_text:
            context_parts.append("RESUME:\n" + self.resume_text)
        if self.projects:
            try:
                projects_preview = json.dumps(self.projects, indent=2)
            except Exception:
                projects_preview = str(self.projects)
            context_parts.append("PROJECTS:\n" + projects_preview)

        context = "\n\n".join(context_parts)
        if len(context) > 10000:
            context = context[:10000] + "\n\n[[TRUNCATED]]"

        # Explicit avatar instruction as requested
        self.system_prompt_text = (
            f"You are Akshay's avatar assistant. Answer as the avatar in first-person on behalf of Akshay. "
            "Use only the provided resources (LinkedIn export, resume text, summary, and projects.json) to answer questions about Akshay's career, projects, skills and experience. "
            "For any question you cannot answer from these resources, do NOT guess — call the record_unknown_question tool (or say you don't know and offer to collect an email). "
            "\n\nCONTEXT:\n" + context
        )

    def handle_tool_call(self, tool_calls):
        """
        Execute tool calls. When an argument value points to a local file path,
        add 'url' key with that path. Return messages as assistant entries (not role 'tool').
        """
        results = []
        for tool_call in tool_calls:
            tool_name = getattr(tool_call.function, "name", None)
            raw_args_json = getattr(tool_call.function, "arguments", "{}")
            try:
                arguments = json.loads(raw_args_json)
            except Exception:
                arguments = {}

            print(f"Tool called: {tool_name} with raw args: {arguments}", flush=True)

            # Add 'url' for any local path arg per your developer instruction
            for k, v in list(arguments.items()):
                if isinstance(v, str) and os.path.exists(v):
                    arguments["url"] = v
                    print(f"Added 'url' field for tool '{tool_name}': {v}", flush=True)

            tool = globals().get(tool_name)
            try:
                result = tool(**arguments) if callable(tool) else {}
            except Exception as e:
                result = {"error": str(e)}

            # Return as assistant-style message so it's valid in messages list
            results.append({"role": "assistant", "content": json.dumps(result)})
        return results

    def system_prompt(self):
        return self.system_prompt_text

    def chat(self, message, history):
        mtext = (message or "").strip()
        low = normalize(mtext)

        # Personal questions (handle quickly)
        personal_patterns = [r"\bwho( are| r)? you\b", r"\bwhat (are|is) you\b", r"\bwhat can you do\b", r"\bwho am i talking to\b", r"\bintroduce yourself\b"]
        for pat in personal_patterns:
            if re.search(pat, low):
                return ("I am Akshay's avatar assistant — I can answer questions about Akshay's career, projects, skills and interests. "
                        "If you want a follow-up from Akshay please share your email and I'll record it.")

        # Email capture
        if is_email(message):
            email = EMAIL_RE.search(message).group(0)
            record_user_details(email=email)
            return f"Thanks — I’ve recorded your email ({email}). Akshay has been notified and will reach out soon."

        # Project-specific question
        project_keywords = ["project", "projects", "program", "course", "pm", "pm program", "upraised", "upraised pm"]
        asked_about_projects = any(k in low for k in project_keywords) or any((p.get("name","")).lower() in low for p in self.projects)
        if asked_about_projects:
            proj = find_project_by_query(self.projects, message)
            if proj:
                name = proj.get("name", "Project")
                desc = proj.get("desc", "No description available.")
                link = proj.get("link")
                reply = f"**{name}**\n\n{desc}\n"
                if link:
                    reply += f"\nLink: {link}\n"
                reply += "\nIf you'd like an introduction or to collaborate, share your email and I'll notify Akshay."
                return normalize_assistant_reply(reply)
            else:
                record_unknown_question(question=message)
                return ("I don't have details for that specific project in my records. "
                        "If you'd like, share your email and I will ask Akshay to follow up. "
                        "Would you like to give your email?")

        # Out-of-scope guardrail (no guessing)
        resources_text = "\n".join([self.summary, self.linkedin, self.resume_text])
        if not is_in_scope(message, resources_text, self.projects):
            record_unknown_question(question=message)
            return ("That question appears to be outside the scope of information I have about Akshay. "
                    "I don't want to guess or provide incorrect details. "
                    "If you'd like a direct follow-up from Akshay, please share your email and I'll ask him to get in touch. "
                    "Alternatively, you can ask about Akshay's career, projects, skills, or resume.")

        # Model flow (sanitized)
        messages = _to_openai_messages(self.system_prompt(), history, message)
        done = False
        assistant_final = ""
        while not done:
            response = self.openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=tools
            )
            choice = response.choices[0]
            finish_reason = getattr(choice, "finish_reason", None)

            if finish_reason == "tool_calls":
                message_obj = getattr(choice, "message", None)
                assistant_part = getattr(message_obj, "content", None)
                if isinstance(assistant_part, str) and assistant_part:
                    messages.append({"role": "assistant", "content": assistant_part})
                tool_calls = getattr(message_obj, "tool_calls", []) or []
                tool_result_messages = self.handle_tool_call(tool_calls)
                # tool_result_messages are assistant messages — append directly
                for tr in tool_result_messages:
                    if isinstance(tr, dict) and "role" in tr and "content" in tr:
                        messages.append({"role": tr["role"], "content": tr["content"]})
                    else:
                        messages.append({"role": "assistant", "content": json.dumps(tr)})
                # loop to allow model to respond after tool output
            else:
                # final assistant extraction
                try:
                    assistant_val = None
                    if hasattr(choice, "message") and getattr(choice, "message", None) is not None:
                        msg_obj = choice.message
                        if isinstance(msg_obj, dict):
                            assistant_val = msg_obj.get("content")
                        else:
                            assistant_val = getattr(msg_obj, "content", None)
                    if assistant_val is None:
                        assistant_val = str(choice)
                    if isinstance(assistant_val, (dict, list)):
                        try:
                            assistant_final = json.dumps(assistant_val, ensure_ascii=False)
                        except Exception:
                            assistant_final = str(assistant_val)
                    else:
                        assistant_final = str(assistant_val)
                except Exception:
                    assistant_final = str(choice)
                done = True

        assistant_final = normalize_assistant_reply(assistant_final)
        return assistant_final

# ---------- Scope detection helper ----------
def is_in_scope(query: str, resources_text: str, projects) -> bool:
    q = normalize(query)
    if not q:
        return False
    q_tokens = set(re.findall(r"\w+", q))
    for p in (projects or []):
        text = normalize(p.get("name", "") + " " + (p.get("desc") or ""))
        if not text:
            continue
        if any(tok in text for tok in q_tokens):
            return True
    res_text = normalize(resources_text or "")
    if not res_text:
        return False
    res_tokens = set(re.findall(r"\w+", res_text))
    if not res_tokens:
        return False
    overlap = len(q_tokens & res_tokens)
    if overlap >= 2:
        return True
    keywords = {"resume", "cv", "linkedin", "project", "projects", "experience", "role", "skills", "background", "education", "work", "job", "company"}
    if any(k in q_tokens for k in keywords):
        return True
    return False

# ---------- UI helpers ----------
# Normalize incoming history items so model never receives structured content
def _history_to_dict_list(hist):
    out = []
    if not hist:
        return out
    if isinstance(hist, list) and len(hist) > 0 and isinstance(hist[0], dict):
        for m in hist:
            try:
                role = str(m.get("role", "assistant"))
                content_raw = m.get("content", "")
                content = normalize_assistant_reply(content_raw)
                out.append({"role": role, "content": content})
            except Exception:
                continue
        return out
    # Convert tuple-history into dict-list
    for pair in hist:
        try:
            u = pair[0]
        except Exception:
            u = ""
        try:
            a = pair[1]
        except Exception:
            a = ""
        out.append({"role": "user", "content": str(u)})
        out.append({"role": "assistant", "content": normalize_assistant_reply(a)})
    return out

def respond_and_append(user_message, chat_history):
    if chat_history is None:
        chat_history = []
    history_as_dicts = _history_to_dict_list(chat_history)
    raw_reply = me.chat(user_message, history_as_dicts)
    reply_text = normalize_assistant_reply(raw_reply)
    chat_history = list(chat_history or [])
    chat_history.append((str(user_message), reply_text))
    return "", chat_history

# ---------- UI layout ----------
avatar_path = "me/avatar.jpg" if os.path.exists("me/avatar.jpg") else None

css = """
/* header layout */
.header-row { display:flex; align-items:center; gap:18px; padding:12px 8px; max-height:160px; }

/* avatar wrapper - remove Gradio card background and padding */
.avatar-circle {
  width:156px;
  height:156px;
  min-width:156px;
  display:flex;
  align-items:center;
  justify-content:center;
  background: transparent !important;
  box-shadow: none !important;
  padding: 0 !important;
  border-radius: 50% !important;
  overflow: visible !important;
}

/* image itself: slightly larger, circular, cover mode */
.avatar-circle img {
  width:156px !important;
  height:156px !important;
  object-fit:cover !important;
  border-radius:50% !important;
  border:3px solid rgba(230,230,230,0.95);
  display:block;
  margin: 0 !important;
  box-shadow: 0 2px 6px rgba(0,0,0,0.25);
}

/* in case Gradio wraps the image in a .gr-image element, make it transparent too */
.avatar-circle .gr-image, .avatar-circle .image {
  background: transparent !important;
  box-shadow: none !important;
  padding: 0 !important;
}

/* header text styles */
.header-text { font-size:20px; color:#fff; margin-bottom:4px; }
.header-sub { color:#cfcfcf; font-size:14px; margin-top:0; }

/* optional: make the header look a bit tighter */
.gradio-container { background: transparent !important; }
"""

if __name__ == "__main__":
    _require_openai_key()
    me = Me()

    with gr.Blocks(title=f"{me.name} — Career Assistant", css=css) as demo:
        with gr.Row(elem_classes="header-row", variant="default"):
            with gr.Column(scale=1, min_width=120):
                if avatar_path:
                    gr.Image(value=avatar_path, elem_classes="avatar-circle", show_label=False)
                else:
                    gr.Markdown("![avatar placeholder](https://via.placeholder.com/72)")
            with gr.Column(scale=4):
                gr.Markdown(f"### Hello — I am {me.name}", elem_classes="header-text")
                gr.Markdown("This is my avatar. You can ask any questions about my career, projects, skills, or interests.", elem_classes="header-sub")

        gr.Markdown("---")
        chatbot = gr.Chatbot(value=[], elem_id="chatbot")
        txt = gr.Textbox(placeholder="Ask a question about Akshay...", show_label=False)
        send_btn = gr.Button("Send")
        txt.submit(respond_and_append, [txt, chatbot], [txt, chatbot])
        send_btn.click(respond_and_append, [txt, chatbot], [txt, chatbot])
        gr.Markdown("---\n*I may ask for your email to follow up. Your email will be used only to notify Akshay.*")

    port_env = int(os.getenv("PORT", "0") or "0")
    port = port_env if port_env != 0 else find_free_port()
    print(f"Launching on port {port} ...", flush=True)
    demo.launch(server_name="127.0.0.1", server_port=port)
