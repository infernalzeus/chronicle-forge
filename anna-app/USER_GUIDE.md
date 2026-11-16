# Chronicle Forge on Anna — using it and keeping evidence

## Make a video

1. **Set up:** enter a topic, a custom duration and the requested scene-image count. Choose detailed illustrations or stick figures. Preview quality is an economical starting point where the selected provider supports it; it does not guarantee a faster response.
2. **Review:** research the topic, select relevant evidence, draft/audit, then edit and approve the narration. Target duration is approximate; the finished video follows actual voice length.
3. **Build scenes:** review the plan and available quota, then generate. Each scene needs an image and a voice clip. They appear as each asset completes. More images mean more paid calls.
4. **Export:** choose still whole-image framing (recommended), create the MP4, preview it and download. Subtitles, thumbnail, source notes and a resumable project are separate optional downloads.

Image count is not frame rate. The video is encoded at 24 frames per second. Very long narration can require additional scene chunks to respect speech-provider limits; the actual planned count is displayed before generation.

## Understand the progress display

- **Overall completed work:** counts ready images and voice clips. Three scenes = six media assets. One finished image and one finished voice = 2/6, or 33%.
- **Current asset:** queued/running state and elapsed time. Anna's documented image-job response supplies state, phase and optional queue position, not a reliable internal completion percentage or intermediate image.
- **Recent average:** measured successful timings for the same model and quality, with sample count. Before the first sample, the UI says there is no measured estimate. Queue time, provider load and content can change the result; resumed/download-only assets do not establish a fresh full-generation average.
- **Encoding:** uses the encoder's real per-scene progress. It is separate from image generation.

## If quota runs out

Do not refresh or close the app. Open **Optional · extra downloads and backup → Save resumable project**, then download diagnostics. Your project includes completed image/audio bytes and pending image-job identifiers. Diagnostics exclude scripts, prompts, sources and media.

Check Anna's Subscription & Usage page for quota availability. Do not repeatedly click Generate while quota is exhausted. Resume later with the same narration, models, quality, style and scene count so completed assets can be reused. Changing those media settings creates a new plan; changing only framing/resolution does not require buying new media.

## Keep a review packet for each important run

Save these yourself; the app does not publish a gallery or record the desktop automatically:

- Resumable project: private backup containing the actual script and completed media.
- Finished MP4 and an optional thumbnail: the demonstration output.
- Diagnostics JSON: stage timings/counts/error codes, without content.
- A screenshot of the result/error, if useful.
- A short note: app version, settings, expected result, actual result, and what needs changing. Keep private source material out of shared reports.

Use CHANGE_HISTORY.md to compare versions. Current screenshots and verified sample videos are under output/studio-review. Those local review artifacts have not been automatically published to partners.

## Staso

Staso 0.5.26 installation/configuration is separate from Chronicle Forge runtime tracing. No integration to Staso was added here. Guard/content-capture settings were not changed; automatic Codex hooks remain unverified, and the Python pipeline remains uninstrumented. Browser diagnostics are not proof of Staso delivery. No credentials are embedded in the Anna app.
