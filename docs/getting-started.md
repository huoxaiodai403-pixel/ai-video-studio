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
若系统没有 winget，请先自行安装 64 位 Python 3.11–3.14。模型权重不默认下载。
工作台默认网址为 <http://127.0.0.1:8189/home>。

## 2. 安装 Codex skill

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-CodexSkill.ps1
```

安装到当前用户 Codex 的 skills 目录；若同名 skill 已存在，会先备份。
打开本仓库目录，在新的 Codex 对话中明确使用 `$ai-video-studio`。
单独的 skill ZIP 也包含安装脚本，但不含工作台与模型引擎。

## 3. 选择实际可用的生成方式

- **在线工具**：在“设置 → 在线接口设置”填写自己提供方的接口、模型和密钥。
  图像、视频、语音、识别能力分别检查，使用费用由对应提供方收取。
- **本地工具**：先打开“资源库 → 模型库”查看缺少的组件，再参照
  [本地模型说明](local-models.md) 准备引擎。不要只复制一个权重就认为整套引擎已安装。
- **先编辑后生成**：即使没有媒体模型，也可以用 Codex 编写分镜、保存草稿和管理
  自己的素材；真正的渲染或合成仍需要对应引擎。

白板和调查长片有自己的渲染器、配音与对齐依赖，不等同于配置在线单步工具后
所有完整工作流立即可用。让 skill 先读取环境检查，缺哪一环先补哪一环。

## 4. 从小样开始

给 Codex 的示例需求：

> 使用 $ai-video-studio，先检查环境。做一条三镜头白板讲解，主题是“核对信息来源”，
> 面向普通读者，用冷静清晰的中文。由你写分镜，先生成预览供检查，再做有声视频。

Codex 应先给出适合内容的脚本和分镜，再使用 skill 的 CLI 提交和查询任务。
文稿创作可以直接由 Codex 完成，不需要先安装本地编剧 LLM。

完成后在“我的作品”预览、试听、下载。继续修改时从作品详情进入对应工程。
旁白、字幕、封面、源分镜和交付包按该工作流实际生成的文件显示。

## 5. 给朋友分享

转发 Release 页面或 ZIP 与 SHA256 校验文件。朋友自行安装 skill、依赖和所需模型。
不要转发你自己的 `config`、音色克隆录音、参考照片、项目或 API 密钥。

## 常见情况

- 网页能打开但不能生成：检查相应模型/服务的就绪状态和任务错误说明。
- 8189 已占用：先确认占用进程属于哪个工作台，不要直接结束不明进程。
- CPU 或显卡不适合大模型：使用兼容在线工具，或只安装能运行的较小引擎。
- 剪映精修：下载素材和字幕，参照 [剪映说明](jianying-windows.md)。
- 更新源码前保留 `config` 与 `projects`；更新不会授权删除已有作品。
