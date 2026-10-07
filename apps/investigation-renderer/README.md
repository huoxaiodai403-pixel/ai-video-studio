# AI Video investigation renderer

This is a separate, data-driven Windows renderer. It adapts the collage styling
and brand mark from `trustfuture/simon-skills` without modifying that checkout.
It does not contain the upstream cake story, amounts, narration, or source claims.

The renderer uses Remotion **4.0.508** and React **19.2.8**, bundled Noto Sans SC
fonts, and the existing Playwright Chromium. No model or GPU inference is needed.
Chromium defaults to software rendering and H.264 encoding uses the CPU.
`--gl angle` permits GPU browser compositing; use it after model inference has
released the shared GPU lock, not concurrently with TTS or alignment.

## Commands

Run from the AI-Video workspace (paths may also be absolute):

```powershell
tools/node/node.exe apps/investigation-renderer/render.mjs video --props PROJECT/props.json --public-dir PROJECT/public --output PROJECT/video-silent.mp4
tools/node/node.exe apps/investigation-renderer/render.mjs still --props PROJECT/props.json --public-dir PROJECT/public --frame 60 --output PROJECT/frame-60.png
tools/node/node.exe apps/investigation-renderer/render.mjs cover --props PROJECT/props.json --public-dir PROJECT/public --ratio 3:4 --output PROJECT/cover-3x4.png
tools/node/node.exe apps/investigation-renderer/render.mjs cover --props PROJECT/props.json --public-dir PROJECT/public --ratio 4:3 --output PROJECT/cover-4x3.png
tools/node/node.exe apps/investigation-renderer/render.mjs validate --props PROJECT/props.json --public-dir PROJECT/public
```

`video` is silent by default; the workbench mixes final narration/music afterward.
`--with-audio` optionally includes the `narration` asset. Still and cover output
is PNG. Covers are **editorial layouts using supplied media**, not AI-generated
images. A separate image-generation stage can replace them in a publishing pack.

Optional arguments: `--concurrency 4` (1–8), `--gl swangle|angle`, `--scale 1`, `--browser CHROME_EXE`,
`--overwrite`. Existing outputs are preserved unless `--overwrite` is explicit.
The browser can also be configured by `INVESTIGATION_CHROME`; otherwise the
renderer locates the existing whiteboard Chromium under `cache/ms-playwright`.
It never downloads a browser silently.

Outputs receive a `.render.json` sidecar. Progress is JSON Lines with stages
`bundle`, `render`, `done`; errors exit nonzero. Each invocation uses a unique
temporary bundle and writes its final output only after successful rendering.

## Props contract

All video/scene/caption times are **integer frames at 30 fps**. Caption `end` is
exclusive. Scenes cover the full timeline continuously, starting at frame zero.

```json
{
  "title": "Topic title",
  "brand": {"signature": "Your account", "accent": "#10C46F"},
  "width": 1920,
  "height": 1080,
  "fps": 30,
  "durationInFrames": 300,
  "scenes": [{
    "id": "s001",
    "startFrame": 0,
    "durationInFrames": 300,
    "kind": "video",
    "media": "assets/clip-001.mp4",
    "mediaStart": 0,
    "heading": "A concrete observation",
    "badge": "Source footage",
    "text": "A short explanatory overlay",
    "points": [],
    "sourceLabel": "Publisher · source description",
    "sourceDate": "2026-10-07",
    "speaker": "Optional attribution"
  }],
  "captions": [{"start": 12, "end": 100, "text": "Actual spoken sentence."}],
  "narration": "narration.wav",
  "coverSubtitle": "Optional cover subtitle"
}
```

- `kind`: `video`, `image`, `evidence`, `diagram`.
- `media` is a physical file inside `--public-dir`, using `/` separators. URLs,
  absolute paths, traversal and symlinks outside that directory are rejected.
- Videos must actually cover `mediaStart + durationInFrames`. Metadata is checked
  in the browser before a render. A short source fails; it is never looped.
- For already trimmed video assets, use `mediaStart: 0`. Source audio is muted.
- Video `layout`: `auto` (default), `full`, `collage`, `portrait`. Auto embeds
  portrait media in a framed collage; landscape media fills the screen. Portrait
  backgrounds use a static gradient to avoid decoding the same video twice.
- Evidence may omit media only when explicit excerpt text is provided. The
  workbench verifies this text against its source before rendering.
- `points`: up to six strings or `{ "title": "...", "text": "..." }` objects.
  Diagram scenes need explicit points or text. No values are invented.
- Text is never truncated. Loaded-font layout is measured; content that would
  need to shrink below 66% of the designed size fails with a scene identifier
  and asks the editor to split the scene or shorten overlays. API text limits
  are ceilings, not a guarantee that every combination fits one screen.
  Scene text accepts up to 1200 characters, badges 80, source dates 100, headings
  100, and source labels 160; the shared API may apply tighter limits. Captions
  accept 120 characters, normalize whitespace, and cannot be blank.
- `diagramLayout`: `flow` (default), `compare`, `timeline`, `checklist`.
  Flow draws directional connections between compact nodes, including the row
  turn when there are more than three points. Compare puts the first half of
  points on side A and the remainder on side B; supply points in that order.
  Timeline alternates labels around an ordered axis; checklist reveals check
  marks beside individual entries. Numbers such as 01/02 mark order only; no
  dates, amounts, percentages or causal text are inferred.
- A point string can use `小标题｜一句短解释` (ASCII `|` also works). Only the
  first separator is split; the rest of the explanation is preserved. Short
  words use compact nodes instead of large empty paper cards. For explicit
  objects, `title` and `text` stay separate without parsing.
- The prototype `diagramStyle` is accepted for compatibility (`list` maps to
  `checklist`); an explicit `diagramLayout` takes precedence. The workbench API
  uses `diagram_layout` and the pipeline converts it to this camelCase field.
- Diagram content stays above y=840 of the 1920×1080 design canvas, leaving
  the lower source and subtitle zones clear. Dense point descriptions may
  require splitting a scene to retain readable type.
- Narration and captions must correspond to the same final audio. The renderer
  does not estimate subtitles from text length or synthesize/modify voices.

## Validation boundary

The included tests check input paths, scene coverage and caption ordering. Real
long-form acceptance still needs complete decode, source coverage/uniqueness
statistics, subtitle/audio checks, and visual/playback review. An encoded MP4
does not by itself verify factual claims or editing quality.

Install only in this isolated directory using the locked dependencies:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/Install-Renderers.ps1
tools/node/node.exe --test apps/investigation-renderer/contract.test.mjs
```

See `NOTICE.md` and `LICENSE.simon-skills` for upstream attribution.

Reports include separate bundle/setup/render timings. Measure representative
scenes on the target machine before estimating long-form production time.
