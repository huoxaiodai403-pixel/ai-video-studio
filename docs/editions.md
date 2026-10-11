# 一个工作台，按需选择运行方式

不再维护完整版和朋友版。所有安装使用同一份页面、接口和创作流程，本地模型作为可选后端。

| 运行方式 | 需要准备什么 |
| --- | --- |
| Windows 系统配音、CPU 渲染、剪辑、导入素材 | 工作台与对应 CPU 渲染组件，不需要 AI 模型权重 |
| 在线编剧、图像、动态、配音和识别 | 在设置中配置对应接口，按任务选择在线来源 |
| 本地编剧、图像、视频、配音、字幕、音乐与增强 | 按需安装独立运行环境和模型；使用现有 GPU 锁 |

安装器默认不下载模型。普通启动只开工作台，不自动启动 ComfyUI / Ollama；需要时使用本地运行设置，或运行 `scripts/Start-Studio.ps1 -StartLocalModels`。`-WorkbenchOnly` 继续兼容。

生成工坊与调查长片可以明确选择 Windows 配音；音乐页可以直接复用已有音频。并非所有模型能力都有在线替代，依赖未安装时会报告具体缺项。旧工程已经选择的后端、参考录音和角色声线不会自动换掉；想改为系统旁白时需在工程中明确选择。

分发只使用 `packaging/source-profile.json` 的明确源码清单，不再应用朋友版覆盖模板。源码包包含可选模型接入代码，不包含权重、个人工程、配置、密钥、参考录音与机器日志。旧 `EDITION=friend` 标记作为兼容输入，不再限制功能；内部 `development` 标记仅用于保持已有草稿命名空间。

从 [v0.3.1](https://github.com/huoxaiodai403-pixel/ai-video-studio/releases/tag/v0.3.1) 起公开提供统一工作台安装包。历史双版本下载保留供回退；新安装请选择无 friend / development 后缀的 Windows 包。

[快速上手](getting-started.md) · [审片与返修](review-workbench.md) · [视频 Skills 来源与接入](video-skills.md)
