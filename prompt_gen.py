"""MS Paint-style image prompt generation via Ollama for chronicle-forge.

Visual storytelling approach: before generating scene prompts, a "visual world"
is defined once (characters, recurring settings, objects, palette). Every prompt
batch receives this world definition PLUS the previous batch's prompts — so
characters and settings carry through from scene to scene instead of each image
being an isolated illustration.

Style split (from pipeline reference image):
  prompt_gen → CONTENT (what to draw, no style words)
  image_gen  → STYLE  (flat illustration profile, injected via OpenCLIP channel)
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

BATCH_SIZE = 8   # scenes per LLM call; smaller = tighter context per batch


def _ollama_stream(prompt: str, label: str = "Generating",
                   max_wait: int = 600) -> str:
    """Stream with a hard wall-clock deadline via daemon thread."""
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
        print(f"\n  {label} timed out after {max_wait}s — using fallbacks")

    print(flush=True)
    if error_box[0] is not None and not buf:
        print(f"  {label} error: {error_box[0]}")
        return ""
    return re.sub(r'<think>.*?</think>', '', "".join(buf), flags=re.DOTALL).strip()


def _define_visual_world(topic: str, narration: str) -> dict:
    """
    One-shot call to define the consistent visual world for the whole documentary.

    Returns a dict with characters, settings, objects, and palette.
    Every prompt batch uses this to keep visuals consistent across scenes.
    """
    prompt = (
        f"You are a visual director for a flat illustration documentary about: \"{topic}\"\n\n"
        f"Full narration:\n{narration[:1800]}\n\n"

        f"Define the VISUAL WORLD that will appear consistently across ALL scenes.\n"
        f"Think like a Kurzgesagt animator: simple iconic characters, recurring environments,\n"
        f"a distinctive color palette used throughout.\n\n"

        f"Rules:\n"
        f"- Characters: describe by ROLE and VISUAL APPEARANCE only (no names)\n"
        f"  e.g. 'Egyptian worker figure — muscular, brown tunic, shaved head'\n"
        f"- Settings: 2-3 distinct recurring locations tied to the narration\n"
        f"  e.g. 'pyramid construction site with sandy desert', 'throne room with pillars'\n"
        f"- Objects: 4-6 iconic props that recur across scenes\n"
        f"  e.g. 'stone block on wooden sled', 'golden ankh symbol', 'papyrus scroll'\n"
        f"- Palette: 4-5 specific colors that define the visual tone\n"
        f"  e.g. 'sandy ochre, deep Nile blue, gold, burnt orange, white'\n\n"

        f"Reply with ONLY valid JSON:\n"
        f"{{\n"
        f"  \"characters\": [\"character 1 description\", \"character 2 description\"],\n"
        f"  \"settings\": [\"setting 1\", \"setting 2\"],\n"
        f"  \"objects\": [\"object 1\", \"object 2\", \"object 3\"],\n"
        f"  \"palette\": \"color1, color2, color3, color4\"\n"
        f"}}"
    )

    raw   = _ollama_stream(prompt, label="Visual world", max_wait=300)
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            world = json.loads(match.group())
            if world.get("characters") or world.get("settings"):
                return world
        except json.JSONDecodeError:
            pass

    print("  Visual world definition failed — using fallback (narration-only context)")
    return {"characters": [], "settings": [], "objects": [], "palette": "vibrant, educational"}


def _prompt_batch(
    topic: str,
    narration: str,
    batch: list,
    offset: int,
    total: int,
    visual_world: dict,
    previous_prompts: list,
) -> list:
    """
    Generate image content descriptions for one batch of scenes.

    Uses visual_world for consistency and previous_prompts for continuity.
    Returns a list of prompt strings (same length as batch).
    """
    # Build visual world block
    chars    = visual_world.get("characters", [])
    settings = visual_world.get("settings",   [])
    objects  = visual_world.get("objects",    [])
    palette  = visual_world.get("palette",    "vibrant, educational")

    world_lines = []
    if chars:
        world_lines.append(f"Characters: {'; '.join(chars)}")
    if settings:
        world_lines.append(f"Settings: {'; '.join(settings)}")
    if objects:
        world_lines.append(f"Recurring objects: {'; '.join(objects)}")
    world_lines.append(f"Color palette: {palette}")
    world_block = "\n".join(world_lines)

    # Build continuity block from previous batch
    if previous_prompts:
        prev_lines = []
        for j, pp in enumerate(previous_prompts):
            scene_num = offset - len(previous_prompts) + j + 1
            prev_lines.append(f"  Scene {scene_num}: {pp}")
        continuity_block = (
            "PREVIOUS SCENES — reuse established visual elements for continuity:\n"
            + "\n".join(prev_lines)
            + "\n\n"
        )
    else:
        continuity_block = ""

    # Build scene blocks
    scene_blocks = []
    for i, scene in enumerate(batch):
        text = scene.get("text_segment") or scene.get("visual_subject", "")
        scene_blocks.append(
            f"[Scene {offset+i+1}/{total}]\n"
            f"  Narration: \"{text}\""
        )
    scenes_text = "\n\n".join(scene_blocks)

    prompt = (
        f"Generate image descriptions for a documentary about: \"{topic}\"\n\n"

        f"DOCUMENTARY NARRATION (full arc for context):\n"
        f"{narration[:1500]}\n\n"

        f"VISUAL WORLD (use these consistently across ALL scenes):\n"
        f"{world_block}\n\n"

        f"{continuity_block}"

        f"VISUAL STORYTELLING RULES:\n"
        f"1. Each image must LITERALLY ILLUSTRATE what the narration says — specific, not generic\n"
        f"   BAD: 'workers doing construction'   GOOD: 'three workers hauling rope attached to stone block on wooden sled'\n"
        f"2. REUSE the characters and settings defined above — visual world must feel consistent\n"
        f"3. Show SCALE and STORY PROGRESSION:\n"
        f"   - Opening scenes: wide establishing shots (desert horizon, city panorama)\n"
        f"   - Middle scenes: medium shots showing action and characters in context\n"
        f"   - Closing scenes: wide resolution shots with visual closure\n"
        f"4. Use VISUAL METAPHORS to reinforce the narration:\n"
        f"   - Power → show scale (tiny figure vs massive structure)\n"
        f"   - Time → show before/after, or seasons changing\n"
        f"   - Conflict → opposing groups or forces shown spatially\n"
        f"5. Keep descriptions 12-20 words — concrete and drawable\n"
        f"6. NO art style words (no 'flat', 'vector', 'Kurzgesagt', 'illustration') — describe CONTENT only\n\n"

        f"SCENES TO DESCRIBE:\n"
        f"{scenes_text}\n\n"

        f"Reply with ONLY valid JSON, no markdown:\n"
        f"{{\"scenes\": [{{\"prompt\": \"what to draw\"}}]}}"
    )

    raw   = _ollama_stream(prompt, label=f"Prompts {offset+1}-{offset+len(batch)}")
    match = re.search(r'\{.*\}', raw, re.DOTALL)

    if not match:
        return [
            scene.get("visual_subject") or scene.get("text_segment", "")[:60]
            for scene in batch
        ]

    try:
        result = json.loads(match.group())
        parsed = result.get("scenes", [])
        out = []
        for i, scene in enumerate(batch):
            ps  = parsed[i] if i < len(parsed) else {}
            fallback = (
                scene.get("visual_subject") or
                scene.get("text_segment", "")[:60]
            )
            out.append(ps.get("prompt", fallback))
        return out
    except (json.JSONDecodeError, KeyError):
        return [
            scene.get("visual_subject") or scene.get("text_segment", "")[:60]
            for scene in batch
        ]


def generate_image_prompts(video_data: dict) -> dict:
    """
    Generate one flat-illustration image prompt per scene, with visual continuity.

    First defines the visual world (characters, settings, palette) in a single
    LLM call, then generates prompts in batches — each batch receives the world
    definition and the previous batch's prompts for visual storytelling continuity.

    Mutates and returns video_data with 'prompt' added to each scene dict.
    """
    scenes   = video_data["scenes"]
    topic    = video_data.get("topic", "")
    narration = video_data.get("narration", "")
    n        = len(scenes)

    # Step A: define the visual world once (shared context for all batches)
    print("  Defining visual world...")
    visual_world = _define_visual_world(topic, narration)
    if visual_world.get("characters"):
        print(f"  Characters: {'; '.join(visual_world['characters'][:2])}")
    if visual_world.get("palette"):
        print(f"  Palette:    {visual_world['palette']}")

    # Step B: generate prompts in batches with rolling continuity
    total_batches   = (n + BATCH_SIZE - 1) // BATCH_SIZE
    previous_prompts: list[str] = []

    print(f"  {n} scenes → {total_batches} batch(es) of ≤{BATCH_SIZE}")

    for b, batch_start in enumerate(range(0, n, BATCH_SIZE)):
        batch = scenes[batch_start:batch_start + BATCH_SIZE]
        print(f"  Batch {b+1}/{total_batches} (scenes {batch_start+1}–{batch_start+len(batch)})...")

        # Pass the last 6 prompts as continuity context (enough to capture recurring elements)
        prompts = _prompt_batch(
            topic, narration, batch, batch_start, n,
            visual_world=visual_world,
            previous_prompts=previous_prompts[-6:],
        )

        for i, scene in enumerate(batch):
            scene["prompt"] = prompts[i]

        previous_prompts.extend(prompts)

    # Store visual world in video_data for reference
    video_data["visual_world"] = visual_world
    return video_data
