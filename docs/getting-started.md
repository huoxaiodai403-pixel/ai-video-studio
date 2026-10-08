# 快速上手：让 Codex 带着工作台做视频

## 1. 安装工作台

下载 Windows 分享包并解压到可写目录。路径可自行选择，不需要固定 D 盘。
在该目录打开 PowerShell，执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-Studio.ps1 -InstallPython
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Open-Studio.ps1
```

也可双击包内 `Install.cmd` 与 `Start.cmd`。首次安装需要网络获取网页依赖；
没有兼容 Python 时，安装器通过 Windows 的 winget 安装 Python 3.12。
若系统没有 winget，请先自行安装 64 位 Python 3.11–3.14。默认同时安装 Node、渲染依赖和 Chromium；Simon 白板源码及 Windows 补丁、中文字体、公开贴纸已随包附带，不再另行克隆 Git 仓库。模型权重不默认下载。只需网页时可加 `-SkipRenderers`，稍后运行 `scripts/Install-Renderers.ps1` 补齐；该脚本会校验源码及实际启动 Chromium。
工作台默认网址为 <http://127.0.0.1:8189/home>。

## 2. 安装 Codex skill

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-CodexSkill.ps1
```

安装到当前用户 Codex 的 skills 目录；若同名 skill 已存在，会先备份。
打开本仓库目录，在新的 Codex 对话中明确使用 `$ai-video-studio`。
单独的 skill ZIP 也包含安装脚本，但不含工作台与模型引擎。

## 3. 选择实际可用的生成方式

**朋友使用 Codex 桌面端时，优先从这些能力开始：**

| 任务 | 方式 | 是否另需媒体模型或密钥 |
| --- | --- | --- |
| 选题、文稿、分镜 | Codex 直接编写 JSON | 否 |
| 白板图形与预览 | Simon + CPU 渲染器 | 否 |
| 插图、封面、角色图 | 当前会话可用的 Codex 内置生图，保存后导入长片 | 内置工具无需另配图像密钥，计入 Codex 用量 |
| 基础配音与同步字幕 | Windows 系统语音（CPU、离线）或 Edge 在线语音 | 无需显卡、模型权重或 API Key |
| 生成式动态视频、音乐、音效 | 可用媒体工具或导入素材 | 仍需对应能力 |

工作台网页不能直接调用 Codex 的聊天工具。正确流程是在 Codex 中创作/生图，
将生成文件导入工程，再由工作台合成。不能把 Codex 订阅当作通用媒体 API 密钥。
白板可选择 Windows、Edge 或火山配音并复用同次合成时间戳；OpenAI 兼容语音要同时配置返回逐词时间戳的 ASR。Windows 字幕使用系统报告的词起点，词尾取下一词起点；不等于声学强制对齐。

- **在线服务**（`/settings`）：按图像、配音、转写、视频、编剧分别连接和验证。编剧可选择 ChatGPT 官方账号授权（按账号资格与套餐额度），或使用自己的 API Key。火山配音支持新版 API Key 与旧版 App ID + Access Token。
  图像、视频、语音、识别能力分别检查，使用费用由对应提供方收取。
- **本地模型**（`/models`）：独立展示 CPU 系统语音、模型文件与运行环境，查看缺少的组件，再参照
  [本地模型说明](local-models.md) 准备引擎。不要只复制一个权重就认为整套引擎已安装。
- **先编辑后生成**：即使没有媒体模型，也可以用 Codex 编写分镜、保存草稿和管理
  自己的素材；真正的渲染或合成仍需要对应引擎。

调查长片、普通制片与白板是不同流程；调查长片仍有自己的配音与对齐依赖，不等同于配置单步服务后所有流程立即可用。让 skill 先读取环境检查，缺哪一环先补哪一环。

## 4. 从小样开始

给 Codex 的示例需求：

> 使用 $ai-video-studio，先检查环境。做一条三镜头白板讲解，主题是“核对信息来源”，
> 面向普通读者，用冷静清晰的中文。由你写分镜，先生成预览供检查，再做有声视频。

Codex 应先给出适合内容的脚本和分镜，再使用 skill 的 CLI 提交和查询任务。
文稿创作可以直接由 Codex 完成，不需要先安装本地编剧 LLM。

完成后在“我的作品”预览、试听、下载。继续修改时从作品详情进入对应工程。
旁白、字幕、封面、源分镜和交付包按该工作流实际生成的文件显示。

## 5. 送到剪映精修

v0.2.0 起提供剪映桥接；早期 v0.1.0 包需要更新工作台和 skill 才有这个入口。
先让 Skill 检查剪映。没有安装时，它会询问是否直接安装客户端并桥接；同意后运行 `scripts/Install-JianyingBridge.ps1 -InstallJianying -NonInteractive`。手动运行无参数版本也会先确认。已安装剪映时，脚本直接配置独立草稿环境。完成首次启动后再次检查草稿目录。
剪映组件需要 64 位 Python 3.12–3.14；使用基础工作台支持的 Python 3.11 时，须另装 3.12 并按剪映说明指定 `-PythonPath`。
在“我的作品”打开已完成的视频工程，进入“送到剪映精修”，
选择“自动选择”并生成草稿，再点击“打开剪映”。在剪映中按返回的草稿名进入工程，
检查镜头、配音和字幕后导出独立的 MP4。详见 [剪映接入说明](jianying-windows.md)。

也可直接对 Codex 说“使用 $ai-video-studio，把刚才的作品交接到剪映，保留可编辑轨道并检查”。
不同工程可保留的轨道不同；仅有最终视频时采用成片交接，不会自动还原所有声音与图层。
白板/讲解镜头没有独立画面素材时会重建为可编辑文字卡片，不自动迁移原手绘动效。

## 6. 给朋友分享

转发修复版 ZIP 与 SHA256 校验文件。朋友安装工作台和 Skill，由 Codex 按目标补齐实际所需依赖；不要求预装全套模型。
不要转发你自己的 `config`、音色克隆录音、参考照片、项目或 API 密钥。

## 常见情况

- 网页能打开但不能生成：检查相应模型/服务的就绪状态和任务错误说明。
- 8189 已占用：先确认占用进程属于哪个工作台，不要直接结束不明进程。
- CPU 或显卡不适合大模型：使用兼容在线工具，或只安装能运行的较小引擎。
- 剪映草稿无法打开：读取交接模式及提示，保留草稿和素材，按 [剪映说明](jianying-windows.md) 核对本机版本与草稿位置。
- 更新源码前保留 `config` 与 `projects`；更新不会授权删除已有作品。
