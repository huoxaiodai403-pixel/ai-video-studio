# 连续配音到真实成片

## 自定义创作优先

网页默认使用当前文稿生成新画面，不套用下文的固定示例。九种方法在 `/generation?...&method=方法ID` 选择「用我的内容创作」，Simon 在原生白板输入新主题与内容。操作契约见 [自定义制作、角色与交接](../../../docs/production-paths.md)。本页下述 `creative_film.py` 和 `scene_html` 为保留的固定场景 / 手工动画源码生产流程，其 Windows 连续配音限制不适用于新的通用生成工坊。

正式片优先使用用户选择的音色库声音。角色库保留版本、参考图与声线；镜头按实际出场者和说话者绑定。Codex 可以制作 Blender 工程和视频后把各镜路径写回计划，通过 `/api/generation/compose` 的 `source: "supplied"` 合成。保留 `.blend`、脚本和渲染设置；交回视频的合成包不能被描述成自动包含外部 Blender 源工程。



覆盖文章十种方法的本地制作示例：九种由 Codex 编写确定性二维动画、画卷或图像合成，使用 `creative_film.py`；Simon 走原生白板接口。作者安排镜头与动作，执行器保留真实 MP4、配音、字幕、镜头与可编辑来源。各例实际技术及缺少的上游专用能力见 [制作目录](creative-production-catalog.json)，不是 Omni、Flow、Seedance 或三维定格模型的替身；模型角色动作仍走已有图像/短镜头流程。

## 网页制作

从「工作流 → 视频 Skill → 使用此方法」进入，先用示例新建计划。在「生成与结果」启用「按本方法的本地场景制作」，选择已登记素材工程，生成首镜样片或完整视频。九种方法经独立 `creative_method_worker.py` 使用同一配音、真实时间轴与逐帧执行器，无需编剧或本地模型；Simon 的原生白板入口会载入本方法示例。生成结果、逐镜素材、字幕、交付包和继续编辑入口都保留在同一工作台。

网页场景是明确的本地版本：标题与旁白可改，固定画面不会自动理解新的视觉描述。镜头数量、顺序、画面、动作、相机或风格改变时阻止套用旧场景，需切换通用生成或由 Codex 更新模板。需要外部图片与背景音的方法只列出本机 `projects/creative-films` 下同方法、原始输入哈希一致的已有素材工程；未准备的素材不伪装为可用，也不进入软件源码包。

请求在进入队列前冻结来源、模板、素材、文稿与版本，重试校验快照和已生成的声音、视频，拒绝覆盖修改过的文件。方法生成是实际的配音、渲染与合成，不复用旧成片冒充新任务。出片后仍需逐镜审看、实际播放与主观听审。

## 直接制作与续作

从工作台根目录运行，先用 `studio_client.py doctor` 核对当前服务及 CPU 渲染器。相应固定来源资料包须已通过 `creative_video.py verify --recipe 方法ID`；缺少时运行仓库的 `scripts/install_creative_skills.py --skill 方法ID`。命令都面向同一个工作台。

```powershell
& tools/.venv/Scripts/python.exe -X utf8 skills/ai-video-studio/scripts/creative_film.py produce --recipe stickman-video-director --spec examples/creative-films/stickman.json --out projects/creative/my-first-film --wait 60
& tools/.venv/Scripts/python.exe -X utf8 skills/ai-video-studio/scripts/creative_film.py resume --project projects/creative/my-first-film --wait 60
```

`--wait` 结束且任务尚未完成时返回当前阶段，再 `resume`；不重新提交已有 job。`status --project 路径` 只读取本地制作记录。生产目录只能新建，不覆盖已有作品。原稿、画幅、素材、声音和动画源码在开始时冻结；变更创作内容用新的输出目录。

只调整视觉时，在新的 `produce` 命令加 `--reuse-speech 旧工程目录`。仅当逐字原稿、声线、语速、工作台和音频哈希一致时复用原声及时间戳。不会重新设计声音或合成一份近似音轨。两进程不能同时续作一个工程。提交超时且没有收据时停止，先人工核对服务器任务与本地 `dispatching` 记录；不要删除记录后盲目重试。

## 可运行示例与真正的方法差异

| 方法 | 规格 / 动画源码 | 动作与构图 |
| --- | --- | --- |
| 火柴人 | `examples/creative-films/stickman.json` / `.html` | 角色抬脚、落点、重心转移与登阶；全景和脚部特写分别编排 |
| 手绘讲解 | `examples/creative-films/handdrawn.json` / `.html` | 竖屏暖白纸、逐笔容器、沙粒和石头的顺序比喻；准确中文字独立绘制 |
| Vox 拼贴 | `examples/creative-films/collage.json` / `.html` | 透明照片剪贴、纸片、地图、路线和文字各有时序；相机推近与元素运动分开 |
| 花叔机制动画 | `examples/creative-films/huashu.json` / `.html` | 任务、处理节点、积压与节奏匹配，整体、特写和对照分别编排 |
| 纸艺祝福 | `examples/creative-films/papercraft.json` / `.html` | 原创纸兔、信封、蛋糕和折纸心形；固定材质、投影和定格节奏；通用祝福不杜撰姓名年龄 |
| 诗词画卷 | `examples/creative-films/poem.json` / `.html` | 《春晓》逐句四景，镜头固定，独立雨丝、水波与诗句层；不是模型 I2V |
| 人生漫画 | `examples/creative-films/life.json` / `.html` | 职业开场、稳定人物、手部细节和环境收束；原图推拉平移明确属于剪辑运动 |
| 第一人称导演 | `examples/creative-films/director.json` / `.html` | 原创虚构 Storytime；准备、卡壳、折纸、抬头和回看，人物身份与道具连续 |
| 书评 | `examples/creative-films/book.json` / `.html` | 原书核对、原创示意书封、原句与阅读建议分开，整组景别变化与固定字幕安全区 |
| Simon 白板 | `examples/creative-films/simon.json` | 先 `studio_client.py submit whiteboard-preview`，检查布局后 `whiteboard-render`；返回原生 Excalidraw、字幕、横竖封面与有声 MP4 |

前两个示例无需图片、模型或云接口。拼贴示例需要自己的 `assets/bicycle.webp` 透明单车素材；先用内置 imagegen 生成或提供有权使用的素材，检查主体完整和透明边缘，保留原图，再准备较小的视频素材副本。工作台源码包不包含用户图片。不要把缺图换成占位方框，也不要把生成工具安装完成当作素材已就绪。

后六个二维例子包含可选的原创音床。先把需要的 JSON/HTML 复制到新输入目录，然后运行 `python examples/creative-films/make_soundbeds.py --out 新输入目录/assets`；脚本只写新 WAV，不覆盖现有文件。诗词另需 `assets/poem.webp`，人生漫画另需 `assets/comic.webp`，均为**一张 2×2 图集**：按阅读顺序存放四镜，人物身份与风格一致，每格留取景余量，源码在视频中裁切取景。使用内置 imagegen 或授权自有图像；保存原始图，再准备不超过 280 KB 的压缩副本。具体故事原稿、身份及逐镜提示词应随生产工程保留。源包只提供代码，不夹带用户媒体。

更换题材时改写**原稿、逐镜画面和动画源码**；不能仅把示例文字替换后仍让石头/台阶表达无关内容。核对诗文与书籍的示例依据见 `examples/creative-films/content-sources.md`。一个短片示例不代表人生长片、导演所有 Mode、花叔全部动画语法或上游账号服务均已验证。

## 规格与动画契约

规格字段见示例：`title, width, height, fps, speech, scenes, scene_html, assets, style, brief, tail, audio_bed`。文件路径相对规格所在目录，拒绝 `..`、链接/目录联接、网络及盘符路径；先将授权素材放到制作输入目录。1–16 镜、最多 4000 字，实际配音加收尾须不超过 60 秒；超长拆章，不能截断旁白凑片长。默认 25 fps，`tail` 默认 0.6 秒。每镜需独立 ID、原句、具体画面，可补主体动作与运镜。

当前连续配音适配器显式使用 Windows 系统语音。`speech.voice_id`、`speech.speed` 留在不可变规格与音频记录中。**生成工坊计划的 `voice_id` 是本地模型音色预设 ID**，交接时留空；不能填 Windows 名称。本页固定示例的“自动重新配音”使用 Windows 默认声音，精确保留当前声线/语速时用本流程续作、复用原声或在剪辑工作台使用现有片段。

`scene_html` 是自包含 HTML，恰好放一个 `<!-- CREATIVE_FILM -->`，定义 `window.renderFrame(timeSeconds)`；所有动作按传入时间求值，不能使用实时计时器、网络、CSS 动画或页面录屏。画布尺寸与规格匹配，横竖屏分别设计构图。真实时间轴注入 `window.CREATIVE_FILM`：

- `scenes`: 原镜头字段加 `start / end / duration`；场景分界必须落在合成词边界，缺词或词内切段即停止，不按字数估时。
- `captions`: 真实逐词时间戳组成的字幕；Windows 词尾取下一词起点，不声称为声学强制对齐。
- `duration / speech_duration / width / height / title`: 实际音轨和片长。片长按完整帧向上取整，保留末尾停顿。
- `Film.shot(t)` 取得当前镜头、索引、局部时间和进度；`Film.ease` 为确定性缓动，`Film.caption(ctx,t,w,h)` 绘制共享字幕安全区。
- `Film.asset('bicycle')` 返回预载的真实内嵌图片。资产 ID 为小写字母、数字和连字符；单图最多 280 KB，源码与图像总量须符合本机 API 的 500 KB 限制。

`audio_bed` 可指定相对 WAV 路径、`gain`（0–1）、`loop`（布尔）与来源 `credit`。仅接受非空 16 位 PCM 单/双声道 WAV，最多 50 MB。原始 `narration.wav` 不变；另存 `soundtrack.wav`，按实际片长补齐或循环背景音、首尾淡化并限峰。输入音床和混音都进入交付包，不把合成音称为现场录音。改背景音或画面可复用逐字原稿与相同声音；输出被修改时停止而不覆盖。

字幕 cue 在真实合成词边界处平衡分段，画面换行使用中文词边界，避免孤立短尾和行首标点；无法完整拆分的合成整词明确报错，不插值出假时间。

## 交付与验收

`production.json` 保存来源提交、源文件哈希、API 收据、阶段和产物哈希。只在服务器任务 `done`、视频下载、完整音画解码通过后导出逐镜头片段。关联原计划使用 revision；用户已修改新版时保留编辑，记录 `newer_edit_preserved`，不覆盖。生成素材始终为“已生成 · 待审片”，不会替用户标成已人工验收。

输出 `video.mp4 / subtitles.srt / narration.wav / alignment.json / timeline.json / scene.html / scene-template.html / spec.json / scenes/*.mp4 / delivery.zip`。交付包带素材、声音、逐镜片段、可编辑源码和来源元数据。作品库自动发现 SRT、时间轴和交付包，返回真实的作品与原计划链接。归档只写本次匹配视频哈希的任务目录，同名不同内容文件停止，不覆盖。原稿或未授权的用户数据不会纳入源码发布清单。

完成后抽查各镜头中段、动作关键点与末帧；核对文字碰撞、字幕安全区、剪切点、实际帧数和声轨长度；在真实作品库播放至结束并回载原计划。浏览器播放成功和完整解码不等于主观听审。音色自然度、艺术品质与用户认可单独记录，不能拿测试数量替代。
