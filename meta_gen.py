"""YouTube metadata generation via Ollama for chronicle-forge.

Split into three separate focused calls so each has a small thinking budget:
  1. Title  — one line, fast
  2. Description — 250-300 words, moderate
  3. Tags — JSON array, fast

Each call has its own timeout and fallback so a slow model never blocks the pipeline.
"""
import json
import os
import re
import threading
import time

import requests
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL    = os.getenv("OLLAMA_MODEL",    "gemma4:e4b")


def _ollama_stream(prompt: str, label: str, max_wait: int) -> str:
    """Stream with a hard wall-clock deadline. Returns empty string on timeout."""
    buf       = []
    error_box = [None]
    done      = threading.Event()

    def _worker():
        try:
            resp = requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": True},
                stream=True,
                timeout=(10, 60),
            )
            resp.raise_for_status()
            char_count   = 0
            t0           = time.time()
            last_print_t = 0.0
            for line in resp.iter_lines():
                if done.is_set():
                    resp.close()
                    return
                if not line:
                    continue
                data  = json.loads(line)
                token = data.get("response", "")
                buf.append(token)
                char_count += len(token)
                now = time.time()
                if char_count > 0 and now - last_print_t >= 1.0:
                    elapsed = int(now - t0)
                    print(f"\r  {label}... {char_count} chars ({elapsed}s)",
                          end="", flush=True)
                    last_print_t = now
                if data.get("done"):
                    return
        except Exception as exc:
            error_box[0] = exc
        finally:
            done.set()

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    completed = done.wait(timeout=max_wait)

    if not completed:
        done.set()
        t.join(timeout=3)
        print(f"\n  {label} timed out after {max_wait}s — using fallback")

    print(flush=True)
    if error_box[0] is not None and not buf:
        print(f"  {label} error: {error_box[0]} — using fallback")
        return ""
    return re.sub(r'<think>.*?</think>', '', "".join(buf), flags=re.DOTALL).strip()


def _generate_title(topic: str, narration_preview: str) -> str:
    prompt = (
        f'Write one YouTube video title for a documentary about: "{topic}"\n\n'
        f"Script preview: {narration_preview[:300]}\n\n"
        f"Rules: under 70 characters. Compelling and SEO-friendly.\n"
        f"Example: How Ancient Egypt Built the Pyramids\n\n"
        f"Output the title text only — no quotes, no explanation, no JSON."
    )
    raw = _ollama_stream(prompt, label="Title", max_wait=300)
    for line in raw.splitlines():
        line = line.strip().strip('"').strip("'")
        if 10 <= len(line) <= 70 and not line.startswith("{"):
            return line
    return topic.title()


def _generate_description(topic: str, narration_preview: str, sources: list) -> str:
    source_block = "\n".join(
        f"- {s['title']}: {s['url']}" for s in sources
    ) or "(no external sources)"

    prompt = (
        f'Write a YouTube video description for a documentary about "{topic}".\n\n'
        f"Script: {narration_preview[:500]}\n\n"
        f"Sources:\n{source_block}\n\n"
        f"Write 250-300 words using this structure:\n"
        f"- 2-sentence hook (shown before 'Show more')\n"
        f"- 3 bullet points covering what the video explores\n"
        f"- 'Sources & Further Reading' section with the URLs above\n"
        f"- One-line call to action (like, subscribe, comment)\n"
        f"- 3 hashtags on the final line\n\n"
        f"Output the description text only — no JSON, no title."
    )
    raw = _ollama_stream(prompt, label="Description", max_wait=600)
    if raw and len(raw) > 50:
        return raw
    return f"Explore the fascinating story of {topic} in this AI-generated documentary."


def _generate_tags(topic: str) -> list:
    prompt = (
        f'List 15 YouTube search tags for a documentary about "{topic}".\n\n'
        f"Mix broad category tags with specific topic tags.\n"
        f'Output ONLY a JSON array of strings: ["tag1", "tag2", ...]'
    )
    raw = _ollama_stream(prompt, label="Tags", max_wait=180)
    match = re.search(r'\[.*?\]', raw, re.DOTALL)
    if match:
        try:
            tags = json.loads(match.group())
            if isinstance(tags, list) and tags:
                return tags
        except json.JSONDecodeError:
            pass
    words = [w for w in topic.lower().split() if len(w) > 3]
    return [topic, *words, "documentary", "history", "educational", "youtube"]


def generate_metadata(topic: str, narration: str, sources: list) -> dict:
    """
    Generate YouTube metadata in three separate focused calls.

    sources: list of {title, url} from research_gen
    Returns: {title, description, tags}
    """
    narration_preview = narration[:500] + ("..." if len(narration) > 500 else "")

    print("  Step 3a: title")
    title = _generate_title(topic, narration_preview)
    print(f"  Title: {title!r}")

    print("  Step 3b: description")
    description = _generate_description(topic, narration_preview, sources)
    print(f"  Description: {len(description.split())} words")

    print("  Step 3c: tags")
    tags = _generate_tags(topic)
    print(f"  Tags: {len(tags)} tags")

    return {"title": title, "description": description, "tags": tags}
