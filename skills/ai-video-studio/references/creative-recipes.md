# 视频文章到实际创作

本页把 X 收藏文章中的十个项目转成工作台创作路由。来源为 [xaiwind 的视频 Skill 汇总](https://x.com/xaiwind/status/2108866001672741199)，逐项上游、固定提交和文件 Git blob 哈希见 [creative-sources.json](creative-sources.json)。原文章只读；流量、收益、模型排行和价格不作为能力证明。

采用其中的叙事、分镜、素材组织和动画方法。上游个人默认项、账号流程与平台选择不覆盖用户已选的语言、画幅、角色、声音、工具和任务授权。用户要求成片时继续到实际媒体；只要提示词时交付提示词。已有足够信息就推进，不照搬上游反复确认的交互。

## 选择方法与执行路线

| 方法 ID | 任务与需要落实的方法 | 工作台执行 |
| --- | --- | --- |
| `huashu-art-motion` | 机制、数据与艺术动画；具体对象和动作先于装饰，稳定色板与媒介，逐镜重新构图 | 参数图表走本页 `chart`；其他原创动画走 `code-animation`，不宣称全引擎已适配 |
| `vox-director` | 拼贴讲解/产品故事；先完整拼贴静帧，再分别设计相机与纸片动作；全景与细节承担不同信息 | 已有图像/视频后端或真实素材 → 组合制作；不自动调用 Atlas Cloud |
| `hand-drawn-video-prompts` | 中文口播配手绘蜡笔画；按论点、因果与例子换镜，每镜一个可视隐喻，提示独立完整 | 静帧 → 短镜头 → 配音/字幕；精确中文、数字与 Logo 用后期层 |
| `stickman-video-director` | 火柴人叙事/解释；通过角色的具体动作表达认知变化；写清起始、行动、反馈与末态 | 角色参考 + 当前视频后端；不用固定英语、十秒片长覆盖用户需求 |
| `kid-papercraft` | 纸艺生日/祝福；登场、个性祝福和温暖收尾，固定纸材、比例与光线 | 纸艺静帧 + 短镜头 + 中文配音；姓名和年龄来自用户，字幕后期制作 |
| `classical-poem-silk-video` | 诗词国风；通读全诗再分景，每景对应诗句、名物、层次与一个主动作 | 生图 + 可用动态图像后端/导入视频 + 诗句文字层；保留环境声，不启用上游 Docker/账号流程 |
| `hbg-life-simulation` | 人物漫画故事；保存原稿与角色设定，真实配音定时间，按情绪/行动变化换镜，检查长镜缺图 | 资料长片或组合制作；静图推拉和平移明确标为剪辑运动 |
| `simon-skills` | 白板/证据资料片；一条解释主线，关键词和关系逐步出现，长片另做证据与覆盖台账 | 现有白板与资料长片流程；不重复安装或替换已适配 Simon worker |
| `director` | 个人经历、知识解释或戏剧冲突；先分模式，再分开人物身份参考、风格规则与每镜场景 | 角色/音色库 + 当前媒体后端；相邻镜头不重启已完成动作 |
| `book-sales-video` | 书评/图书推荐；核对原书事实，保留已确认口播，整组规划景别与视角，固定字幕安全区 | 真实书封/素材 + 连续配音 + 组合制作/剪映；不把上游 macOS OpenChatCut 当成本机功能 |

资料包在 `<工作台>/tools/creative-skills/<方法 ID>/`，保留原仓库相对目录。入口位置见清单的 `entry`。选好方法后读该入口及本次需要的引用，不一次加载所有文档：

- 花叔：`references/09-视频动画语法.md`、`references/动画语法/t3_finance_chart.md`；其他语法和风格配方按需读取。
- Vox：`references/beat-layer.md`、`references/prompt-guide.md`；分层拼贴再读 `references/local-engine.md`。
- 手绘：`hand-drawn-video-prompts/references/style-guide.md`、`automation-workflow.md`。
- 火柴人：`skills/directing-stickman-videos/references/storyboard-template.md`、`style-catalog.md`；模型提示契约只用于实际选择的模型。
- 纸艺：`skills/kid-papercraft/SKILL.md`。
- 诗词：`skill/classical-poem-silk-video/references/style-and-scene-mapping.md`。
- 人生故事：`references/storyboarding.md`、`visual-system.md`、`style-system.md`。
- Simon：`skills/whiteboard-video/references/dsl.md` 或 `skills/investigation-video/references/long-form-workflow.md`；执行仍读本工作台 API。
- 导演：所选 `modes/<mode>/workflow.md` 和 `references/video-generation-prompt-guide.md`。
- 书评：`references/copywriting-and-storyboard.md`、`shot-planning.md`、`bilingual-subtitles.md`。

## 当前网页与素材交接

先用「用我的内容创作」保存新主题与完整原稿，再生成和核对分镜。不要仅替换固定示例旁白。每次提交冻结文稿、任务设置、音色和角色版本；参考图只用于身份，新的构图与动作仍需重新生成并实际审看。角色参考的图像叙事会使用本次编剧服务整理清晰的画面指令，记录原回复；未改写用户旁白。

Codex 与 ComfyUI 共用同一工程。纸艺或其他三维动画可以用 Blender 制作真实场景，渲染为镜头视频后填写 `asset_path`，再提交 `source: "supplied"`；此时不重新调用编剧和生图服务。配音、字幕和交付遵循 [生成工坊 API](generation.md)。主流程优先使用已选本地高质量声音；以下无需模型的命令示例明确选择 Windows 作为基础演示，不作为正式配音建议。

## 共同制作契约

1. 保存原文、事实来源和创作目标；明确输出时长、画幅和已有素材。缺少会实质改变作品的信息才询问，已有选择不重新问。
2. 分开稳定规则（人物、材质、字体、颜色、声音）与逐镜变化（景别、构图、动作、情绪）。不用同一版式换文案凑成片。
3. 每镜保存原句、画面职责、具体主体、动作起点/结果、运镜、真实参考路径与声音角色。模型生成提示逐镜自包含；不能用不存在的参考文件占位。
4. 配音后读取实际时间戳，再对齐画面、字幕和音效；预估秒数只用于前期规划。字幕按语义断句，留统一可读区域，不用单纯固定字数切尾。
5. 先出能代表风格、人物和转场的短段，再制作全片。看实际画面、抽听配音、检查片头/中段/结尾与字幕，返修只重做相关镜头。B 站剪辑文章的“真实音轨作主时钟、先短段验证”方法沿用于此，[来源](https://x.com/q936941441/status/2104908688138150145)。
6. 保存计划、提示、素材、产物和来源；区分资料已安装、接口已适配、真实出片、视听审核和用户接受。影片艺术色板不修改工作台 UI 设计系统。

## 安装与核对原始方法资料

在工作台根目录运行，只下载固定提交中的白名单文档、许可证和已审查的图表代码，不执行上游安装器，不下载模型/音色/示例人物或修改凭据：

```powershell
& tools/.venv/Scripts/python.exe -X utf8 scripts/install_creative_skills.py
& tools/.venv/Scripts/python.exe -X utf8 skills/ai-video-studio/scripts/creative_video.py verify
```

只需一种时加 `--skill huashu-art-motion`。已有资料与固定哈希不同会保留并报错，不覆盖本地编辑。十个根许可证为 MIT；作者演示角色、笔画数据和字体有独立许可，未纳入本资料/代码白名单。更新提交时重新审查，不能只换版本号。

## 建立可提交的创作计划

先用 `studio_client.py doctor` 确定实际服务根路径，再把用户稿件保存为 UTF-8 JSON，例如：

```json
{"title":"让素材跟上叙事","brief":"解释为什么每个镜头都要有对应素材。","style":"暖白纸与深青色图形","voice_id":"","speech_backend":"windows","image_backend":"online","shots":[{"id":"shot-01","narration":"先理清叙事，再逐镜补齐素材。","visual":"分镜表从缺图到逐项对应","action":"依次补齐镜头并停在完整表格","camera":"固定","duration":6}]}
```

```powershell
& tools/.venv/Scripts/python.exe -X utf8 skills/ai-video-studio/scripts/creative_video.py prepare --recipe huashu-art-motion --json brief.json --out projects/creative/my-new-film
& tools/.venv/Scripts/python.exe -X utf8 skills/ai-video-studio/scripts/studio_client.py submit generation-plan --json projects/creative/my-new-film/generation-plan.json
```

`prepare` 只创建全新目录，保留原稿、声音、后端与分镜，向创作要求附加方法；执行边界、固定来源和输入哈希单独记入 `source-record.json`。未指定时新草稿默认系统语音与在线图像来源，提交付费生成前仍需相应授权。返回的计划 ID 进入网页生成工坊。`knowledge-film` 和 `whiteboard` 继续用专用 API，不把通用计划已保存当作已渲染。已有计划沿用原 revision 更新，不通过本命令复制覆盖。

上面的系统配音 JSON 仅用于无需模型的基础检查。正式创作先在音色库试听，再明确传入 `speech_backend:"local"` 与实际 `voice_id`；不要为了方便改掉用户选好的声音。网页会优先使用已准备的本地声线。`prepare` 同时登记 `method_id`，并保留 `production` 与 `cast`；作品库可按方法找回这些新主题工程。

## 花叔参数图表的实际渲染

已适配 `t3_finance_chart` 的柱状与折线图：坐标/标题先出，数据生长，再突出一个观察。输入数据不改变，只改变呈现时间。必填标题、单位、来源；教学数值应像 [示例](huashu-chart-example.json) 一样显著标明“演示数据”。单镜 1–8 秒、2–16 点，支持横竖画幅、命名色板、上下字幕安全区；超长内容拆镜。

保存上一步返回的 `gen-...` ID 后：

```powershell
& tools/.venv/Scripts/python.exe -X utf8 skills/ai-video-studio/scripts/creative_video.py chart --spec skills/ai-video-studio/references/huashu-chart-example.json --plan gen-这里替换为实际ID --out projects/creative/my-new-film/render-request.json
& tools/.venv/Scripts/python.exe -X utf8 skills/ai-video-studio/scripts/studio_client.py submit generation-render --json projects/creative/my-new-film/render-request.json
& tools/.venv/Scripts/python.exe -X utf8 skills/ai-video-studio/scripts/studio_client.py status 返回的job_id --wait 60
```

只在 `done` 后读取作品库、MP4 与 QA。源码保留上游许可证、提交与参数，可继续编辑。适配器嵌入已校验图表代码，沿用现有离线 Chromium/FFmpeg worker，不运行上游 HTTP 服务或 XHR/eval 加载器，不改工作台主进程。

默认静音；需要声音时先走工作台配音，把实际音频路径写入 `audio_path`，按真实声轨安排 cue 和 duration。超出八秒应拆镜，不能静默截掉口播。采用 Windows 系统字体替代上游字体，不承诺跨机器像素一致，换机检查中文字形和排版。K 线、外部图片/帧序列、数字滚动 cue 和全套艺术风格尚未由此适配器开放。

## 交付边界

十种方法都有[实际出片流程与示例](creative-production.md)，可执行入口、素材要求和能力边界收录在 [制作目录](creative-production-catalog.json)。九种采用连续配音驱动原创二维代码或图像合成，导出 MP4、SRT、逐镜片段与源码包并回接原计划；Simon 使用原生白板流程，交付有声 MP4、可编辑 Excalidraw 场景、时间轴和封面。代码动画支持中断续作、视觉返修复用原声与可选自制音床，字幕按真实合成词边界组织。

这十条本地制作路径不等于上游所有模型、子模式或长片质量均已验证。古诗与人生漫画样例使用真实生成的静态图组加代码合成，并非模型 I2V；音床为自制合成声音，系统配音的主观听感仍需审听。资料下载完成不能把 Atlas Cloud、Omni、Seedance、Flow 或 OpenChatCut 标成可用。沿用 `api.md`、`generation.md`、`video-skills.md` 的调用字段，不照搬 macOS 路径或账号脚本。渲染后进作品库与审片台，交付可播放视频和可编辑源文件。
