# Third-party notices

The workbench application and its Codex skill are MIT licensed. This does not
change licenses of dependencies, downloaded models, media or fonts.

- Whiteboard workflows bundle a runtime subset from
  [huoxaiodai403-pixel/simon-skills](https://github.com/huoxaiodai403-pixel/simon-skills),
  a fork of [trustfuture/simon-skills](https://github.com/trustfuture/simon-skills),
  MIT, copyright 2026 trustfuture. The full license is `apps/simon-skills/LICENSE`;
  `SOURCE-MANIFEST.json` in that directory records the revision and checksums.
  `workflows/simon-windows.patch` is already applied to the bundled runtime.
  The four bundled stickers are public upstream example assets, not user projects.
- The bundled Xiaolai font uses SIL Open Font License 1.1, retained at
  `apps/simon-skills/skills/whiteboard-video/assets/fonts/OFL.txt`.
- The Volcengine speech adapter follows the MIT Simon TTS integration's
  protocol, with app-scoped Windows credential storage and timestamp validation.
  `edge-tts` is installed separately under its own license; it uses an online
  speech service and is not an offline model. Windows speech uses installed
  system voices. No private voices or credentials are redistributed.
- The investigation renderer retains its specific attribution at
  `apps/investigation-renderer/NOTICE.md` and the complete upstream MIT license at
  `apps/investigation-renderer/LICENSE.simon-skills`.
- Bundled Noto Sans SC fonts are under SIL Open Font License 1.1. The full notice
  is at `apps/investigation-renderer/fonts/LICENSE.OFL.txt`.
- The optional Jianying draft bridge installs [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft)
  0.3.0 separately under its [Apache-2.0 license](https://github.com/GuanYixuan/pyJianYingDraft/blob/main/LICENSE).
  It is a community library, not a Jianying official API; Jianying itself is not redistributed.
- Remotion, React and other npm/Python packages remain under their own licenses.
  The package manager installs their notices together with dependencies.
  Review [Remotion's license](https://www.remotion.dev/license) for your use.
- ComfyUI, Ollama, Qwen, FLUX, Wan, ACE-Step, Stable Audio and IndexTTS are optional,
  separately installed components. This release redistributes no model weights
  and does not grant rights to third-party voices, photos or generated content.

The share packages exclude local projects, recorded voices, registered reference
images, credentials, private notes, caches, logs and machine-specific QA evidence.
