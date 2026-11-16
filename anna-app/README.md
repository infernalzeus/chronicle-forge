# Chronicle Forge on Anna

Anna app **772**, slug `chronicle-forge`: https://anna.partners/developer?app=772. Updated 3 November 2026.

**Release status:** version **0.1.1** (ID **1912**), cut from revision **r11**, was submitted successfully on 3 November 2026. Anna reports **pending_review**, pinned to **v0.1.1**. Version 0.1.0 was rejected with listing, progress and AI-output feedback. The updated listing, two screenshots and privacy page are synchronized and publicly accessible. Public availability still depends on Anna approval.

## Models and processing

The Anna app calls only Anna Host APIs for research, narration, image generation and speech. It never calls Ollama, localhost, SDXL, PyTorch or the desktop pipeline, and never reads `.env` or API-key files. The user specifically requested advance notice before any local AI model run; no local model has been invoked during this integration.

MP4 encoding runs on the user's device using a single-thread FFmpeg WebAssembly worker. This is conventional video processing, not an AI model. The encoder downloads about 31 MB once per page session and uses CPU/RAM. No microphone, camera, screen capture or filesystem permission is requested. The file-open control reads only the project file selected by the user. Media providers are selected from Anna's actual catalog.

## Workflow

1. Research public pages and explicitly select relevant evidence. The five-second test option fetches one source and caps narration/audit responses at 256/384 tokens.
2. Draft source-linked narration and inspect a separate model-assisted audit. The audit is not proof of truth. Correct the editable narration and approve it before paid media generation.
3. Generate Anna-hosted illustrations and scene-by-scene speech. Completed assets are reused on retry. Stop takes effect after any in-flight hosted call, which may still be charged. Closing or reloading loses in-memory work unless saved.
4. Export a captioned 16:9 H.264/AAC MP4 at 720p or 1080p. Captions are approximate within each scene; scene durations come from decoded speech. Downloads include MP4, SRT, thumbnail, script/source notes and a resumable project containing completed media.
5. Reopen a resumable project without regeneration. File types and size are checked; imported text is treated as data. Publicly publishing the resulting video is the user's responsibility.

All generated images are labelled as AI illustrations. The app does not automatically publish to YouTube or other social platforms.

## Verification

- JavaScript workflow, media planning, retry/cancellation, budget limits, and project recovery tests: **30 passed**.
- Python research safety tests: **5 passed** in the earlier integration. These mock network boundaries and do not invoke models.
- Anna strict manifest/bundle validation passed.
- Browser-only smoke test: downloaded 2.002-second MP4; ffprobe confirmed H.264 picture (640×360) and AAC audio (48 kHz); FFmpeg decoded without errors.
- Hosted low-cost acceptance used one NASA source, two bounded script/audit calls, **one generated illustration** (GPT Image 2 on Anna) and **one four-word speech request** (Qwen3 TTS Flash on Anna). Final narration: “The Moon orbits Earth.” Speech was about two seconds. No extra model calls were made during renderer debugging.
- The first direct WebCodecs pipeline stalled. Browser MediaRecorder passed the small synthetic test but silently omitted video from the 720p generated-image clip. File inspection detected audio-only output; an in-app video-track validation gate now rejects such files. The final renderer uses software FFmpeg rather than either failing browser-encoder path.
- The paid image was saved through Edge and the already-generated audio was recovered from the first test artifact. `.internal/anna-restore-test.json` reuses those assets for regression tests without paid regeneration. Working files are ignored by Git.

See the final acceptance record below for current release status.

### Final acceptance record

- Final software-rendered 720p file: H.264 1280×720 + AAC 48 kHz, **2.104329 s**, 771,110 bytes; fully decoded without errors. A frame was inspected for picture, captions and AI disclosure.
- Final r8 two-scene 1080p file: H.264 1920×1080 + AAC 48 kHz, **2.104329 s**, 1,161,877 bytes; fully decoded without errors. The final frame check confirmed the disclosure stays inside the frame and captions are readable.
- Subtitle and thumbnail downloads succeeded. The browser-generated resumable project was downloaded and parsed back with two intact image blobs and two intact audio blobs. The two-scene fixture reused/split the same paid media and made no new model calls.
- Artifacts are in `output/anna-acceptance/`; working fixtures remain in ignored `.internal/`. The browser-generated project is in the user's Downloads folder. Earlier audio-only failure artifacts are superseded by the verified files.
- Public release privacy page returned HTTP 200 without account credentials: https://anna.partners/anna-apps/infernalzeus/chronicle-forge/0.1.0/privacy.html.
- No long-duration paid video was generated. Tests deliberately used a four-word narration and only one paid illustration and one paid speech clip. Long-project performance remains unverified; start with a short video before attempting long renders.

## Development and distribution

```powershell
node --test anna-app/tests/*.test.mjs
python -m unittest discover -s tests -v
npx --yes @anna-ai/cli validate --strict --manifest anna-app/manifest.json --bundle anna-app/bundle
npx --yes @anna-ai/cli apps push --cwd anna-app
```

The authenticated Anna CLI keeps its token outside the repository. Do not print or copy it into project files. `.anna/` is ignored. Always confirm uploads resolve to app 772. `apps push` updates a private working draft; `apps cut` creates an immutable candidate; `apps submit-review` requests Anna review. Public availability requires Anna approval and release. Admin approval cannot be performed by this application.

The FFmpeg encoder is vendored from official npm distributions: `@ffmpeg/ffmpeg@0.12.15` and `@ffmpeg/core@0.12.10`. Its original WASM bytes are split into five pieces to meet Anna's 10 MB per-file limit; combined size stays below the 50 MB total bundle limit. `encoder-lock.json` records the original SHA-256. Notices, licenses, corresponding upstream source/build links and the DejaVu font license are included in `bundle/vendor/ffmpeg/`. No encoder source is modified.

Original desktop scripts remain available independently. Running `main.py`, `image_gen.py`, `script_gen.py` or the original desktop UI can invoke local models; do not run that pipeline without notifying the user first. Existing old checkpoints are not repaired automatically.

Official references: [Developer Hub](https://anna.partners/llms.txt), [Image API](https://anna.partners/developers/reference/host-api-image), [Speech API](https://anna.partners/developers/reference/host-api-audio), [Publishing](https://anna.partners/developers/apps/app-publish).


## Review fixes — 3 November 2026 (v0.1.1)

- Listing expanded into usage, features, cost, persistence and output limitations; two actual hosted-app screenshots included.
- Sticky activity banner with elapsed time, indeterminate waiting indicator and stop control. Encoding reports per-scene percentages. Per-scene image/voice readiness is shown.
- Image generation uses Anna generateAsync/getJob, retaining job IDs and idempotency keys across retries and saved projects. Network polling/download failures retain paid work; terminal provider failures are explicit.
- Model catalog loads automatically. Test-card output is labelled as an encoder test, separately from generated documentaries; obsolete previews are cleared when work changes.
- 30 Node tests and 5 Python tests passed. Anna strict validation passed. Hosted acceptance used one NASA source, one draft/audit pair, one GPT Image 2 (fal) image and four words of Qwen3 TTS Flash narration. No local AI models were invoked.
- Paid assets saved and restored in final draft r10; exported 2.104329-second 1280×720 H.264/AAC MP4, independently decoded without errors and visually inspected for picture/captions/disclosure. Longer and other-provider workflows were not rerun for this revision.
- The reviewers' screenshots did not include the exact AI error. The old synchronous wait was replaced with observable, recoverable jobs; this addresses slow-call failure/recovery but does not establish the original provider-side root cause.

- Resubmission confirmed: v0.1.1 (1912), pending_review, pinned candidate v0.1.1. Both listing JPEG URLs and the v0.1.1 privacy page returned HTTP 200.


## Private studio review — v0.2.1, 3 November 2026

User review requested before another submission. Studio candidate v0.2.1 replaces the compact Anna interface with four numbered sections, visible detailed/stick-figure choices, a custom 5–300 second target, 1–24 requested scene images (long speech may require additional chunks, shown in the plan), scene cards before paid calls, and explicit optional exports. The initial window is larger for the desktop workflow.

The pipeline monitor shows elapsed time, an activity log, completed-asset percentages, encoding progress and the latest completed image. New images/audio are displayed immediately rather than waiting for every scene. Unknown provider-internal progress remains indeterminate. Existing assets are kept on retry; changing a media-setting or narration shows a fresh plan and blocks stale-asset exports. Export-only changes do not buy new media.

Root cause of the drifting/cropped picture: mandatory 6% zoompan plus canvas cover scaling. Default output now uses still images and contain framing, preserving source edges. Crop-to-fill and gentle zoom are explicit opt-in options; zoom is unavailable in whole-image mode.

Verification: 41 Node tests plus 5 Python tests passed; strict Anna validation passed. Hosted-browser 30-second three-scene export used portrait/square/wide synthetic diagnostic cards and ten-second tones, no AI calls. Result: 30.021333 seconds, H.264/AAC 1280×720, 720 picture frames, fully decodes. Every scene retains four coloured corner markers; samples seven seconds apart have mean pixel changes below 0.17/255 (compression noise, no pan/zoom). A real existing Anna illustration and four-word voice clip were restored and exported using the still default: 2.104329 seconds, H.264/AAC 1280×720, decodes successfully. No new hosted AI or local model calls were made for this studio revision. Other-provider and long generated stories were not rerun.

Diagnostics are bounded, in-memory and downloaded only by user action: fixed stage/type, timestamp, duration, counts and allowlisted error code. No script, prompt, source content, URL, media, token or job identifier. Browser download verified 14 safe events, including encoding completion. Local Staso 0.5.26 hooks/profile/credentials were left untouched; automatic hooks and Python instrumentation remain unverified/unimplemented as documented by the user. See .internal/staso-observability-design.md for the content-free integration boundary.

Review artifacts: output/studio-review/studio-preview.png, export-preview.png, still-image-preview.mp4, 30-second-framing-test.mp4 and diagnostics.json. No commits or pushes performed.


## Timing and quota polish — working draft v0.2.2

After the user's live three-scene run completed one image/voice pair and failed with APP_QUOTA_EXCEEDED, the UI was refined to separate overall completed-work percent from current-asset waiting. Per-asset elapsed time and measured successful completion averages are grouped by model/quality; at most twenty timing samples per group stay in local browser storage. There is no invented estimate before the first sample, no provider-internal percent, and no automatic transmission.

Preview/standard/high quality is forwarded to Anna where supported; provider support and latency are explicitly qualified. Quota exhaustion now pauses the workflow with save/check-quota/resume instructions rather than unrelated permissions guidance. Model catalog quota is shown when available, and a zero-quota check precedes new media submission. This cannot guarantee enough quota for the whole plan because provider prices vary. A compact sticky monitor keeps current progress visible in narrow app windows.

48 Node tests pass (including timing isolation, twenty-sample cap, storage denial, quota classification and preview quality forwarding); five Python tests passed in the preceding studio verification. Anna strict validation passed. No new paid AI generation was performed for this polish; hosted visual acceptance still requires opening the updated draft after backing up the user's active project. The open stopped job must not be refreshed before its project is saved.

User-facing records: CHANGE_HISTORY.md and USER_GUIDE.md. Staso runtime instrumentation remains absent; its existing hooks/profile/credentials were not modified. The new browser timing store is not a Staso trace.


Review status update — 3 November 2026: latest working revision r16 was cut as v0.2.2 (1937) and submitted. Anna confirmed pending_review pinned to v0.2.2, replacing v0.1.1. Store metadata and studio screenshots synchronized. Final real multi-scene test remains quota-blocked; this limitation was included in the submitted changelog.
