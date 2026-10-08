# 朋友版 API

`python CLIENT doctor` 检查服务；`list --status all` 查作品；`voices` 列音色；`generation` 列实际路线；`status JOB_ID --wait 60` 等待真实结果；`download --job JOB_ID --field video --output 新路径` 下载，不覆盖旧文件。

## 白板

参考同目录 `whiteboard-request.json`，Codex 直接写口播与场景。调用 `submit whiteboard-preview --json 请求文件`，检查静帧；再 `submit whiteboard-render --json 请求文件`。无需先有生图模型。选 Windows/Edge 时使用同次语音的时间戳；在线兼容语音需有返回词时间戳的转写接口。中文字体和经验证的 Simon CPU 渲染源码随包提供。

## 配音与素材

网页 `/speech` 可选 Windows、Edge、在线服务或已准备的本地音色。`GET /api/speech/options` 获取实际声线；`POST /api/speech` 请求包含 `text,backend,voice_id,speed`，backend 按实际选择 windows/edge/volc/online/local。本地 preset 先从 `/api/voice-library` 获取实际 voice，不编造ID。

`GET /api/image-references` 查看已登记图片。导入现有图片使用页面图库上传，或查看工作台 `scripts/image_references.py` 的实际 API 请求字段后提交；不要将私人照片随软件包分发。

代码动画 API 见 [generation.md](generation.md)。可先生成配音，读取真实 WAV 时长，再写动画并传 audio_path 合成。

## 剪映

`jianying status --project 工程ID` 查看客户端和桥接。
`jianying export --project 工程ID --mode auto` 创建新的草稿，保留原作品。
`jianying open --project 工程ID` 启动已安装客户端。随后在剪映中查看草稿与轨道，实际导出后再判断交接是否完成。

缺剪映且用户已授权安装：运行工作台 `scripts/Install-JianyingBridge.ps1 -InstallJianying -NonInteractive`，桥接要求64位 Python 3.12–3.14。已有客户端先复用；复杂编辑和导出需要用户或当前会话实际具备的桌面工具。

## 使用边界

朋友版不提供调查长片、角色循环、Blender、高级模型管理、独立视频模型和音乐生成。HTTP成功或文件存在仅是功能证据。需要看实际画面和音轨；未试听就保留待试听状态。
