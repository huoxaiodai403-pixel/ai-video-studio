# 本地模型与渲染依赖

工作台把界面环境与各推理引擎分开。仅安装轻量网页环境就能打开模块、编辑分镜、
管理素材和配置在线工具；本地生成需要相应应用、依赖、模型组件全部到位。

## 渲染器

`scripts/Install-Renderers.ps1` 是可选的渲染依赖安装入口，安装脚本会输出实际
下载内容。它准备 Node、Simon 白板源码与 Windows 适配、浏览器渲染依赖和
调查视频渲染器，不下载 AI 模型权重。基础安装器会通过 imageio-ffmpeg 准备
本地 FFmpeg；安装渲染器前需要 Git，且应先完成基础安装。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-Renderers.ps1
```

安装后先检查 `/api/whiteboard/status` 与 `/api/investigation/health`，再做一个
少镜头预览。文件检查通过不等于整条有声制片已经通过。

## 引擎布局

| 引擎 | 运行目录 / 组件 | 对应功能 |
| --- | --- | --- |
| ComfyUI | `apps/ComfyUI`，GGUF 等所需自定义节点，`models` 下完整图像/视频组件 | Qwen / FLUX / Wan |
| Qwen3-TTS | `apps/qwen-tts/.venv` 与 `models/Qwen3-TTS-12Hz-1.7B-*` | CustomVoice、VoiceDesign、Base |
| IndexTTS | `apps/index-tts/.venv` 与其 checkpoints | 备用配音 |
| Qwen ASR/Aligner | 按配置指向完整权重目录，并准备识别/对齐的独立推理环境 | 字幕与真实时间轴 |
| ACE-Step 1.5 | `apps/ace-step/.venv` 与 `models/ACE-Step-1.5` | 配乐 |
| Stable Audio 3 | `apps/stable-audio-3/.venv` 与该适配器要求的权重 | CPU 短音效 |
| Ollama（可选） | `apps/Ollama` 或本机服务，接口与模型名称在设置中指定 | 本地辅助写稿 |

各引擎的精确组件清单以 `scripts/model_profiles.py`、对应 worker 的 `readiness()`
及模型库状态为准。完整模型安装本身不在轻量分享包的一键安装范围内。
可让 Codex 根据朋友电脑的 GPU、显存与系统逐项部署，不要复制另一个人的虚拟环境。

## 选择原则

- 先确认主要目标：白板讲解通常不需要同时安装大型图生视频模型。
- 图像参考编辑需要 FLUX 完整组件；普通 Qwen 图像配置不能直接替代该输入能力。
- Wan A14B 比小模型等待更久，需要两套噪声模型与对应文本编码器、VAE。
- Qwen3-TTS 固定音色不需要个人克隆参考录音；可先使用内建声线做短句试听。
- GPU 推理按串行阶段运行。工作台使用 GPU 锁，手动在外部应用跑模型仍可能争用显存。
- 大文件、下载来源及权重许可由所选模型决定，安装前查看上游说明。

同一台电脑上的模型目录与当前默认值不会随源码发布。`config/creation.json`
由本机生成，密钥配置也需要朋友自己填写。

## 在新电脑重建就绪记录

配音和音乐模块的就绪记录必须由新电脑实际检查产生。不要复制作者电脑上的
`installation.json` 或 `*.import-probe.json`，也不要手工把 `ready` 改成 `true`。
先按对应官方项目准备独立环境、固定版本代码和模型，再运行以下命令：

```powershell
# Qwen：实际导入 qwen_tts、torch、torchaudio、soundfile、transformers。
.\tools\.venv\Scripts\python.exe .\scripts\verify_local_engines.py --engine qwen

# ACE：实际导入官方 handler、LLM、inference 与 torchao 等依赖。
.\tools\.venv\Scripts\python.exe .\scripts\verify_local_engines.py --engine ace

# SFX：实际导入 LiteRT 等 CPU 依赖，并逐一核对已安装的三个权重 SHA256。
.\tools\.venv\Scripts\python.exe .\scripts\verify_local_engines.py --engine sfx --verify-models
```

检查子进程禁用 GPU、禁止模型联网下载，不加载推理模型或合成音频。成功后在本机生成：

- Qwen：`apps/qwen-tts/installation.json`；已有来源信息会保留。
- ACE：`manifests/ace-step.import-probe.json`。
- SFX：`manifests/stable-audio-3.import-probe.json`，以及权重旁的 `.verified.json`。

这些记录仅说明依赖可导入，模块仍独立检查模型和必要许可文件是否完整。未安装环境时，
检查会报告缺失并退出，不会凭空创建“已就绪”记录。

ACE 的公开模型清单在 `examples/model-plans/ace-step-1.5.json`，包含固定上游提交、
组件名、大小和哈希，没有本机验收路径。核对磁盘空间和下载体积后，可单独执行：

```powershell
.\tools\.venv\Scripts\python.exe .\scripts\download_model_plan.py .\examples\model-plans\ace-step-1.5.json
```

这条命令会下载清单中的大型模型，仅在显式运行时执行。它不安装 ACE Python 环境，
也不自动改其他模型配置。SFX 使用 `scripts/stable_sfx.py` 中固定的模型、代码提交与
文件 SHA；保留 `models/Stable-Audio-3-Optimized/licenses/LICENSE.md` 和
`LICENSE_GEMMA.md` 后再检查。本页没有承诺任意新版本代码可兼容这些固定适配器。

只选 Qwen 配音时不要求安装 IndexTTS。选择 IndexTTS 音色，或同片混用两种引擎时，
才需要对应的 IndexTTS 环境与参考音频。完成准备后先试听一句，再跑完整视频。
