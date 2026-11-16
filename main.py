"""Chronicle Forge — AI long-form YouTube story generator.

Pipeline (6 steps):
  1. research_gen   → Wikipedia research + source URLs
  2. script_gen     → Pass 1: story narration (LLM tags stripped → punctuation/caps)
                      Pass 2: scene breakdown + image prompts
                      Pass 3: visual sub-scene expansion (adds emotion/action images)
  3. meta_gen       → YouTube title, description, tags (3 sub-calls)
  4. tts_gen        → edge-tts OR Kokoro audio + word-boundary timestamps
  5. image_gen      → SDXL cinematic images (16:9, one per expanded scene)
  6. video_composer → timestamp-synced Ken Burns MP4 (1920×1080)

Press Ctrl+C at any time to pause cleanly. Run with --resume to continue.

Resume auto-detects the furthest completed state:
  all images exist      → skip to step 6 (video compose only)
  some images exist     → skip to step 5 (continue from next missing image)
  audio + timestamps    → skip to step 5 (images fresh)
  has scene prompts     → skip to step 4 (TTS then images)
  has youtube meta      → skip to step 3 (re-run prompts onward)
  has narration only    → skip to step 2 (re-run Pass 2 + Pass 3 + onward)

Usage:
    python main.py                                          # fully interactive
    python main.py --topic "ancient egypt" --duration 420  # any number of seconds
    python main.py --voice christopher                      # pick narrator voice
    python main.py --resume                                 # resume from checkpoint
    python main.py --resume --logging                       # resume + verbose images
    python main.py --tts kokoro                             # use local Kokoro TTS
    python main.py --tts edge --voice christopher           # edge-tts with specific voice
"""
import argparse
import json
import os
import sys

# Force UTF-8 output so arrow/Unicode characters survive Windows cp1252 consoles.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA_PATH = "output/video_data.json"

# ── TTS voice tables ──────────────────────────────────────────────────────────

EDGE_VOICE_OPTIONS = {
    "andrew":      ("en-US-AndrewMultilingualNeural", "Andrew — US male, natural (default)"),
    "guy":         ("en-US-GuyNeural",                "Guy — US male, confident narrator"),
    "christopher": ("en-US-ChristopherNeural",        "Christopher — US male, deep & authoritative"),
    "eric":        ("en-US-EricNeural",               "Eric — US male, clear and engaging"),
    "aria":        ("en-US-AriaNeural",               "Aria — US female, warm and expressive"),
    "jenny":       ("en-US-JennyNeural",              "Jenny — US female, natural and clear"),
    "ryan":        ("en-GB-RyanNeural",               "Ryan — British male, classic storyteller"),
    "sonia":       ("en-GB-SoniaNeural",              "Sonia — British female, elegant"),
    "william":     ("en-AU-WilliamNeural",            "William — Australian male, casual authority"),
}
DEFAULT_EDGE_VOICE_KEY = "andrew"

KOKORO_VOICE_OPTIONS = {
    "heart":   ("af_heart",   "Heart — US female, warm (default)"),
    "bella":   ("af_bella",   "Bella — US female, bright"),
    "sarah":   ("af_sarah",   "Sarah — US female, natural"),
    "nova":    ("af_nova",    "Nova — US female, expressive"),
    "adam":    ("am_adam",    "Adam — US male"),
    "michael": ("am_michael", "Michael — US male, clear"),
    "george":  ("bm_george",  "George — British male, classic"),
    "lewis":   ("bm_lewis",   "Lewis — British male, strong"),
    "emma":    ("bf_emma",    "Emma — British female, warm"),
}
DEFAULT_KOKORO_VOICE_KEY = "heart"

# Kept for backward-compat with any external callers.
VOICE_OPTIONS     = EDGE_VOICE_OPTIONS
DEFAULT_VOICE_KEY = DEFAULT_EDGE_VOICE_KEY


def _load_data() -> dict:
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(
            f"No saved data at {DATA_PATH}\n"
            "Run without --resume to generate a new video."
        )
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_data(data: dict) -> None:
    os.makedirs("output", exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  Saved → {DATA_PATH}")


def _print_summary(data: dict) -> None:
    scenes = data.get("scenes", [])
    words  = len(data.get("narration", "").split())
    yt     = data.get("youtube", {})
    print(f"  Topic:    {data.get('topic', '?')}")
    print(f"  Duration: {data.get('target_seconds', '?')}s  |  {words} words")
    print(f"  Scenes:   {len(scenes)}")
    if yt.get("title"):
        print(f"  YT Title: {yt['title']}")


def _select_engine(cli_arg: str | None) -> str:
    """Return TTS engine: 'edge' or 'kokoro'."""
    if cli_arg in ("edge", "kokoro"):
        label = "edge-tts (Azure Neural)" if cli_arg == "edge" else "Kokoro (local)"
        print(f"  TTS engine: {label}")
        return cli_arg

    print("\nTTS Engine:")
    print("  1. edge-tts — Microsoft Azure Neural (online, high quality) [default]")
    print("  2. Kokoro   — local CPU model (fully offline, ~200 MB)")
    print()
    raw = input("Select engine [1-2, default 1]: ").strip()
    if raw == "2":
        print("  TTS engine: Kokoro (local)")
        return "kokoro"
    print("  TTS engine: edge-tts (Azure Neural)")
    return "edge"


def _select_voice_edge(cli_arg: str | None) -> tuple[str, str]:
    """Return (key, voice_id) from --voice alias or interactive menu."""
    if cli_arg:
        key = cli_arg.lower()
        if key in EDGE_VOICE_OPTIONS:
            voice_id, desc = EDGE_VOICE_OPTIONS[key]
            print(f"  Narrator: {desc}")
            return key, voice_id
        print(f"  Unknown edge-tts voice '{cli_arg}' — showing menu.")

    print("\nAvailable edge-tts voices:")
    keys = list(EDGE_VOICE_OPTIONS)
    for i, key in enumerate(keys, 1):
        _, desc = EDGE_VOICE_OPTIONS[key]
        marker = " (default)" if key == DEFAULT_EDGE_VOICE_KEY else ""
        print(f"  {i:2d}. {desc}{marker}")
    print()

    raw = input(f"Select voice [1-{len(keys)}, default 1]: ").strip()
    idx = int(raw) - 1 if raw.isdigit() and 1 <= int(raw) <= len(keys) else 0
    chosen_key = keys[idx]
    voice_id, desc = EDGE_VOICE_OPTIONS[chosen_key]
    print(f"  Narrator: {desc}")
    return chosen_key, voice_id


def _select_voice_kokoro(cli_arg: str | None) -> tuple[str, str]:
    """Return (key, voice_id) from --voice alias or interactive menu."""
    if cli_arg:
        key = cli_arg.lower()
        if key in KOKORO_VOICE_OPTIONS:
            voice_id, desc = KOKORO_VOICE_OPTIONS[key]
            print(f"  Narrator: {desc}")
            return key, voice_id
        # Also accept raw Kokoro IDs like 'af_heart' directly
        all_ids = {v[0]: k for k, v in KOKORO_VOICE_OPTIONS.items()}
        if cli_arg in all_ids:
            found_key = all_ids[cli_arg]
            voice_id, desc = KOKORO_VOICE_OPTIONS[found_key]
            print(f"  Narrator: {desc}")
            return found_key, voice_id
        print(f"  Unknown Kokoro voice '{cli_arg}' — showing menu.")

    print("\nAvailable Kokoro voices:")
    keys = list(KOKORO_VOICE_OPTIONS)
    for i, key in enumerate(keys, 1):
        _, desc = KOKORO_VOICE_OPTIONS[key]
        marker = " (default)" if key == DEFAULT_KOKORO_VOICE_KEY else ""
        print(f"  {i:2d}. {desc}{marker}")
    print()

    raw = input(f"Select voice [1-{len(keys)}, default 1]: ").strip()
    idx = int(raw) - 1 if raw.isdigit() and 1 <= int(raw) <= len(keys) else 0
    chosen_key = keys[idx]
    voice_id, desc = KOKORO_VOICE_OPTIONS[chosen_key]
    print(f"  Narrator: {desc}")
    return chosen_key, voice_id


def _select_voice(cli_arg: str | None, engine: str) -> tuple[str, str]:
    """Return (key, voice_id) for the chosen TTS engine."""
    if engine == "kokoro":
        return _select_voice_kokoro(cli_arg)
    return _select_voice_edge(cli_arg)


# ── Resume detection helpers ──────────────────────────────────────────────────

def _has_script(data: dict) -> bool:
    """Pass 1 complete: narration text exists (tags already stripped)."""
    return bool(data.get("narration"))


def _has_prompts(data: dict) -> bool:
    """Pass 2 complete: scenes exist with image prompts."""
    scenes = data.get("scenes", [])
    return bool(scenes) and "prompt" in scenes[0]


def _has_expanded(data: dict) -> bool:
    """Pass 3 complete: scene list has been visually expanded."""
    return bool(data.get("scenes_expanded"))


def _has_partial_expand(data: dict) -> bool:
    """Pass 3 started but not finished (at least one batch checkpointed)."""
    return (not data.get("scenes_expanded")
            and data.get("scenes_expand_cursor", 0) > 0
            and "scenes_original" in data)


def _has_youtube(data: dict) -> bool:
    return bool(data.get("youtube", {}).get("title"))


def _has_audio() -> bool:
    return (os.path.exists("output/narration.mp3")
            or os.path.exists("output/narration.wav"))


def _get_audio_path() -> str:
    """Return path of whichever audio file was generated."""
    if os.path.exists("output/narration.wav"):
        return "output/narration.wav"
    return "output/narration.mp3"


def _has_timestamps(data: dict) -> bool:
    scenes = data.get("scenes", [])
    return bool(scenes) and "start_ms" in scenes[0]


def _count_existing_images(n_scenes: int) -> int:
    return sum(
        1 for i in range(n_scenes)
        if os.path.exists(f"output/images/scene_{i+1:03d}.png")
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Chronicle Forge — AI story video generator"
    )
    parser.add_argument("--model", help="Ollama text model for this run (overrides OLLAMA_MODEL)")
    parser.add_argument("--topic",    help="Story topic (e.g. 'ancient egypt')")
    parser.add_argument("--duration", type=int,
                        help="Target duration in seconds (e.g. --duration 420)")
    parser.add_argument("--logging",  action="store_true",
                        help="Verbose: print prompts and open each image as it renders")
    parser.add_argument("--voice",    metavar="NAME",
                        help="Narrator voice alias: andrew, guy, christopher, eric, "
                             "aria, jenny, ryan, sonia, william")
    parser.add_argument("--tts",      choices=["edge", "kokoro"],
                        metavar="ENGINE",
                        help="TTS engine: edge (Microsoft Azure, default) or "
                             "kokoro (local CPU, offline)")
    parser.add_argument("--style",    choices=["stickman", "refined"],
                        default=None,
                        help="Image style: stickman (Zenn flat style) or "
                             "refined (quality 2D animation, default)")
    parser.add_argument("--resume",   action="store_true",
                        help=f"Resume pipeline from checkpoint at {DATA_PATH}")
    args = parser.parse_args()
    if args.model:
        # Set before generation modules import their environment configuration.
        os.environ["OLLAMA_MODEL"] = args.model

    print("=== Chronicle Forge — AI Story Video Generator ===\n")
    os.makedirs("output/images", exist_ok=True)

    # ─── Resume: load checkpoint first, then restore all settings from it ────
    if args.resume:
        print(f"Loading checkpoint from {DATA_PATH}...")
        video_data = _load_data()
        _print_summary(video_data)

        # Restore TTS settings from checkpoint; CLI args take precedence.
        tts_engine = args.tts or video_data.get("tts", "edge")
        voice_key  = args.voice or video_data.get("voice_key")
        voice_opts = KOKORO_VOICE_OPTIONS if tts_engine == "kokoro" else EDGE_VOICE_OPTIONS
        tts_voice  = voice_opts[voice_key][0] if voice_key in voice_opts else None

        if not _has_audio():
            _label = "Kokoro (local)" if tts_engine == "kokoro" else "edge-tts (Azure)"
            print(f"  TTS: {_label}  (override with --tts / --voice)\n")

        # Skip-to detection: find the furthest completed step.
        n_scenes = len(video_data.get("scenes", []))
        n_images = _count_existing_images(n_scenes)

        if n_images == n_scenes > 0 and _has_audio():
            print(f"  Checkpoint: all {n_scenes} images exist — resuming from step 6 (video)\n")
            skip_to = 6
        elif n_images == n_scenes > 0:
            # Images are all done but audio was deleted — regenerate TTS only.
            print(f"  Checkpoint: all {n_scenes} images exist but audio missing — resuming from step 4 (TTS)\n")
            skip_to = 4
        elif n_images > 0:
            print(f"  Checkpoint: {n_images}/{n_scenes} images done "
                  f"— resuming from step 5 (continue from image {n_images + 1})\n")
            skip_to = 5
        elif (_has_prompts(video_data) and _has_expanded(video_data)
              and _has_audio() and _has_timestamps(video_data)):
            print("  Checkpoint: audio + timestamps found — resuming from step 5 (images)\n")
            skip_to = 5
        elif _has_prompts(video_data) and _has_expanded(video_data):
            print("  Checkpoint: Pass 1-3 complete — resuming from step 3 (metadata)\n")
            skip_to = 3
        elif _has_prompts(video_data) and _has_partial_expand(video_data):
            cursor = video_data["scenes_expand_cursor"]
            total  = len(video_data["scenes_original"])
            print(f"  Checkpoint: Pass 3 partial ({cursor}/{total} scenes done) — resuming\n")
            skip_to = 2
        elif _has_prompts(video_data):
            print("  Checkpoint: Pass 2 complete, no expansion — resuming Pass 3\n")
            skip_to = 2   # inner logic skips Pass 1 + 2, runs Pass 3 only
        elif _has_script(video_data):
            print("  Checkpoint: narration saved — re-running from Pass 2 onward\n")
            skip_to = 2
        else:
            print("  Checkpoint has no script — starting from step 1\n")
            skip_to = 1
    else:
        tts_engine    = _select_engine(args.tts)
        voice_key, tts_voice = _select_voice(args.voice, tts_engine)
        skip_to    = 1
        video_data = {}

    # Effective style: on resume prefer checkpoint over argparse default (None → "refined").
    effective_style = args.style or (video_data.get("style") if args.resume else None) or "refined"

    # ─── Step 1: Research ─────────────────────────────────────────────────────
    if skip_to <= 1:
        topic = args.topic
        if not topic:
            topic = input("Story topic (e.g. 'the Manhattan Project', 'ancient egypt'): ").strip()
        if not topic:
            raise SystemExit("Topic is required.")

        duration = args.duration
        while not duration:
            raw = input("Duration in seconds (e.g. 300 = 5 min, 600 = 10 min): ").strip()
            duration = int(raw) if raw.isdigit() else None

        print(f"\nTopic: {topic!r}  |  Duration: {duration}s  |  "
              f"Logging: {'on' if args.logging else 'off'}\n")

        from script_gen import check_ollama
        check_ollama()

        print("[1/6] Fetching Wikipedia research...")
        from research_gen import fetch_research
        research = fetch_research(topic, verbose=args.logging)

        video_data = {
            "topic":          topic,
            "target_seconds": duration,
            "research":       research,
            "tts":            tts_engine,
            "voice_key":      voice_key,
            "style":          effective_style,
        }
    else:
        topic    = video_data["topic"]
        duration = video_data["target_seconds"]
        research = video_data.get("research", {"summary": "", "sources": []})

    # ─── Step 2: Script (3 passes, with checkpoints) ─────────────────────────
    if skip_to <= 2:
        print("\n[2/6] Generating story script...")
        from script_gen import (generate_narration, generate_scenes_with_prompts,
                                 expand_scenes, convert_narration_tags)

        # Pass 1: story narration — save immediately to protect against Pass 2/3 failure.
        # Two-layer interrupt guard:
        #   Layer 1 (_ollama_stream): catches KeyboardInterrupt during streaming and
        #            returns whatever was generated so the caller can save it.
        #   Layer 2 (here): catches KeyboardInterrupt in the tiny window after
        #            generate_narration() returns but before _save_data() completes.
        if not _has_script(video_data):
            narration_tagged = None
            try:
                narration_tagged = generate_narration(topic, duration, research["summary"])
                narration = convert_narration_tags(narration_tagged)
                video_data["narration"] = narration
                _save_data(video_data)
            except KeyboardInterrupt:
                if narration_tagged:
                    print("\n  Saving narration before exit...")
                    narration = convert_narration_tags(narration_tagged)
                    video_data["narration"] = narration
                    _save_data(video_data)
                raise
        else:
            print("  Pass 1: narration already saved — skipping to Pass 2")
            narration = video_data["narration"]

        # Pass 2: scene cuts (auto-split) + batched LLM image prompts
        if not _has_prompts(video_data):
            scenes = generate_scenes_with_prompts(narration, duration)
            video_data["scenes"] = scenes
            _save_data(video_data)
        else:
            print("  Pass 2: scene prompts already saved — skipping to Pass 3")
            scenes = video_data["scenes"]

        # Pass 3: visual sub-scene expansion (adds emotion/action images)
        # Checkpoints after every batch — safe to Ctrl+C or let batches time out.
        if not _has_expanded(video_data):
            # Preserve the pre-expansion scene list so resume can pick up mid-run.
            if "scenes_original" not in video_data:
                video_data["scenes_original"] = list(scenes)
                _save_data(video_data)

            original_scenes  = video_data["scenes_original"]
            cursor           = video_data.get("scenes_expand_cursor", 0)
            already_expanded = video_data.get("scenes", []) if cursor > 0 else []
            remaining        = original_scenes[cursor:]

            if cursor > 0:
                print(f"  Pass 3: resuming from scene {cursor + 1}/{len(original_scenes)}")

            def _checkpoint_pass3(partial, new_cursor):
                video_data["scenes"]               = already_expanded + partial
                video_data["scenes_expand_cursor"] = cursor + new_cursor
                _save_data(video_data)

            new_expanded = expand_scenes(remaining, on_batch=_checkpoint_pass3)
            scenes = already_expanded + new_expanded
            video_data["scenes"]          = scenes
            video_data["scenes_expanded"] = True
            video_data.pop("scenes_expand_cursor", None)
            video_data.pop("scenes_original",      None)
            _save_data(video_data)
        else:
            print("  Pass 3: scene expansion already saved — skipping")
            scenes = video_data["scenes"]

        # Deduplicate scenes by text_segment — LLM occasionally repeats opening lines.
        seen_segs, unique = set(), []
        for sc in scenes:
            t = sc.get("text_segment", "")
            if t not in seen_segs:
                seen_segs.add(t)
                unique.append(sc)
        if len(unique) < len(scenes):
            n_removed = len(scenes) - len(unique)
            print(f"  Removed {n_removed} duplicate scene(s) — {len(unique)} unique scenes remain")
            scenes = unique

        # Tag each scene with its 1-based index (for checkpoint inspection only).
        for i, sc in enumerate(scenes):
            sc["_n"] = i + 1
        video_data["scenes"] = scenes
        _save_data(video_data)

        print(f"  Script: {len(narration.split())} words, {len(scenes)} scenes (expanded)")

    # ─── Step 3: YouTube Metadata ─────────────────────────────────────────────
    if skip_to <= 3:
        print("\n[3/6] Generating YouTube metadata (3 sub-calls)...")
        from meta_gen import generate_metadata
        youtube = generate_metadata(
            topic, video_data["narration"], research["sources"]
        )
        print(f"  Title: {youtube['title']}")
        if youtube.get("tags"):
            print(f"  Tags:  {', '.join(youtube['tags'][:6])}...")

        video_data["youtube"] = youtube
        _save_data(video_data)

    # ─── Step 4: TTS ──────────────────────────────────────────────────────────
    audio_path = _get_audio_path()   # may be .mp3 or .wav depending on engine
    if skip_to <= 4:
        if _has_audio() and _has_timestamps(video_data):
            audio_path = _get_audio_path()
            print("\n[4/6] Skipping TTS — audio and timestamps already exist.")
        else:
            print(f"\n[4/6] Generating TTS narration ({tts_engine}, per-scene)...")

            # Guard: remove any duplicate text_segments saved in the checkpoint.
            _raw = video_data["scenes"]
            _seen, _deduped = set(), []
            for sc in _raw:
                t = sc.get("text_segment", "")
                if t not in _seen:
                    _seen.add(t)
                    _deduped.append(sc)
            if len(_deduped) < len(_raw):
                print(f"  Removed {len(_raw) - len(_deduped)} duplicate scene(s) before TTS")
                video_data["scenes"] = _deduped
                _save_data(video_data)

            # Per-scene clips: each scene gets its own TTS clip, timed individually.
            # start_ms/end_ms are set from cumulative clip durations — frame-accurate,
            # no word-boundary matching or character-position estimation needed.
            from tts_gen import generate_tts_scenes
            audio_path, scenes_with_ts = generate_tts_scenes(
                video_data["scenes"], voice=tts_voice, engine=tts_engine
            )

            video_data["scenes"] = scenes_with_ts
            total_ms = scenes_with_ts[-1]["end_ms"] if scenes_with_ts else 0
            print(f"  Audio: {total_ms/1000:.1f}s  |  {len(scenes_with_ts)} scenes with timestamps")

            _save_data(video_data)

    # ─── Step 5: Images + Thumbnail ───────────────────────────────────────────
    if skip_to <= 5:
        n_scenes  = len(video_data["scenes"])
        n_done    = _count_existing_images(n_scenes)
        remaining = n_scenes - n_done

        print(f"\n[5/6] Generating images via SDXL (style: {effective_style})...")
        if n_done > 0 and remaining > 0:
            print(f"  Resuming from image {n_done + 1}/{n_scenes} "
                  f"({n_done} already done).")
        elif remaining == 0:
            print(f"  All {n_scenes} scene images already exist.")

        from image_gen import generate_images, generate_thumbnail

        # ── Thumbnail (generated before scene images, pipeline warm-up is free) ──
        thumb_path = "output/thumbnail.png"
        if not os.path.exists(thumb_path):
            print("  Generating YouTube thumbnail...")
            from script_gen import generate_thumbnail_prompt
            youtube_title = video_data.get("youtube", {}).get("title", topic)
            thumb_prompt, headline = generate_thumbnail_prompt(
                topic, youtube_title, video_data["narration"]
            )
            print(f"  Headline: {headline!r}")
            generate_thumbnail(thumb_prompt, headline, style_mode=effective_style)
        else:
            print(f"  Thumbnail already exists — {thumb_path}")

        # ── Scene images ──────────────────────────────────────────────────────
        if remaining > 0:
            print("  Press Ctrl+C at any time to pause. "
                  "Run with --resume to continue from this point.")
        image_paths = generate_images(
            video_data["scenes"], style_mode=effective_style, verbose=args.logging
        )
        print(f"  {len(image_paths)} scene images ready")

    else:
        # skip_to == 6: all images confirmed to exist at resume detection time
        n_scenes    = len(video_data["scenes"])
        image_paths = [f"output/images/scene_{i+1:03d}.png" for i in range(n_scenes)]
        print(f"\n[5/6] Skipping image generation — all {n_scenes} images already exist.")

    # ─── Step 6: Video ────────────────────────────────────────────────────────
    print("\n[6/6] Composing timestamp-synced video (1920×1080)...")
    from video_composer import compose_video
    output_path = compose_video(image_paths, video_data["scenes"], audio_path)

    # ─── Results ──────────────────────────────────────────────────────────────
    print(f"\n{'='*50}")
    print("Done!")
    print(f"  Video     → {output_path}")
    print(f"  Thumbnail → output/thumbnail.png")
    print(f"  Pipeline  → {DATA_PATH}")
    print(f"  Images    → output/images/  ({len(image_paths)} files)")
    print()

    yt = video_data.get("youtube", {})
    if yt.get("title"):
        print("=== YouTube Metadata ===")
        print(f"Title:\n  {yt['title']}\n")
        if yt.get("tags"):
            print(f"Tags:\n  {', '.join(yt['tags'])}\n")
        if yt.get("description"):
            print("Description:")
            print(yt["description"])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nPaused. Run with --resume to continue from where you left off.")
        raise SystemExit(0)
