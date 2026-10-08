# 代码动画

朋友版生成目录只有代码动画和白板；白板转入专用编辑器。

1. `GET /api/generation/catalog` 检查实际运行条件。
2. `POST /api/generation/plan` 创建计划：`title,route:"code-animation",brief,style,character,voice_id,shots`。镜头字段为 `id,narration,visual,action,camera,duration,reference,voice_id,status,review,asset_path`。新镜头 status=planned。
3. Codex 编写自包含动画 HTML。必须定义全局 `window.renderFrame(t)`，不使用网络、外部脚本、定时器和 CSS 墙钟动画。
4. `POST /api/generation/render`：`{plan_id,kind:"code-animation",preview:true,payload:{html,width:1280,height:720,fps:25,duration:6,audio_path?:真实本机音频路径}}`。
5. 查询 `/api/jobs` 的 job_id；实际 MP4、封面、源码和 QA 在任务输出中，作品统一进入 `/library`。长内容拆成镜头，单镜最多60秒。

可选网页自动创作：`POST /api/generation/draft` 和 `/api/generation/compose`，请求 `{plan_id,revision,backend:"auto",preview:true}`。需要已配置编剧。默认未选本地预设时使用 Windows CPU 语音；显式音色沿用对应引擎。

更新计划需携带 `id,revision`，冲突409时读新版本后合并。`POST /api/generation/retry` 仅恢复失败的自动任务，参数 `{job_id}`，沿用原快照。产物自动关联但不自动审阅通过。代码动画 SRT 为按实际音频的镜头级时间，不是逐词对齐或自动烧录字幕。

CLI：`submit generation-plan|generation-render|generation-draft|generation-compose --json 请求文件`；`generation --plan ID` 读计划；`status JOB_ID --wait 60` 查结果。
