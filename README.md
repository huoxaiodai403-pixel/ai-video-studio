<p align="center"><img src="assets/brand/studio-mark.svg" width="88" alt="AI Video Studio"></p>

# AI Video Studio

**在本机工作台创作视频，统一管理素材、音色、分镜和作品。**

Windows 优先的本地 AI 视频工作台，提供代码动画、角色短片、循环动画、Blender 镜头预演、手绘白板、热点调查长片、小说转漫剧和通用制片流程。安装源码包含可选模型接入与仍需验证的实验流程。

只维护一个工作台，本地模型按需安装和启用。朋友可以直接使用在线接口、Windows 系统语音、CPU 渲染和已有素材。所有创作入口共享同一份源码，详见[运行方式](docs/editions.md)。

本轮新增[实际视频审片与返修](docs/review-workbench.md)，可慢放、标记问题、保存记录和复制返修说明。收藏文章提到的十类工具已整理为[视频 Skills 来源与接入](docs/video-skills.md)，区分已核实来源、已有引擎与待适配能力。

可以直接在网页中填写需求、生成并修改方案、看样片和制作视频。也可以用 Codex 创作文稿、分镜或直接编写动画，再由工作台渲染；配套 Skill 是可选操作入口。

## 下载与启动

从 [v0.3.1 发布页](https://github.com/huoxaiodai403-pixel/ai-video-studio/releases/tag/v0.3.1) 下载统一工作台；自己和朋友使用同一个安装包，旧版本保留供回退：

- [ai-video-studio-0.3.1-windows.zip](https://github.com/huoxaiodai403-pixel/ai-video-studio/releases/download/v0.3.1/ai-video-studio-0.3.1-windows.zip)：工作台源码、CPU 渲染适配、可选本地模型接入、安装/启动脚本与文档。
- [ai-video-studio-skill-0.3.1.zip](https://github.com/huoxaiodai403-pixel/ai-video-studio/releases/download/v0.3.1/ai-video-studio-skill-0.3.1.zip)：可选的 Codex Skill，需要连接工作台。
- [SHA256SUMS.txt](https://github.com/huoxaiodai403-pixel/ai-video-studio/releases/download/v0.3.1/SHA256SUMS.txt)：下载校验值，可用 PowerShell `Get-FileHash .\ai-video-studio-0.3.1-windows.zip -Algorithm SHA256` 对照。

解压到可写目录，先双击 `Install.cmd`，成功后双击 `Start.cmd`。也可在 PowerShell 中运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-Studio.ps1 -InstallPython
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Open-Studio.ps1
```

默认页面：<http://127.0.0.1:8189/home>。安装器准备网页环境及 CPU 渲染器（Node、npm 依赖、Chromium），**不会默认下载模型权重**。Simon 来自本账号复刻仓库的固定版本，源码、Windows 补丁与字体直接随包分发，朋友无需安装 Git 或另行拉取仓库。只需网页环境时可加 `-SkipRenderers`。默认启动只打开工作台；需要已安装的 ComfyUI / Ollama 时运行 `scripts/Start-Studio.ps1 -StartLocalModels`，也可在本地运行设置中按需启动。

在 Codex 桌面端直接写口播和分镜；当前会话有内置生图工具时，可生成插图后导入工作台，无需另配图像接口。白板预览只需 CPU 渲染器。基础配音与字幕可用 Windows 系统语音离线完成，Edge 可免密钥在线配音；生成式视频和配乐仍需对应工具或已有素材，详见 [快速上手](docs/getting-started.md)。

此包是可安装的源码发行包，不是包含全部模型的离线整合包。空环境能启动工作台，不代表所有媒体引擎已经就绪。

换电脑和旧版升级见 [安装与迁移](docs/deployment.md)，本次修复与验收范围见 [v0.3.1](docs/releases/v0.3.1.md)。

2026-10-12 文档补充：GitHub 下载的 v0.3.1 新包已完成本机隔离安装与三段新内容出片检查，未借用预装 Python 或本地模型；另一台电脑与干净 Windows 虚拟机尚未验收。首次在工作电脑使用请按[部署说明](docs/deployment.md#工作电脑首次部署不安装本地模型)操作。现有 v0.3.1 附件与校验值保持不变。

## 在 Codex 中使用

直接使用网页时，从「工作流 → 生成工坊」开始，详见 [生成工坊](docs/generation-workshop.md)。以下 Skill 安装只适用于希望配合 Codex 的用户。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-CodexSkill.ps1
```

在 Codex 打开解压目录，开始新对话，示例：

> 使用 $ai-video-studio，做一个讲“如何判断一条热点消息是否可靠”的白板视频。先给出分镜，使用平静清晰的中文解说，检查可用引擎后再制作。

> 使用 $ai-video-studio，把这个脚本做成双角色调查长片。先检查来源与素材，保留可编辑工程、旁白和 SRT，成片放入作品库。

> 使用 $ai-video-studio，把刚才的作品送到剪映，保留可编辑轨道，检查后将精修成片放回原作品。

> 使用 $ai-video-studio，直接编写一个解释“先查原始出处”的图形动画，按真实旁白时长安排动作，生成可播放样片并保留源码。

完整入口见 [Skill](skills/ai-video-studio/SKILL.md)。分享单独 skill 时，朋友还需安装工作台；只为文稿、Codex 生图和白板预览，不必安装本地大模型。

## 模块

| 模块 | 用途 |
| --- | --- |
| 工作台 | 从内容目标选择流程，继续最近工程 |
| 我的作品 | 集中查看成片、预览和草稿，搜索、标签、收藏、下载、恢复工程 |
| 资源库 | 图库与视频素材、音频库、音色库、模型库 |
| 工作流 | 组合制作、生成工坊、手绘白板、热点长片、小说转漫剧、通用视频制作 |
| 创作工具 | 图像、动态镜头、配音、音乐音效、字幕、画质增强 |
| 在线服务 / 本地模型 | 分开管理账号、接口与本机引擎；实际输出验证和预览 |

成果自动进入统一作品管理；可复用画面和音频进入资源库。选择图片可带入参考生图、动态镜头或调查长片；长片可按全片、角色和镜头设置音色。

## 可选引擎

“工作流 → 组合制作”可把 HyperFrames / Remotion 动效、素材剪辑、字幕译配、产品演示与截图演示串联为真实任务。运行 `scripts/Install-VideoTools.ps1` 安装固定版本组件；默认不下载模型。无需模型时，选择在线来源、系统语音或现成素材。执行方式、例子和当前验证边界见 [视频 Skills 接入](docs/video-skills.md)。

| 用途 | 已接入的引擎 |
| --- | --- |
| 图像 | Qwen-Image 2512、FLUX.2 klein 4B 参考图编辑 |
| 动态镜头 | Wan2.2 5B、Wan2.2 A14B |
| 配音 | Windows CPU 系统语音；Edge、火山及兼容在线语音；可选 Qwen3-TTS / IndexTTS |
| 字幕 | Qwen3-ASR、Qwen3 ForcedAligner |
| 音乐与音效 | ACE-Step 1.5、Stable Audio 3 |
| 文稿辅助 | Codex 对话；ChatGPT 官方账号授权或 API Key；可选 Ollama 与原文分段 |
| 动画与合成 | 自包含 HTML/Canvas/SVG 逐帧动画、Blender 几何预演、Simon 白板适配、Remotion 调查片、FFmpeg |

图像、视频、配音、识别工具也可配置兼容在线接口。具体能力取决于提供方，配置会保存在朋友自己的电脑；本仓库没有 API 密钥。

## 边界与交付

- 长片按章节和镜头制作；不保证一句话无需审阅即可生成可靠的十分钟内容。
- 需要对事实来源、人物一致性、配音听感和字幕进行实际审阅。
- 分享包不带原作者个人作品、参考照片、克隆录音、凭据、模型权重或私人笔记。
- 不自动公开发布视频。工作台默认仅绑定本机环回地址，不应直接暴露到公网。
- 剪映草稿交接与成片回收：在“我的作品 → 送到剪映精修”生成草稿；剪映内的编辑、导出由用户或具备桌面工具的 Codex 完成。首次交接若缺剪映，Skill 会先询问是否安装，同意后安装官方客户端及桥接。手动运行 `scripts/Install-JianyingBridge.ps1` 也会在缺客户端时提示。见 [剪映接入说明](docs/jianying-windows.md)。

## 文档与开发

- [快速上手](docs/getting-started.md)
- [换电脑安装、迁移与安全软件拦截](docs/deployment.md)
- [生成工坊与代码动画](docs/generation-workshop.md)
- [本地模型与依赖](docs/local-models.md)
- [结构与数据流](docs/architecture.md)
- [上游项目与出处](docs/references.md)
- [第三方许可证](NOTICE.md)

应用源码与 skill 使用 MIT 许可证。第三方模型、字体、依赖与内容各自遵循原许可证。
