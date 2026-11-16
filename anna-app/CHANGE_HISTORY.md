# Chronicle Forge — what changed

Last updated: 3 November 2026. This records verified repository history, Anna versions and work in this conversation; it is not a reconstruction of every change over the past few months.

| Stage | What it offered / what changed | Status and evidence |
|---|---|---|
| Original desktop v0.0.1, 30 June | Local Python pipeline. Later desktop UI had live logs, a six-step progress bar, elapsed time, scene-image previews, refined/stickman styles and local model support. | Git commits 9cc55e0 and 715cae4. The desktop code remains separate. |
| Desktop UI tweak, 15 October | Latest existing Git checkpoint before this work. | Git commit 5b1536b. Git does not provide a detailed month-by-month record beyond these few checkpoints. |
| Initial Anna adaptation, 30 October | Research and script preview first; not yet the complete video workflow. | Superseded by full Anna app. |
| Anna v0.1.0, 31 October | Added hosted research, script/audit, image, voice, MP4, subtitles, thumbnail and project recovery. Replaced local AI calls with Anna services. | Candidate 1847. Rejected by Anna: listing screenshots, unclear progress, AI/output problems. |
| Anna v0.1.1, 3 November | Async recoverable image jobs, visible status/elapsed time, automatic model catalog, listing screenshots, expanded description, clear test-card labels. | Candidate 1912. Submitted for review. The review remains pinned here unless explicitly resubmitted. |
| Private studio v0.2.0 → v0.2.1, 3 November | Four-step UI; prominent detailed/stick-figure choices; custom seconds and scene-image count; plan before paid generation; immediate per-asset previews; completed-work percentages; optional downloads; still whole-image export by default. Prevented exporting old assets after settings changed. | Candidates 1927 and 1928, private and not resubmitted. 46 automated tests; 30-second diagnostic video; existing real illustration/voice export. |
| Current local polish after quota incident | Current-asset elapsed time, measured per-model/quality timing averages, preview/standard/high quality where supported, clearer quota pause, zero-quota check, compact sticky monitor for narrow windows. | Uploaded as private working revision r16 (app.json v0.2.2), awaiting hosted visual review after the active project is backed up. No new paid AI generation performed to test them. |

## What was restored, and what was not rolled back

- Restored the *visibility and feedback* of the original UI: live image previews, progress representation, style choice and logs. The Anna implementation is new browser code, not a rollback to the Python UI.
- Detailed and stickman styles already existed in the first full Anna code, but were poorly surfaced. They are now prominent choices.
- Custom duration and scene-image count are new Anna controls. The original desktop form exposed duration; the first Anna UI offered presets and chose scene count automatically.
- Removed mandatory zoompan and fill cropping as defaults. Still whole-image mode preserves image edges. Fill/zoom remains opt-in.
- Kept source selection, human script approval, resumable paid assets, hosted-model support and software MP4 export.
- Did not add direct Ollama/local-image access to the Anna iframe. Local model support remains in the separate desktop app. No local model was run.

## Evidence and limits

- 30-second framing test: portrait, square and panoramic synthetic cards, with quiet tones. 720 expected picture frames; all four corner markers retained; no visible within-scene movement. This is a diagnostic test, not a generated documentary showcase.
- Real-media preview: reused an existing Anna image and four-word speech clip. No additional paid generation was needed.
- User-observed three-scene run: scene 1 image and approximately 15-second voice completed; scene 2 image submission hit APP_QUOTA_EXCEEDED. Overall work was 2/6 assets (33%). No final MP4 existed for that incomplete run.
- We did not establish the exact provider-side cause of Anna's original AI failure: reviewer screenshots did not include its error code.
- The new timing averages do not expose provider diffusion steps or internal generation percent. They summarize measured successful completion times only.

## Tracking boundaries

App diagnostics are local, content-free downloads. The activity log and current project stay in the open window; completed work must be saved explicitly. Timing averages alone may persist in this browser. Staso hooks were configured separately by the user; this work has not enabled or verified their execution and has not instrumented the Python pipeline.

Recent source changes remain uncommitted in Git. Anna's immutable candidates preserve their app bundles, but do not replace a complete source-control history. No Git commit or push was performed.


Review status update — 3 November 2026: latest working revision r16 was cut as v0.2.2 (1937) and submitted. Anna confirmed pending_review pinned to v0.2.2, replacing v0.1.1. Store metadata and studio screenshots synchronized. Final real multi-scene test remains quota-blocked; this limitation was included in the submitted changelog.
