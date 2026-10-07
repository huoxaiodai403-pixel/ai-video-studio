<p align="center"><img src="assets/brand/studio-mark.svg" width="88" alt="AI Video Studio"></p>

# AI Video Studio

**用 Codex 编排创作，在本机工作台管理素材、生成画面与声音、合成视频。**

Windows 优先的开源 AI 视频工作台，提供手绘白板、热点调查长片、小说转漫剧和通用制片流程。配套 Codex skill 可以检查环境、读取作品、提交分镜、查询任务和取得交付文件。

Codex 负责选题、文稿、分镜和审阅；工作台负责可重复执行的媒体任务。你仍可以在网页中调整画面、旁白、角色音色和字幕。

## 下载与启动

在 [Releases](https://github.com/huoxaiodai403-pixel/ai-video-studio/releases) 下载：

- `ai-video-studio-0.1.0-windows.zip`：工作台源码、安装/启动脚本、Codex skill、公共示例与文档。
- `ai-video-studio-skill-0.1.0.zip`：单独分享的 Codex skill；需要连接已安装的工作台。
- `SHA256SUMS.txt`：下载校验值。

解压到可写目录，在 PowerShell 中运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-Studio.ps1 -InstallPython
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Open-Studio.ps1
```

默认页面：<http://127.0.0.1:8189/home>。安装器先准备轻量网页环境，**不会默认下载模型权重**。第一次生成前按 [快速上手](docs/getting-started.md) 配置在线接口，或按 [本地模型说明](docs/local-models.md) 准备对应引擎。

此包是可安装的源码发行包，不是包含全部模型的离线整合包。空环境能启动工作台，不代表所有媒体引擎已经就绪。

## 在 Codex 中使用

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-CodexSkill.ps1
```

在 Codex 打开解压目录，开始新对话，示例：

> 使用 $ai-video-studio，做一个讲“如何判断一条热点消息是否可靠”的白板视频。先给出分镜，使用平静清晰的中文解说，检查可用引擎后再制作。

> 使用 $ai-video-studio，把这个脚本做成双角色调查长片。先检查来源与素材，保留可编辑工程、旁白和 SRT，成片放入作品库。

完整入口见 [Skill](skills/ai-video-studio/SKILL.md)。分享单独 skill 时，朋友还需安装工作台和实际使用的媒体引擎。

## 模块

| 模块 | 用途 |
| --- | --- |
| 工作台 | 从内容目标选择流程，继续最近工程 |
| 我的作品 | 集中查看成片、预览和草稿，搜索、标签、收藏、下载、恢复工程 |
| 资源库 | 图库与视频素材、音频库、音色库、模型库 |
| 工作流 | 手绘白板、热点长片、小说转漫剧、通用视频制作 |
| 创作工具 | 图像、动态镜头、配音、音乐音效、字幕、画质增强 |
| 设置 | 在线提供方、运行状态和模型默认参数 |

成果自动进入统一作品管理；可复用画面和音频进入资源库。选择图片可带入参考生图、动态镜头或调查长片；长片可按全片、角色和镜头设置音色。

## 可选引擎

| 用途 | 已接入的引擎 |
| --- | --- |
| 图像 | Qwen-Image 2512、FLUX.2 klein 4B 参考图编辑 |
| 动态镜头 | Wan2.2 5B、Wan2.2 A14B |
| 配音 | Qwen3-TTS CustomVoice / VoiceDesign / Base、IndexTTS |
| 字幕 | Qwen3-ASR、Qwen3 ForcedAligner |
| 音乐与音效 | ACE-Step 1.5、Stable Audio 3 |
| 文稿辅助 | Codex；也保留可选 Ollama 编剧和原文分段 |
| 合成 | Simon 白板适配、Remotion 调查片、FFmpeg |

图像、视频、配音、识别工具也可配置兼容在线接口。具体能力取决于提供方，配置会保存在朋友自己的电脑；本仓库没有 API 密钥。

## 边界与交付

- 长片按章节和镜头制作；不保证一句话无需审阅即可生成可靠的十分钟内容。
- 需要对事实来源、人物一致性、配音听感和字幕进行实际审阅。
- 分享包不带原作者个人作品、参考照片、克隆录音、凭据、模型权重或私人笔记。
- 不自动公开发布视频。工作台默认仅绑定本机环回地址，不应直接暴露到公网。
- Windows 可以通过桌面自动化或社区草稿工具与剪映配合；本发行版不承诺内置新版剪映一键导出。见 [剪映接入说明](docs/jianying-windows.md)。

## 文档与开发

- [快速上手](docs/getting-started.md)
- [本地模型与依赖](docs/local-models.md)
- [结构与数据流](docs/architecture.md)
- [上游项目与出处](docs/references.md)
- [第三方许可证](NOTICE.md)

应用源码与 skill 使用 MIT 许可证。第三方模型、字体、依赖与内容各自遵循原许可证。
