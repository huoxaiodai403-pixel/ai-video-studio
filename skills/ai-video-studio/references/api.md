# 本机 API 与 Codex 创作流程

以下命令中的 `CLIENT` 代表本 Skill 的 `scripts/studio_client.py` 完整路径；使用当前机器可用的 Python 3.10+。所有 JSON 文件为 UTF-8。响应保留服务的真实字段，错误输出到 stderr 并以非零代码退出。

```powershell
python CLIENT doctor
python CLIENT list --view products --status all
python CLIENT list --view assets --kind image
python CLIENT voices
python CLIENT models
python CLIENT status JOB_ID
python CLIENT status JOB_ID --wait 45
```

`doctor` 不进行推理；逐项报告服务、白板、配音和配乐的检查结果。一些旧健康检查会同时检查可选的本地编剧和 IndexTTS 环境；Codex 直接写稿不依赖本地编剧就绪。模型文件齐全不代表本轮生成质量已经验证。

## 白板：Codex 写分镜 → 预览 → 渲染

复制 `whiteboard-request.json` 到任务输出目录，编辑旁白和关键词。示例可直接用于预览；渲染依赖本机已配置的配音和字幕模型。支持的布局为 `opening / compare / steps / summary`。每镜头标题最多 36 字、1–3 条关键词，每条最多 24 字；每镜头旁白最多 600 字，全片最多 3600 字。短卡片承载重点，口播承载完整解释。

```powershell
python CLIENT submit whiteboard-preview --json whiteboard-request.json
python CLIENT status 返回的JOB_ID --wait 45
python CLIENT submit whiteboard-render --json whiteboard-request.json
```

顶层可选 `voice_preset_id` 为 `voices` 返回的实际 ID；`characters` 为 `{"主持人":"实际预设ID","来宾":"另一预设ID"}`，分镜用 `speaker` 指定角色。镜头也可使用独立 `voice_preset_id`。省略时使用本机默认音色。不要把示例机的 ID 分享给其他机器。`voice` 仅接受 `speed / emotion / intensity / online_voice`，本流程配音和字幕当前均为 local。

可选 `board_beats` 数量必须与关键词一致，按顺序完整覆盖旁白；改稿后同步调整，或省略让渲染器处理。`board_sticker` 可选 `none / reader / stepper / stuck / panicked`。返回任务中 `previews` 为图片，成片任务还包含 `video / subtitle / sources` 等现存交付 URL。恢复编辑：`/whiteboard?project=JOB_ID`。

## 长片：资料与章节 → 保存 → 素材 → 预览 → 渲染

复制 `investigation-request.json` 并按题材扩充。示例为 `explainer` 方法教学，图解与 `fact_status=analysis` 符合其内容，不伪装新闻调查。

```powershell
python CLIENT submit investigation-save --json investigation-request.json
python CLIENT project 返回的JOB_ID
```

后续 JSON 顶层加 `job_id`；更新稿件后再次 save，避免每次创建重复工程。

`storyboard` 必需字段：`title`、`chapters`、`scenes`。模式 `mode=explainer|investigation`，叙事方式 `narrative_mode=account|cost|rules|process|compare|identity`，`target_minutes` 1–12。1–12 章，1–96 镜头，每镜头旁白不超过 500 字，全片不超过 12000 字。目标时长是制作目标，最终需读取真实音轨与成片时长。

章节 `{id,title,summary?}`；镜头 `{id,chapter_id,narration,speaker?,kind,heading?,points?,source_ids?,fact_status?}`。

- `kind`: `video / image / evidence / diagram`；图解布局填 `diagram_layout=flow|compare|timeline|checklist`，不能写进 kind。
- `sources`: 来源台账数组，包含 `{id,title,url,published_at,content,status}`；日期未知保留空串，URL 可为空用于用户提供资料。状态默认 `unreviewed`；只能根据实际复核结果使用 `source_checked` 或 `user_reviewed`。`source_ids` 只能引用当前台账。正文最多 24 条、单条 16000 字、合计 40000 字。
- 真实事件核验未完成的镜头用 `needs_review`；自己的方法解释用 `analysis`。不能靠批量修改状态绕过内容/来源缺口。
- 图解 `points` 最多 6 条；证据摘录 `text` 最多 1200 字。`visual_brief` 说明画面意图。

获取公开来源可使用自身浏览器/搜索能力，也可 `submit source --json source.json`（文件为 `{"url":"已确定的公开文章地址"}`）。API 无登录态，不能访问需登录或动态页面时使用合法取得的原文；正文输出仅是待复核材料。

导入已获准使用的素材，先保存工程，然后提交：

```json
{"job_id":"实际工程ID","path":"本机现有文件的绝对路径","kind":"video","description":"与该段讲解对应的动作素材"}
```

```powershell
python CLIENT submit investigation-media --json media.json
```

素材 `kind` 为 `video/image/evidence/audio`，响应 `item.id` 放入镜头 `media_id`。剪切起点为 `media_start` 秒；长片检查会报告时长或来源覆盖缺口。资源库条目的 `absolute_path` 可以作为导入路径；文件被复制到该项目目录。需关联事实来源时同时传当前项目已有的 `source_id`，不能复制其他项目的来源 ID。

整片背景音乐使用 `storyboard.bgm={"mode":"media","media_id":"本项目音频ID"}`；无配乐用 `{"mode":"none"}`。`generated` 是工作台的内置生成模式，不等于已自动调用 ACE-Step；要用 ACE-Step 请先独立生成配乐并导入。音效不应冒充整片循环背景音乐。

```powershell
python CLIENT submit investigation-preview --json project-request.json
python CLIENT submit investigation-render --json project-request.json
python CLIENT project JOB_ID
```

保存返回的 `gaps` 需处理；HTTP 422 可能已保存项目并返回 `job_id`，应复用它。渲染已有项目需要完整 `storyboard`，不能仅传 job_id。中断恢复用 `submit investigation-resume`，JSON 仅 `{"job_id":"实际工程ID"}`，会复用原冻结配置；不对已完成工程调用。恢复编辑：`/investigation?project=JOB_ID`。

## 剪映草稿交接

作品需已完成渲染，且工程内有最终视频。先读取状态，不能把音频任务、空草稿或只有预览图的任务直接当作视频工程：

```powershell
python CLIENT jianying status
python CLIENT jianying status --project JOB_ID
python CLIENT jianying export --project JOB_ID --mode auto
python CLIENT jianying open --project JOB_ID
```

路由分别为 `GET /api/jianying/status?project_id=ID`、`POST /api/jianying/export` 与 `POST /api/jianying/open`。导出请求只传 `{"project_id":"实际工程ID","mode":"auto"}`，打开请求只传 `project_id`；不提供项目 ID 的 `open` 仅启动已检测到的剪映。CLI 不接受任意可执行文件、启动参数或输出路径。

状态中的 `installed / executable / draft_root / bridge_ready` 表示安装及桥接环境；`project` 对象里的 `can_export / available_modes / mode_reasons` 决定本工程能用哪种方式。桥接未安装时在工作台根运行 `scripts/Install-JianyingBridge.ps1`，依赖隔离到 `apps/jianying-bridge/.venv`；剪映本体从其官网安装并完成首次启动。`draft_root_source=jianying-settings` 表示已采用剪映中设置的自定义草稿目录。

- `auto` 自动选择可用方式；检查响应中的实际 `mode` 和 `warnings`。
- `scenes` 把保留的镜头、角色配音和字幕组成轨道。白板/讲解镜头没有独立图片或视频时会重建为原生标题、要点文字卡片，可直接改文字；原手绘描边、排版动效和转场不自动迁移。已有图片或视频内部的文字与图形仍属于画面。
- `flattened` 以最终视频交接，保留原画面与混音；不是重新拆出所有角色声音或原始图形。字幕已经烧录的成片不能直接再叠加同一套可见字幕。

导出返回 `draft_id / draft_name / draft_path / mode / tracks / warnings / manifest_url / delivery_dir`，保留这些字段用于后续剪映操作。生成草稿后，再运行 `open`，在剪映中按返回的草稿名打开。`open` 响应 `opened=true` 仅代表启动应用，`draft_opened_automatically=false` 明确表示没有自动进入工程。`desktop_export_available=false` 表示桥接 API 没有自动导出 MP4 的功能，不代表当前 Codex 会话的桌面工具不可用。应用启动、草稿打开和最终导出分别核对。最终 MP4 可保存到响应的 `delivery_dir`，与原工作台工程保持关联。

草稿创建会复制素材，CLI 为该命令默认等待最多 600 秒，其余请求默认 20 秒。可在 `jianying` 前加 `--timeout 秒数` 调整。如果连接中断或超时，先用 `status --project` 查看 `last_export`，不要把未收到响应当成草稿必然不存在。相同素材的重复请求会复用已存在的交接草稿，响应中 `reused=true`；已经在剪映修改过的草稿不会被覆盖。

剪映 MP4 放入 `delivery_dir` 后，再读取项目状态。`last_export.files` 只列出已稳定、未被写入占用且容器可读取的导出文件；仍在写入或不完整的文件列在 `pending_files`，没有交付 URL。文件的 `verification.container_readable=true` 只是容器检查，`visual_review / audio_review=pending` 仍需实际视听，不能自动改称质量通过。

如用户要求剪映最终成片，使用实际可用的 Windows 桌面控制工具完成时间线核对和导出，遇到登录、会员素材或不兼容提示时读取具体原因。新版剪映与社区草稿库须以实际打开结果验证，不降级软件或尝试改写加密旧草稿。修改用户已有剪映项目应先复制保留原版。

## 音色与单项素材

`voices` 返回 `presets / default_preset_id / default_voice / references`。预设内 `voice` 为完整配置。独立配音请求：

```json
{"backend":"local","text":"本次用于试听的短句。","settings":{"voice":{"复制选定预设voice对象的字段":"对应实际值"}}}
```

把上面的说明对象替换成实际 `voice` 对象，再 `submit speech`。本地文本最多 2000 字；`qwen3-design` 首次设计最多 120 字，稳定角色需先试听并保存声音，不逐句重新设计。没有听审依据时不更改全局默认音色。

配乐请求用 `submit music`：

```json
{"engine":"ace-step-1.5","prompt":"Instrumental, calm minimal piano, gentle background for narration, no vocals","duration_seconds":30,"bpm":72,"seed":42}
```

音效同一端点，`engine=stable-audio-3-sfx`、1–15 秒、不要传 bpm。ACE-Step 为 30–60 秒，BPM 40–180。先用 `models` 确认模块安装状态，缺模型不会自动替换到付费服务。

`submit image / motion / transcribe / produce` 可提交工作台对应 API 的请求；这些独立模块参数随版本演进，使用前读取当前 `/api/creation`（`models` 命令输出）和仓库 `scripts/creation_settings.py`、`studio_extensions.py`、`studio.py`。素材路径必须属于当前机器，`backend` 显式选择 `local`。`produce` 的普通分镜模式与上述白板/长片 schema 不同，不混用。

## 状态、交付与复用

`list --status all` 同时列出草稿、预览、完成品和失败工程；默认 `done` 只显示成品。`--kind image|video|audio|music|sfx|speech|whiteboard|investigation` 按用途筛选，`--query` 搜索标题，`--favorite` 仅收藏。统一界面是 `/library`，资源入口 `/assets`，图库 `/gallery`，音频库 `/audio-library`，音色库 `/voices`。

```powershell
python CLIENT item LIB_ID
python CLIENT download --item LIB_ID --output ./delivery/result.mp4
python CLIENT download --job JOB_ID --field video --output ./delivery/video.mp4
python CLIENT download --job JOB_ID --field subtitle --output ./delivery/subtitles.srt
python CLIENT download --job JOB_ID --field bundle --output ./delivery/delivery.zip
```

可选字段来自真实状态对象，或用 `--label` 精确选择 `downloads` 中的交付标签。下载仅允许本服务返回的 outputs/library URL，拒绝外部重定向和覆写现有文件，输出字节数及 SHA-256。`done` 后仍需核查媒体；交付文案、机器验证 JSON 与实际观感属于不同证据。
