---
name: ai-video-studio
description: 通过本机 AI 视频工作台创作代码动画、手绘口播、纸张拼贴、火柴人、纸艺祝福、古诗词、人物故事、书评、白板和资料长片。根据视频文章选用创作 Skill，编写口播与分镜，调用已有媒体后端渲染、管理作品或交接 Windows 剪映。Skill 是可选入口，网页也可直接创作。
---

# AI 视频工作台

本 Skill 是工作台的可选对话入口，适合在 Codex 中创作或分享给朋友，不是使用工作台的前提。用户直接用网页时，应优先走 `/generation` 的“输入需求 → 生成方案 → 样片 → 成片”，使用工作台已配置的编剧、音色和模型，不要求复制指令、手写 JSON 或来回传文件。

统一工作台保留所有创作入口，本地模型按需安装和启用；未安装模型时使用系统语音、在线接口、CPU 渲染或导入素材。外部视频 Skills 的实际来源、依赖与适配边界见 [视频 Skills 接入](references/video-skills.md)。按交付物选择主工具；不能把外部 Skill 安装成功视为网页 worker 已接入。视频生成后从作品库进入 `/review?id=作品ID`，逐项审看并保存时间标记；返修保留音色、角色和不相关镜头，生成新版后重新审看。

用户选择在 Codex 中创作时，Codex 可以理解需求、查资料、写口播、设计分镜和检查成片；工作台执行生成并统一管理作品。可直接提交结构化稿件，避免重复调用编剧。需要插图、封面或角色图时，可以使用当前会话实际可用的内置生图工具并导入真实文件，也可使用工作台已有模型。沿用用户选择，不强制切换工具或后端。

## 开始创作

用户提到 X 收藏中的视频文章、花叔、Vox、手绘、火柴人、纸艺、诗词、模拟人生、导演或书评方法时，先读 [视频文章创作方法](references/creative-recipes.md)，选择与作品目标匹配的方法，再按本文调用已有执行接口。用 `scripts/creative_video.py list` 查看十种方法与能力边界；需要原始详细方法时从固定版本资料包读取对应文件。`prepare` 可把选定方法写入真正可提交的工作台计划，`chart` 可将花叔图表参数编译为代码动画请求。十种方法的本地制作示例及能力边界见 [制作目录](references/creative-production-catalog.json)；九种二维/图像合成路线的连续配音、真实时间轴、背景音混合、逐帧渲染、字幕和源码交付用 [成片制作流程](references/creative-production.md)，支持中断续作和视觉返修复用原声。不能只给文章摘要或安装清单就视为制作完成。

运行本 Skill 的 `scripts/studio_client.py doctor` 检查当前服务和依赖。脚本只使用 Python 3.10+ 标准库；优先使用工作台 `tools/.venv/Scripts/python.exe`，否则使用有效的 `python` 或 `py -3`。`AI_VIDEO_STUDIO_URL` 默认为 `http://127.0.0.1:8189`，仅接受本机地址。可设置 `AI_VIDEO_STUDIO_ROOT`，也会从当前目录和 Skill 位置向上发现工作台；不依赖固定盘符。

服务未启动时，在已找到的工作台根目录使用 `scripts/Start-Studio.ps1`。服务可用时以 doctor 的 `root_source=running-service` 和 `root` 为准，避免把源码目录当成正在运行的解压目录。诊断命令不会启动服务、下载模型或生成内容。v0.2.1 起工作台包内包含 Simon 白板源码、Windows 补丁、中文字体及公开贴纸；Node/npm/Chromium 由 `scripts/Install-Renderers.ps1` 安装。依赖未齐时先按用户任务补足对应模块，不默认安装全部大模型。

## 优先使用 Codex 与现有素材

文稿、分镜直接在对话中完成；白板图形与预览用 CPU 渲染器即可，不依赖生图模型、配音或密钥。内置生图可用性以朋友的当前会话工具为准，计入其 Codex 使用额度；工作台网页无法自行调用桌面聊天工具。需要图片时由 Codex 生成并交接本地文件，具体导入方式见 [API 与创作流程](references/api.md#codex-内置生图与素材导入)。

先检查当前会话的实际媒体工具与 doctor 返回的 checks.speech。基础配音可使用 Windows 系统语音（CPU、离线、无需模型权重）；正式创作优先保留用户选择的音色或已配置的 Qwen3 等声线，并以当前文稿试听；想要在线音色时可选择 Edge（联网、免密钥），或用户已配置的火山语音。三者复用同次合成的时间戳，无需另装 Whisper。Windows 记录词起点，词尾取下一词起点，不能称为声学强制对齐。OpenAI 兼容 TTS 若要字幕，还需支持逐词时间戳的 ASR；本地高级声线保留独立模型流程。详见 API 说明，不用估计时间冒充真实对齐。网页编剧可用工作台自己的官方 ChatGPT 授权，仅用于文稿与分镜；不读取 Codex 或其他插件凭证。

依据用户要做的内容选择流程，详细字段和可执行命令见 [API 与创作流程](references/api.md)：

- **生成工坊**：`generation` 读取六条路线及实际环境，`generation --plan ID` 读取创作计划。`submit generation-plan` 保存；`generation-draft` 由工作台编剧写分镜；`generation-compose` 自动执行配音与画面生成；`generation-render` 是高级素材/HTML/白模参数入口。网页是默认使用入口，`generation --plan ID --handoff` 仅在用户要交接给 Codex 或朋友时使用。代码动画、角色叙事、关键姿势循环与 Blender 白模各有明确能力边界，见 [生成工坊 API](references/generation.md)。

- **组合制作**：网页 `/video-tools` 把动效、剪辑、字幕、译配、产品演示和视觉素材串成工程。先查 `/api/video-tools/catalog`，依据实际可用后端选择步骤；客户端 `submit video-tools --json 方案.json` 实际执行。支持 HyperFrames HTML、Remotion 单文件 TSX、已有视频、SRT、字幕段落和截图；详细字段与执行边界见 [视频 Skills 接入](references/video-skills.md)。图片工具的产物必须是实际本机文件；不能把网页接入等同于能直接调用聊天工具。失败修正后提交新版，成功输出交给审片。

- **手绘白板**：短知识讲解、步骤对比；1–8 个镜头，直接写 `storyboard`，先预览再渲染。参考 [白板请求示例](references/whiteboard-request.json)。
- **资料长片 / 机制讲解**：章节、来源台账、证据或动态素材；先保存项目，再导入素材、补齐覆盖、预览、渲染。参考 [讲解请求示例](references/investigation-request.json)。该示例约一分钟，仅用于验证流程；十分钟成片需要实际足量的口播、素材和音轨验证。
- **素材 / 角色声音**：从 `list --view assets` 和 `voices` 读取现有内容。选本机实际返回的音色 ID；按角色映射，而非每句重新设计声音。需要独立生图、动态镜头、配乐或音效时按 API 指南单独提交，再复用到工程中。
- **剪映精修**：先 `jianying status`。`installed=false` 时主动询问“是否现在安装剪映专业版并配置桥接”；用户已同意则继续，不重复确认。获准后在实际工作台根目录运行 `scripts/Install-JianyingBridge.ps1 -InstallJianying -NonInteractive`；若已安装但 `bridge_ready=false`，直接运行同一脚本的 `-NonInteractive` 模式补桥接。用户拒绝安装则保留工作台交付物。检查首次启动和草稿目录，再 `jianying status --project 工程ID`，按可用模式 `jianying export`、`jianying open`。详见 [剪映草稿交接](references/api.md#剪映草稿交接)。

创作时保留用户选定的题材、音色和模型。没有明确风格偏好时采用自然、清楚的表达。把要呈现的事实与自己的解释分开；真实事件用实际查看过的来源，不能把抓取成功或模型生成视为事实核查。虚构教学例子需在稿件和画面明确标注。


## 自定义内容与共享工程

十种文章方法必须围绕用户本次主题、原稿与角色重新制作。固定示例不能充当换内容验收。网页方法入口默认「用我的内容创作」；只有用户明确选择示例复刻时才使用固定场景。

角色库使用 `/api/characters`，保存外貌、服装、参考图与音色的版本。生成计划使用 `cast`，镜头使用 `character_ids` 与 `speaker_id`；小说 / 通用制作 / 资料长片通过角色库入口带入固定版本。参考图最多四张，ComfyUI 的参考图路线使用本地 FLUX.2 klein。没有真实参考图时不得宣称身份一致已经锁定。

用户可选择网页 / ComfyUI 自动制作，也可让 Codex 接管同一计划。需要 Blender 时保留完整建模、材质、灯光、动画与 `.blend`，导出真实视频；现有 `blender-previs` 只是几何预演。把实际镜头路径保存到 `asset_path`，随后调用 `/api/generation/compose`，使用 `source:"supplied"`、计划 ID 和最新版本，工作台用选定声音、真实字幕对齐统一合成。已交回短视频会停在末帧以覆盖旁白，长视频按旁白裁尾，输入原声不保留；特殊节奏和混音使用剪辑工作台。

网页帮助见工作台 `docs/production-paths.md`；API 字段见 [生成工坊接口](references/generation.md)。交付应分别说明新内容是否出片、ComfyUI 是否真正推理、Blender 是否实际渲染、逐镜画面与声音是否检查，不能以说明文档或编译成功代替。

## 生成与交付

提交后记住 `job_id`，使用 `status` 查看进度。HTTP 202 只是排队；只有 `status=done` 且目标媒体存在才算产出。长片的 `save` 或 `preview` 完成也不是成片完成。失败时检查 `error`、`phase`、`gaps` 和工程记录，修正具体问题，不循环重复提交。

长片修改已有项目必须携带 `job_id`，保存后的快照和导入素材都属于该项目；跨项目复用需重新登记，不能照抄别处的 `media_id`、`source_id`。修订已交付的作品时另建项目或先保留旧版。显卡任务顺序提交，遵守工作台 GPU 锁；不要为提速绕过互斥或停止用户正在运行的任务。

完成后检查关键画面、文字排版、字幕时间及结尾，抽听多处配音，查看最终分辨率、帧率和时长；区分机器检查与实际视听。无法播放时如实说明，不声称音质或画面已经人工验收。导出 MP4、字幕及 API 提供的交付包/可编辑源文件，并给出 `/library` 和相应工程链接。

剪映桥接使用社区草稿格式；不改写既有剪映工程。`jianying export` 生成的是草稿，`jianying open` 启动的是应用，两者都不是剪映已导出 MP4 的证明。需要完整剪映成片时，继续用当前会话实际可用的 Windows 桌面工具打开对应草稿、检查时间线并导出；以导出文件及视听检查为准。没有桌面工具或遇到版本不兼容时报告具体边界，保留已生成草稿与素材，不套用旧版自动导出脚本反复点击。

该 Skill 的提交和下载都面向本机工作台。公开发布作品、上传第三方平台、付费云推理或分享私人参考声音，需要用户的相应任务授权。不会通过本 Skill 自动发布。
