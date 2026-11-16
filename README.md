# Chronicle Forge

A local-AI powered YouTube story video generation pipeline. 
Give it a topic, get a fully narrated, image-synced MP4 — script, voiceover, visuals, and YouTube metadata included.

## Anna app — October 2026

A private **v0.2.1 studio candidate** is ready for user review: custom duration/image count, detailed/stick-figure controls, live previews and percentages, still whole-image export by default, clearer optional downloads and content-free local diagnostics. **46 tests pass**; a 30-second three-scene browser framing test and existing real-image/voice export were verified with no new AI calls. The submitted Anna review remains pinned to v0.1.1; this newer candidate is not submitted or public.

The [Anna app](anna-app/README.md) provides the full research → narration review → hosted illustrations → hosted speech → captioned MP4 workflow. It uses Anna-hosted AI services and a browser software video encoder, with no Ollama or local AI model dependency. Downloads include source notes, subtitles, a thumbnail and a resumable media project. These project files are separate from the original local pipeline checkpoints.

The local pipeline now refuses narration generation without research and instructs the model to avoid unsupported details and invented motives. These are safeguards, not a factual accuracy guarantee. Existing saved narrations are reused by `--resume`; these changes do not repair old checkpoints. The saved Blockbuster/Netflix run requires human fact review and includes an unrelated research article. Preserve or archive old output before starting a fresh run.

Run safety checks with `python -B -m unittest discover -s tests -v` and `node --test anna-app/tests/*.test.mjs`. All 35 automated tests passed. Live Anna research, script/audit, one image and one four-word speech clip were exercised. The final 2.104-second video was exported and decoded successfully at 720p and 1080p; two-scene concatenation and project recovery were also checked without further generation. After review feedback, app 772 version **0.1.1** (version ID **1912**, revision r11) was resubmitted and is **pending Anna review** as of 3 November 2026. It adds recoverable image jobs, visible generation progress and clearer output labels, plus expanded listing details and screenshots. A new 2.104-second 720p hosted image/speech video was exported, decoded and inspected; no local AI model was used. Long videos have not been acceptance-tested, to respect the user's low-cost test constraint.

---

## What It Does

Chronicle Forge runs a 6-step pipeline fully automatically:

| Step | What happens |
|------|-------------|
| 1 — Research | Fetches Wikipedia context for the topic |
| 2 — Script | **Pass 1:** Writes the narration story (with delivery annotations stripped to punctuation) **Pass 2:** Splits into scenes + writes image prompts **Pass 3:** Expands scenes into visual sub-moments (action → reaction → emotion) |
| 3 — Metadata | Generates YouTube title, description, and tags |
| 4 — TTS | Narrates the script with edge-tts or Kokoro, capturing word-level timestamps |
| 5 — Images | Generates one SDXL image per scene (16:9, Ken Burns ready) |
| 6 — Video | Composites timestamp-synced Ken Burns slideshow at 1920×1080 |

Everything is checkpointed. Ctrl+C at any time, `--resume` to continue exactly where you left off.

---

## System Requirements

### Operating System

| Path | OS |
|------|----|
| AMD GPU (DirectML) | **Windows 10/11 only** — `torch-directml` is Windows-exclusive |
| NVIDIA GPU (CUDA) | Windows or Linux |
| CPU-only (no images) | Any OS |

---

### Hardware

#### Minimum
| Component | Minimum | Notes |
|-----------|---------|-------|
| CPU | 4-core, 2.5 GHz | Used for TTS, video composition, VAE decode |
| RAM | 16 GB | SDXL loads ~4 GB into RAM; pipeline buffers images |
| GPU VRAM | 8 GB | Enough for SDXL at 1216×832 with split-device (UNet on GPU, VAE on CPU) |
| Disk | 20 GB free | SDXL model ~6 GB + generated images + output video |

#### Recommended
| Component | Recommended |
|-----------|-------------|
| CPU | 8-core, 3.5 GHz+ |
| RAM | 32 GB |
| GPU VRAM | 12 GB+ |
| Disk | 50 GB free (multiple runs + model cache) |

#### AMD GPUs (DirectML, Windows)
Any DirectML-capable AMD GPU works. Tested range:

| Class | Example | Notes |
|-------|---------|-------|
| Entry (8 GB VRAM) | RX 6600, RX 6650 XT | Works; ~3–4 min/image at 20 steps |
| Mid (12 GB VRAM) | RX 6700 XT, RX 7700 XT | ~2 min/image |
| High (16 GB VRAM) | RX 6800 XT, RX 7900 GRE | ~90 s/image |

Integrated AMD graphics (Radeon 680M, etc.) will work but are very slow — expect 10–20 min/image.

#### NVIDIA GPUs (CUDA)
| Class | Example | Notes |
|-------|---------|-------|
| Entry (8 GB VRAM) | RTX 3070, RTX 4060 | Works; ~45–90 s/image at 20 steps |
| Mid (12 GB VRAM) | RTX 3080, RTX 4070 | ~30–50 s/image |
| High (24 GB VRAM) | RTX 3090, RTX 4090 | ~15–25 s/image |

---

### External Software

These must be installed separately before running Chronicle Forge.

#### Ollama — required (LLM backend)
Downloads: [ollama.com](https://ollama.com)

Ollama runs the language model that writes the narration, scene prompts, and YouTube metadata.

```bash
# After installing Ollama, pull the model:
ollama pull gemma4:e4b

# Verify it's running:
ollama serve
```

- Ollama must be **running** (`ollama serve`) before starting the pipeline
- Default model: `gemma4:e4b` — runs on this PC, nothing is sent over the internet
- Any Ollama-compatible model works; set `OLLAMA_MODEL` in `.env` to change it
- The first call loads the model into the graphics card, so it can take a few seconds

#### SDXL Model — required (image generation)
Chronicle Forge needs an SDXL base model in **diffusers format** (a folder, not a single `.safetensors` file).

**Option A — InvokeAI** (recommended): InvokeAI downloads and converts SDXL models automatically and stores them in diffusers format. Point `MODEL_PATH` in `.env` at the model folder inside InvokeAI's model directory.

**Option B — manual conversion**: Download an SDXL `.safetensors` from CivitAI or Hugging Face and convert:
```bash
python -c "
from diffusers import StableDiffusionXLPipeline
pipe = StableDiffusionXLPipeline.from_single_file('your-model.safetensors')
pipe.save_pretrained('output-folder/')
"
```
Then set `MODEL_PATH=output-folder/` in `.env`.

Recommended base models: `stable-diffusion-xl-base-1.0`, `dreamshaperXL`, `realvisxlV50`.

#### FFmpeg — required (video composition)
MoviePy (used for the final video step) requires FFmpeg.

- **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH, or install via `winget install ffmpeg`
- **Linux**: `sudo apt install ffmpeg`

Verify: `ffmpeg -version`

#### Python 3.11 — required
```bash
python --version   # must say Python 3.11.x
```

`torch-directml` ships pre-built wheels for Python 3.11 on Windows only. Python 3.12+ is not supported for the AMD path.

---

## Requirements

### Choosing an Ollama text model

The local web UI has a **Text model** selector and **Refresh models** button.
It discovers text-generation models from your configured Ollama service,
labels local versus cloud execution, and prefers a local model on first use.
Your last submitted selection is remembered in that browser. The selected
model applies to remaining script, metadata, and image-prompt generation for
that run; resuming does not regenerate already saved text. It does not change
the speech or image-generation model. This selector belongs to the Python
web UI, separate from the Anna-hosted app.

For command-line use: `python main.py --model gemma4:e2b` (plus your normal
options). Without `--model`, the CLI still uses `OLLAMA_MODEL` from the
environment or `.env`. Local inference has no Ollama cloud charge; cloud
models require credits or an included paid allowance. On 13 November 2026,
a minimal `nemotron-3-super:cloud` probe returned HTTP 402 (credits required).

### Isolated Python environment (Windows)

Use Python 3.11 and install dependencies inside `.venv`:

```powershell
python3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-web.txt -c constraints.txt
.\.venv\Scripts\python.exe web_ui.py
```

If `python3.11` is unavailable, use the full path to a Python 3.11 executable
for the first command. Once `.venv` exists, always use its Python as shown;
activation is optional. The environment is excluded from version control.
`constraints.txt` keeps the installed libraries compatible with the current
MoviePy and DirectML code. Ollama and the SDXL model remain separate prerequisites.

### Optional — Staso agent tracing

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-staso.txt -c constraints.txt
.\.venv\Scripts\staso.exe setup --target codex --scope project --agent-name chronicle-forge --no-guard
.\.venv\Scripts\staso.exe status
```

Create an account at https://staso.ai/ and supply your Staso API key in the
interactive setup. This connects coding-agent hooks; installing the SDK alone
does not trace the Python pipeline. Configure Guard policies later if desired.
Review capture options during setup before sending traces.

### Python packages
```bash
pip install -r requirements.txt
```

### Optional — Kokoro TTS (local, offline)
```bash
pip install kokoro soundfile
```

### Optional — Web UI
```bash
pip install flask
```

---

## Setup

**1. Clone and install**
```bash
git clone <repo>
cd chronicle-forge
pip install -r requirements.txt
```

**2. Create `.env`** (copy from `.env.example`)
```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:e4b

# Path to your SDXL model in diffusers format
MODEL_PATH=Z:\Programs\Invoke\models\your-model-id

# SDXL inference settings
INVOKE_STEPS=20
INVOKE_CFG=7.0

# Default edge-tts voice (can override with --voice)
TTS_VOICE=en-US-AndrewMultilingualNeural
```

**3. Start Ollama**
```bash
ollama serve
ollama pull gemma4:e4b
```

---

## GPU Setup

### AMD GPU — DirectML

`torch-directml` lets AMD GPUs run SDXL on Windows without ROCm. The pipeline uses a specific split-device architecture to work around DirectML's limitations:

| Component | Device | Why |
|-----------|--------|-----|
| UNet | DirectML (GPU) | Heavy diffusion compute — this is where the GPU matters |
| VAE encoder/decoder | CPU (fp32) | DirectML's fp16 VAE produces corrupted output; CPU avoids it |
| Text encoders (CLIP / OpenCLIP) | CPU | Small models; keeping on CPU avoids device-mismatch crashes |
| Latents / scheduler | CPU | DirectML can't create random tensors; all book-keeping on CPU |

The UNet receives tensors from CPU, moves them to DML internally, and returns outputs back to CPU — a transparent bridge so the rest of the diffusers pipeline doesn't need to know about the device split.

**Four patches are applied at load time** (`_patch_dml_unet` in `image_gen.py`):

1. **CPU→DML→CPU bridge** on `unet.forward` — all inputs moved to DML on entry, all outputs returned to CPU on exit
2. **`time_proj` on CPU** — DirectML cannot compute int64 timestep embeddings; this layer runs on CPU then the result is moved to DML
3. **`time_embedding` to DML** — receives the CPU float from `time_proj`, explicitly moved to DML before proceeding
4. **`add_embedding` to DML** (SDXL-specific) — the extra conditioning embeddings SDXL appends are moved to DML before the add_embedding layer

**Version requirements are strict:**

```
torch-directml          # latest (AMD, Windows only)
diffusers>=0.27.0,<0.31.0   # newer versions change internal call signatures that break the patches
transformers>=4.40.0
```

> If you upgrade diffusers past 0.30.x and images stop generating, pin back to `diffusers==0.30.3`.

**Install:**
```bash
pip install torch-directml "diffusers>=0.27.0,<0.31.0" transformers accelerate safetensors
```

---

### NVIDIA GPU — CUDA

Replace the DirectML stack with standard PyTorch CUDA. No bridging patches are needed — CUDA handles full-pipeline GPU tensors without device splits.

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install "diffusers>=0.27.0" transformers accelerate safetensors
```

Then in `image_gen.py`, change the device:
```python
# Line ~199: replace
dml = torch_directml.device()
pipe.unet.to(dml)
# with:
pipe.to("cuda")
```

And remove the `_patch_dml_unet` call and `_decode_on_cpu` (use `output_type="pil"` instead of `"latent"`).

---

---

## Web UI

A browser-based interface with live logging, image preview, and step progress.

**Install Flask:**
```bash
pip install flask
# or
pip install -r requirements-web.txt
```

**Launch:**
```bash
python web_ui.py           # opens http://localhost:5000 automatically
python web_ui.py --port 8080
python web_ui.py --no-browser   # skip auto-open
```

Features:
- **Settings form** — topic, duration slider, TTS engine (edge / Kokoro), voice, image style, resume checkbox
- **Live log stream** — colour-coded output (step headers, progress, warnings, errors) via Server-Sent Events
- **Image preview** — polls every 2.5 seconds and shows the latest generated scene image
- **Step progress bar** — 6 steps, animates while active, turns green when done
- **Elapsed timer** — shown in the header while the pipeline runs
- **Stop button** — terminates the pipeline process
- **Download link** — appears when the final MP4 is ready
- Reconnect-safe: refreshing the browser replays the full log buffer

---

### Basic
```bash
# Fully interactive (asks topic, duration, engine, voice)
python main.py

# Supply everything on the command line
python main.py --topic "the invention of dynamite" --duration 300

# 10-minute video with British narrator
python main.py --topic "the Chernobyl disaster" --duration 600 --voice ryan
```

### TTS engine
```bash
# Microsoft Azure Neural (default, requires internet, highest quality)
python main.py --tts edge --voice christopher

# Kokoro — local, fully offline, CPU-native (~200 MB model)
python main.py --tts kokoro --voice george
```

### Image style
```bash
# High-quality 2D illustration with cel shading (default)
python main.py --style refined

# Simple stick figures, Zenn-channel flat aesthetic
python main.py --style stickman
```

### Resume / checkpoint
```bash
# Resume from the furthest completed step
python main.py --resume

# Resume with verbose image logging
python main.py --resume --logging
```

### All flags
| Flag | Values | Default | Description |
|------|--------|---------|-------------|
| `--topic` | any string | (prompted) | Story topic |
| `--duration` | seconds | (prompted) | Target video length |
| `--tts` | `edge`, `kokoro` | (prompted) | TTS engine |
| `--voice` | see tables below | (prompted) | Narrator voice alias |
| `--style` | `refined`, `stickman` | `refined` | Image style |
| `--resume` | flag | off | Resume from checkpoint |
| `--logging` | flag | off | Verbose image generation output |

---

## Voices

### edge-tts (online)
| Alias | Description |
|-------|-------------|
| `andrew` | US male, natural — *default* |
| `guy` | US male, confident narrator |
| `christopher` | US male, deep & authoritative |
| `eric` | US male, clear and engaging |
| `aria` | US female, warm and expressive |
| `jenny` | US female, natural and clear |
| `ryan` | British male, classic storyteller |
| `sonia` | British female, elegant |
| `william` | Australian male, casual authority |

### Kokoro (offline)
| Alias | Description |
|-------|-------------|
| `heart` | US female, warm — *default* |
| `bella` | US female, bright |
| `sarah` | US female, natural |
| `nova` | US female, expressive |
| `adam` | US male |
| `michael` | US male, clear |
| `george` | British male, classic |
| `lewis` | British male, strong |
| `emma` | British female, warm |

---

## Output

All files land in `output/`:

```
output/
├── video_data.json     ← full pipeline state (topic, narration, scenes, metadata)
├── narration.mp3       ← TTS audio (edge-tts)
├── narration.wav       ← TTS audio (Kokoro)
├── final_video.mp4     ← finished video (1920×1080)
└── images/
    ├── scene_001.png
    ├── scene_002.png
    └── ...
```

The `video_data.json` checkpoint means `--resume` can pick up from any failed or interrupted step without regenerating prior work.

---

## Sample Topics

These topic types reliably produce strong narration and visually rich scenes.

### Historical Inventions (dramatic origin stories)
```
the invention of dynamite
the accidental discovery of penicillin
how Post-it Notes were invented by accident
the creation of Velcro
the invention of the printing press and what it destroyed
how aspirin was discovered
```

### Rise & Fall (corporate tragedy)
```
how Kodak invented digital photography and then killed itself
the rise and fall of Blockbuster Video
how Theranos fooled Silicon Valley
the collapse of Enron
how Nokia lost the smartphone war it started
```

### Disasters & Survival
```
the Chernobyl disaster
the last days of Pompeii
how the Titanic actually sank
Ernest Shackleton's impossible survival in Antarctica
the 1918 Spanish flu pandemic
the Texas City Disaster of 1947
```

### Scientific Secrets
```
the Stanford Prison Experiment
Operation Paperclip — how NASA hired Nazi scientists
MK-Ultra and the CIA's mind control program
the real story of Nikola Tesla vs Thomas Edison
how the atomic bomb changed everything
```

### Ancient World
```
how the Egyptian pyramids were actually built
the fall of the Roman Empire
the lost city of Pompeii
the real history of the Trojan War
how the Mongol Empire conquered the world
```

### Space & Exploration
```
the Apollo 13 disaster and rescue
the race to the Moon (US vs Soviet Union)
the Voyager probes — humanity's furthest journey
the Challenger disaster and what NASA knew
```

### Cold War & Espionage
```
the Cuban Missile Crisis — 13 days that nearly ended the world
the Berlin Wall — how it was built and how it fell
the double agent who fooled the KGB
Project Azorian — the CIA stole a Soviet submarine
```

---

## Sample Prompts by Duration

### 5 minutes (300s — ~750 words)
Best for focused single-event stories:
- `"the accidental discovery of penicillin"`
- `"how Blockbuster rejected Netflix"`
- `"the Stanford Prison Experiment"`
- `"the Texas City Disaster of 1947"`

### 8 minutes (480s — ~1200 words)
Room for full story arcs with turning points:
- `"the invention of dynamite"` 
- `"the Chernobyl disaster"`
- `"the Apollo 13 disaster and rescue"`
- `"how Kodak destroyed itself"`

### 10 minutes (600s — ~1500 words)
Full documentary feel with multiple acts:
- `"the rise and fall of Theranos"`
- `"Ernest Shackleton's survival in Antarctica"`
- `"the Cuban Missile Crisis"`
- `"the real history of Nikola Tesla"`

---

## How the Narration Works

The script LLM (`gemma4:e4b`) writes emotionally-driven narration — not a documentary list of facts. It follows a three-act structure:

1. **Cold open** — drop into a vivid scene with no context ("He held a vial so unstable one wrong move would kill everyone in the building.")
2. **Rising stakes** — specific details, cause-and-effect, tension
3. **Retention hook** — a question or revelation around the halfway point that makes stopping feel impossible
4. **Payoff** — a closing image or consequence that lingers

Delivery is shaped through prose construction only:
- Short sentences hit hard
- Em-dashes (—) create mid-sentence pivots
- Ellipses (...) trail into suspense
- ALL CAPS on a single word for peak emphasis (rare)
- Paragraph breaks are breath marks

---

## Architecture

```
main.py              ← pipeline orchestration, CLI, checkpointing
research_gen.py      ← Wikipedia research fetch
script_gen.py        ← Pass 1/2/3: narration, scene cuts, visual expansion
meta_gen.py          ← YouTube title / description / tags
tts_gen.py           ← edge-tts and Kokoro audio generation
image_gen.py         ← SDXL image generation (DirectML / CUDA)
video_composer.py    ← Ken Burns video compositor (moviepy + OpenCV)
```

---

## Troubleshooting

**`torch-directml` install fails or import crashes**
This package only has Windows wheels for Python 3.11. Confirm your environment:
```bash
python --version          # must be 3.11.x
pip install torch-directml
python -c "import torch_directml; print(torch_directml.device())"
```
If you're on 3.12+, create a 3.11 venv and reinstall everything.

**`unbox expects Dml at::Tensor as inputs` crash during image generation**
The CPU→DML bridge patch in `_patch_dml_unet` should prevent this. If it still fires, it usually means a diffusers version past `0.31.0` is installed — it changes internal call signatures that break the patches. Pin back:
```bash
pip install "diffusers==0.30.3"
```

**`RuntimeError` during VAE decode / black or corrupted images**
DirectML fp16 VAE decode produces garbage output. The pipeline already decodes on CPU in fp32 via `_decode_on_cpu`. If you see black images, check that `pipe.vae` is not on the DML device — it should be on CPU.

**Images are slow (>3 min per image)**
Normal for AMD+DirectML. Expect 90–180 seconds per image at 20 steps on a mid-range AMD card. Reduce steps:
```env
INVOKE_STEPS=15
```

**Ollama times out on long prompts**
The cloud thinking model is slow. The pipeline uses 180s per batch call and 600s for the narration. If it times out, partial output is saved. Run `--resume` to continue.

**Images look photorealistic instead of illustrated**
This is expected with `--style refined` — it produces quality 2D illustration. For stick figures use `--style stickman`. If `refined` images still look too photorealistic, increase `INVOKE_CFG` to `8.0` or `9.0`.

**Kokoro not found**
```bash
pip install kokoro soundfile
```

**edge-tts fails / no audio**
Requires an internet connection. The Microsoft Azure TTS endpoint is free but rate-limited. Try again in a few seconds, or switch to `--tts kokoro` for offline use.

**Video audio out of sync**
If you switch TTS engines between runs, delete the old audio file and re-run TTS:
```bash
del output\narration.mp3
del output\narration.wav
python main.py --resume
```
The pipeline uses TTS word-boundary timestamps for image sync — mismatched audio from a different engine/run will desync.


Review status update — 3 November 2026: latest working revision r16 was cut as v0.2.2 (1937) and submitted. Anna confirmed pending_review pinned to v0.2.2, replacing v0.1.1. Store metadata and studio screenshots synchronized. Final real multi-scene test remains quota-blocked; this limitation was included in the submitted changelog.
