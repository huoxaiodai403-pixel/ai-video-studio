# 生成工坊

工作台可独立使用；本页只是 Codex 或脚本操作的可选入口。网页 `/generation` 可输入需求、选择音色、生成并编辑分镜、看样片、生成成片。不需要为了生成而复制交接指令。

## API

- `GET /api/generation/catalog`：路线、方法来源、实际渲染组件与编剧配置状态。配置存在不保证远端推理成功。视频文章的十种创作方法与可执行交接见 [视频文章创作方法](creative-recipes.md)。
- `POST /api/generation/plan`：创建或更新计划。创建字段 `title,route,brief,style,character,voice_id,shots`。更新携带 `id,revision`，冲突返回 409；不要覆盖另一个窗口的更新。
- `GET /api/generation/plan?id=gen-...`：读取已存计划。
- `POST /api/generation/draft`：`{plan_id,revision,backend:"auto"}`；工作台已配置编剧输出可编辑镜头。auto 优先已配置的在线编剧，否则已配置本地编剧。
- `POST /api/generation/compose`：`{plan_id,revision,preview:true,backend:"auto"}`。用现有编剧与媒体服务自动制作。代码动画先合成所选声音，再以真实音频时长生成画面。请求时冻结音色与设置。
- `POST /api/generation/retry`：`{job_id}`。仅恢复失败的自动制作任务，复用原始计划与设置快照和已完成素材；采用新计划时应另建任务。
- `POST /api/generation/render`：`{plan_id,kind,preview:true,payload:{...}}`，供高级用户导入自包含 HTML、关键姿势或几何预演参数。
- `GET /api/generation/handoff?id=...`：可选给 Codex/朋友的创作指令。

异步操作返回 `job_id`；通过 `/api/jobs` 或 client `status` 追踪，不能把 202 当完成。成片、样片、计划统一进入 `/library`。`preview` 为样片，`quality_review=pending` 表示仍需实际审看。

## 数据

route：`code-animation`、`character-story`、`character-loop`、`blender-previs`、`whiteboard`、`knowledge-film`。最后两项继续使用现有专用工作流。

每镜字段：`id,narration,visual,action,camera,duration,reference,voice_id,status,review,asset_path`。duration 为估计；生成后读取实际声轨。默认声线为空时沿用当前设置，逐镜声线覆盖全片声线。status 为 `planned/generated/needs-fix/approved`，只有真实媒体加明确审阅记录才可保存 approved，文件存在不能代表质量已通过。

高级 render payload：

- code-animation：`html,width,height,fps,duration,audio_path?`。自包含 Canvas/SVG/DOM，定义 `window.renderFrame(t)`，用秒数确定帧；不允许网络、外部脚本或 CSS 墙钟动画。单镜最长 60 秒，较长片按镜头组织。可编辑源码下载，不在工作台同源执行。
- character-loop：`frames:[本机图片绝对路径...],width,height,fps,background`。至少四张不同姿势，同一画布和锚点；background 为 `transparent/green`。边缘连通抠绿保留内部绿色；输出 GIF 与透明 WebP，仍需检查首尾衔接。
- blender-previs：`width,height,fps,duration,camera,subject,distance,objects?`。camera 为 `orbit/push/static`；objects 每项 `{name,shape,start:[x,y,z],end:[x,y,z],scale:[x,y,z]}`，shape 为 `sphere/cube/cylinder`。输出几何白模 MP4、`.blend` 和场景参数。真实人物、复杂骨骼和 Seedance 云端参考视频生成不包含在白模渲染中。

## 示例

```json
{"title":"辨别热点消息","route":"code-animation","brief":"用三个判断步骤讲清如何核对来源，平静中文解说。","style":"米白底、深蓝线条，动作简洁","character":"","voice_id":"","shots":[{"id":"shot-01","narration":"先找到原始出处，再判断转述有没有改变意思。","visual":"一条消息卡片沿引用链追溯到原始文档","action":"逐条揭示引用链，聚焦原始文档","camera":"固定","duration":6,"reference":"教学示意，非真实新闻","voice_id":"","status":"planned","review":"","asset_path":""}]}
```


## 自定义方法、角色和镜头交回

计划增加 `method_id`（九种非 Simon 方法 ID）、`production`（`format`: landscape / portrait / square；`image_engine`: 空、flux2-klein-4b 或 qwen-image-2512）、`cast`（角色 ID 数组）。单镜增加 `character_ids` 与 `speaker_id`。参数仅作用于本片，不修改全局设置。显式方法计划默认 `method_mode:custom`；固定场景复刻使用 `method_mode:example`。

GET / POST `/api/characters` 列表或保存角色；更新需携带 ID 和 revision。GET `/api/characters?id=角色ID` 返回完整角色及绑定声音。生成提交时冻结角色版本；小说和资料长片的 `character_links` 使用名称到 `{id,revision}` 的映射。

Codex / Blender 制作的镜头使用实际绝对路径填写 `asset_path`，保存计划后向 `/api/generation/compose` 提交 `{plan_id,revision,preview:false,source:"supplied"}`。此模式复制素材并记录哈希，不调用图像或编剧服务，按选定声音生成旁白和字幕。输出保留完整构图，短视频停末帧、长视频裁尾；源视频音轨被本片配音替换。重试读取任务素材快照。完整场景 `.blend` 是源文件，需先渲染成 MP4 再交回。
