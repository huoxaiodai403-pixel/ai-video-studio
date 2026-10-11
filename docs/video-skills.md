# 视频 Skills 的组合制作

自定义主题、角色库、ComfyUI 与 Codex / Blender 的交接操作，见 [制作方式与角色](production-paths.md)。


新增收藏文章里的艺术动画、拼贴、手绘、火柴人、纸艺、诗词、人生故事、导演与书评方法，见 [视频文章的创作方法](creative-video-methods.md)。主 Skill 统一选型并交接现有工具，花叔参数图表已有 CPU 适配器。

工作台入口：`/video-tools`。组合制作使用统一工作台，可选择在线接口、系统配音、已有字幕或已安装的本地模型。安装 Skill 源码不等于安装模型。

页面可以从作品与资源选择素材，安排步骤，执行任务、预览并下载成片，继续编辑原方案或把结果交给下一份工程。每次制作创建新工程，冻结输入文件，保留中间产物与日志；失败后修改方案重新制作，不覆盖原件。完成后进入审片，机器渲染完成不会自动标为质量通过。

## 已接入的执行方式

| 能力 | 工作台实际执行 | 上游与边界 |
| --- | --- | --- |
| HyperFrames | HTML + GSAP → 上游 CLI → MP4 | [heygen-com/hyperframes](https://github.com/heygen-com/hyperframes)；可载入示例或使用 Codex 编写的 composition |
| video-use | 字幕 + 剪辑要求 → 工作台编剧选段 → FFmpeg 剪切 | [browser-use/video-use](https://github.com/browser-use/video-use) 的 Windows 工作流适配；识别/编剧复用工作台接口，不运行其 ElevenLabs 专用整套 CLI。也可直接提供 cuts |
| Remotion | React TSX / 内置模板 → bundler + renderer → MP4 | [remotion-dev/skills](https://github.com/remotion-dev/skills)；支持标题、参数、上一阶段图片与单文件 TSX |
| ffmpeg-skill | 上游 cut.py 精确切段 → 工作台画幅、速度、音量、拼接与混音 | [kajisho5/ffmpeg-skill](https://github.com/kajisho5/ffmpeg-skill)；不需要 AI 模型 |
| agent-caption | 已有 SRT / cues，或在线、Qwen、WhisperX 识别 → 字幕文件与烧录 | [ahkamboh/agent-caption](https://github.com/ahkamboh/agent-caption)；选 WhisperX 时才运行上游 caption.py，其他来源复用工作台适配 |
| video-subtitle-translator | 工作台编剧逐段翻译 → 保留时间轴 → SRT/VTT 与可选烧录 | [alwaysmavs/agent-skills](https://github.com/alwaysmavs/agent-skills/tree/main/skills/video-subtitle-translator) 的流程适配，不依赖另行登录 OO CLI；也支持现成译文 |
| video-dubbing | 原字幕 → 译文 → 逐段 TTS → 时长匹配 → 新音轨与可选字幕 | [renky1025/agent-skills](https://github.com/renky1025/agent-skills/tree/main/video-dubbing) 同名来源；Windows 使用工作台语音后端替代 MLX，配音替换原音轨 |
| app-demo-agent | 录屏 + 旁白 → 系统/在线/本地配音 → 补边、合成与可选音乐 | [michaelboeding/skills](https://github.com/michaelboeding/skills/tree/main/skills/app-demo-agent) 的 Windows 适配；旁白留空时由支持图片的编剧接口读取真实关键帧。当前使用简洁背景补边，未接入上游完整设备框库 |
| browser-video-recording | 真实截图 + 光标/点击/缩放时间线 → 上游 Python renderer → MP4 | [MengTo/Skills](https://github.com/MengTo/Skills/tree/main/agent-skills/codex/browser-video-recording)；Windows 使用中性光标素材。是截图演示，不是自动连续录屏 |
| imagegen | 导入 Codex 已生成图片或调用已配置在线生图 → 传入后续动效 | [OpenAI imagegen](https://github.com/openai/skills/tree/main/skills/.system/imagegen)；复用当前 Codex 能力，不重复安装。网页不能直接调用聊天中的 image_gen 工具 |

字幕翻译与配音串联时，同目标语言直接复用上一步译文。剪辑改变时间轴后，旧字幕不会被继续套用；需重新识别或传入新时间轴字幕。视频用实际媒体时长校验字幕，配音过长或过短会停止并提示调整，不把溢出的声音截掉冒充完成。

## 安装与版本

准备 Git，并在工作台安装 Python、Node/npm 后运行 `scripts/Install-VideoTools.ps1`。它从 `workflows/video-tools.json` 的固定提交安装上游源码到 `tools/video-skills`，并安装固定版本 HyperFrames、Remotion、React、GSAP 和 FFprobe 到 `tools/video-runtime`。先尝试 Git SSH，再回退公开 HTTPS；已有不同来源目录不会自动覆盖。首次渲染可能下载 Chromium；这不是 AI 模型权重。

安装器默认不下载模型。需要本地字幕时再使用 `-IncludeLocalCaption` 安装独立环境。第三方源码与运行依赖不直接打进源码分享包；各自许可证以固定提交为准。该目录是工程依赖，不是全局 Codex Skills 安装目录。

## Codex 提交与交接

1. GET `/api/video-tools/catalog` 检查组件和来源配置。
2. 生成 `title`、可选本机绝对路径 `source` 和 `steps`。每步是 `skill` 与结构化 `options`。字段约束见 `scripts/video_tools_api.py`，可运行示例见 `examples/video-tools-pipeline.json`。
3. POST `/api/video-tools/run`；或执行仓库 Skill 客户端：`python skills/ai-video-studio/scripts/studio_client.py submit video-tools --json examples/video-tools-pipeline.json`。用 `AI_VIDEO_STUDIO_URL` 指定本机服务地址。
4. GET `/api/video-tools/project?id=返回的job_id` 查看进度、可编辑方案、下载链接和作品 ID。`status=done` 后检查真实媒体。也可用客户端 `status JOB_ID`。
5. 从作品库继续剪辑或进入审片。失败日志、阶段产物和输入快照保存在该工程；重试创建新版，当前没有自动从任意失败步骤续跑。

页面只提交结构化参数，不接受任意 shell 命令。HTML/TSX 是本机用户或 Codex 编写的可执行模板，应检查来源。原文件只读，最终 MP4、SRT/VTT、request.json 与 stages.json 可下载。

## 2026-10-09 验证边界

开发环境已经实际渲染：HyperFrames、Remotion、FFmpeg 剪辑加字幕、Windows 中英文配音、产品演示、真实浏览器截图演示。页面提交的 Remotion 任务已生成 MP4 并接入作品库与审片。

当前源码环境未配置在线编剧、ASR、TTS、生图，也未安装本地识别/配音模型。自动选段、自动翻译、自动画面写稿、在线生图与本地模型分支已接入，缺配置时在提交前检查；这些外部推理调用尚未通过真实服务验收。手工提供的字幕和译文不算自动识别/翻译验收。听感、翻译质量、产品演示叙述仍需人工审看。

## 草稿与编辑恢复

组合制作支持“保存草稿”，未选素材或尚未配置服务时也可保存。草稿更新携带版本号，旧页面不能覆盖新版本；已执行工程另存新草稿。草稿保存在本机工程目录，可从作品库的草稿筛选重新打开。

“检查制作条件”只验证输入、所需依赖和配置，不执行生成。剪辑后的已知时长会用于后续字幕校验。字幕编辑器可逐段编辑原文/对应译文，读取 UTF-8 SRT；系统和 Edge 音色使用当前可用列表。

执行过程显示每一步及已完成的真实产物。“使用工程保存的素材副本”只替换当前仍引用原路径的素材，保留当前字幕和参数修改；适用于原素材移动后的重新制作。它不是从失败步骤断点续跑。

API：POST `/api/video-tools/draft` 接收 `{request, id?, revision?}`；POST `/api/video-tools/check` 接收制作请求；POST `/api/video-tools/subtitles` 接收 `{path}`；工程 GET 同时返回步骤产物和可复用的快照。

## 剪辑工作台界面（2026-10-09）

- `/video-tools` 使用已选定的第 3 张视觉方案：素材库、实际画面预览、字幕/配音/制作步骤面板及画面、配音、字幕三轨。
- 点击字幕段可定位、修改文本与起止时间；播放位置可分割当前字幕。保存草稿或制作时会同步尚未点击“应用”的输入。
- 字幕修改写入制作方案，下次制作时合入新成片；预览明确显示已制作版本，不伪装为实时重新渲染。
- 画面轨展示当前合成范围，配音轨展示方案旁白；本版本不提供任意多素材拖拽拼接、真实波形或逐轨静音/锁定。裁剪使用实际保留片段参数。
- 常规素材通过文件选择导入。支持 MP4、PNG、JPG、WebP，单文件 32 MB；更大素材可在制作设置填写本机路径。`POST /api/video-tools/import` 接收 `{name,base64}`，验证实际媒体后写入 UUID 目录，只进入资源库，不伪装为生成作品。
- 完整制作方案、各步骤参数与组件状态在“制作设置”；下载与审片入口在“结果与导出”。
- 桌面布局与窄屏布局共用实际生产接口。动效采用 100–200 ms 的按压、选中与面板进入，支持 `prefers-reduced-motion`。
- UI 图标使用 [Feather v4.29.2](https://github.com/feathericons/feather) 的官方图形，许可随 `video-tools.js` 保留；不依赖远程 CDN。
- 统一剪辑界面支持在线与 CPU 制作，本地模型按需安装。
