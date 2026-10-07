# 结构与数据流

```text
Codex + ai-video-studio skill
  → 文稿 / 分镜 JSON / 来源与角色安排
  → 本机 HTTP API（127.0.0.1:8189）
  → 独立媒体引擎：配音、对齐、生图、视频、音乐
  → Simon / Remotion / FFmpeg 合成
  → projects/studio/<任务号> → 统一作品与资源库
```

`scripts/studio.py` 是网页入口；扩展接口分布在 `studio_extensions.py`、
`creation_api.py`、`whiteboard_api.py`、`investigation_api.py`、`music_api.py`。
`library_api.py` 只索引登记素材、工作台产物与持久小说草稿，不扫描整块磁盘。

网页与 Codex 调用相同接口。Codex skill 中的标准库 CLI 适合脚本化编排；
网页负责可视化编辑、试听和审片。详见仓库中的 skill API 参考。

| 目录 | 含义 | 是否分享 |
| --- | --- | --- |
| scripts / docs / skills / examples | 源码、说明、Skill、公共模板 | 是 |
| apps/investigation-renderer | Remotion 渲染器源码与字体许可证 | 是，不含 node_modules |
| tools / apps 下其他引擎 | 机器自己的解释器与可选引擎 | 否，按需安装 |
| models | 模型权重 | 否 |
| config | 默认参数、接口凭据、音色预设、收藏标签 | 否 |
| projects | 分镜、草稿、媒体与交付物 | 否 |
| assets/voices、assets/image-references | 个人音色录音与参考图 | 否 |
| logs / cache / manifests | 日志、缓存、机器检查记录 | 否 |

默认接口只绑定环回地址。配置中的在线凭据由当前 Windows 用户加密；
复制别人的配置文件不是正确的安装方式。朋友应自行配置服务与音色。

GPU 任务按已有线程锁与 `manifests/gpu.lock` 协调；CPU 网页服务不应直接
导入庞大的 GPU 推理环境。引擎完成后释放其模型进程，避免显存互相挤占。

工程保留分镜和任务参数快照。改音色预设或模型默认值只影响新任务。
恢复工程、重新渲染、最终发布是不同操作，不会因打开作品详情就自动执行。

发行打包使用 `packaging/build_release.py` 的文件允许列表，并生成每个成员的
SHA256。不要直接把当前运行目录整体压缩发给他人。
