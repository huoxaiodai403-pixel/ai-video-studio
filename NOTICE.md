# Third-party notices

The workbench application and its Codex skill are MIT licensed. This does not
change licenses of dependencies, downloaded models, media or fonts.

- Whiteboard workflows adapt [trustfuture/simon-skills](https://github.com/trustfuture/simon-skills),
  MIT, copyright 2026 trustfuture. The upstream source is obtained separately;
  `workflows/simon-windows.patch` records Windows integration changes.
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
