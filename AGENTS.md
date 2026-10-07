# Working in AI Video Studio

This repository is a Windows-first local media workbench. For creating a video,
read `skills/ai-video-studio/SKILL.md`; use Codex to develop and review the script
and storyboard, then call the local workbench for generation and rendering.

For code changes, inspect the affected API and its tests. Keep model workers
isolated from the lightweight HTTP/UI environment. Use paths derived from the
repository root and preserve existing project files and per-job settings.

Useful checks:

```powershell
& tools/.venv/Scripts/python.exe -m unittest discover -s scripts -p 'test_*.py'
```

Local model execution is expensive and optional. CPU/API checks do not establish
media quality; when a request needs generation, inspect the actual outputs and
report remaining listening or review boundaries accurately. Follow the existing
GPU lock when using local workers.

Do not commit `config`, `projects`, models, voice samples, reference media or
machine logs. Distribution is built from the explicit source-file list in
`packaging/build_release.py`. Public release authority is request-scoped.
