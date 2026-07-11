# YOLO26 Studio

YOLO26 Studio 是一个仅在本机运行的视觉模型训练平台。它把图片素材管理、五类人工标注、不可变数据集快照、动态增强、GPU 训练队列、结果管理、预标注和 ONNX 导出放在一个 Web 界面中。

支持的任务：

- 目标检测（矩形框）
- 实例分割（多边形）
- 语义分割（多边形或像素掩码）
- 姿态估计（关键点与可见性）
- OBB（旋转框）

## 项目内资源约束

运行时不依赖项目目录外的模型、虚拟环境、缓存或数据：

```text
./.venv                  Python 3.11 虚拟环境
./models/pretrained      官方预训练权重
./models/trained         归档训练权重
./uploads/assets         原始素材
./data/studio.db         SQLite 元数据
./data/datasets          不可变数据集快照
./runs                   训练、预标注和导出产物
./logs                   服务日志
./backups                备份文件
./resources              项目随附资源
```

外部离线资源目录只作为安装源和下载归档，不是运行依赖。平台数据库只保存相对于项目根目录的路径，复制整个项目目录即可迁移。

## 已验证环境

- Windows 11
- Python 3.11
- NVIDIA GeForce RTX 3060 12GB
- PyTorch 2.6.0 + CUDA 12.4
- Ultralytics 8.4.92（YOLO26）
- Node.js 24

## 安装

依赖准备脚本要求显式传入离线资源根目录。该目录应包含 `PyTorch离线包/cu124-py311` 和 `YOLO26平台依赖`：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install.ps1 -OfflineResourceRoot "你的离线资源目录"
```

脚本会创建项目根目录 `.venv`，从离线 wheels 安装 CUDA 版 PyTorch 和平台依赖，并在 `frontend/node_modules` 安装前端依赖。不会使用 Conda、全局 Python 环境或项目外模型。

下载其他 YOLO26 尺寸或重新归档模型：

```powershell
.\scripts\download-models.ps1 -OfflineResourceRoot "你的离线资源目录" -Scales n,s,m,l,x
```

模型始终先保存到离线资源目录，再复制到 `models/pretrained`。

## 启动与停止

```powershell
.\scripts\start.ps1
```

浏览器访问 `http://127.0.0.1:8000`。平台默认只监听本机地址，不提供账号和局域网访问。

```powershell
.\scripts\stop.ps1
```

环境诊断：

```powershell
.\scripts\diagnose.ps1
```

## 使用流程

1. 在“素材库”批量导入图片；相同内容会按 SHA-256 拒绝重复导入。
2. 在“人工标注”选择任务和类别，完成标注并设置为“已审核”。
3. 在“数据集版本”创建不可变训练快照；平台会固化素材、标注、类别、划分随机种子和内容哈希。
4. 把对应任务的 YOLO26 权重放在 `models/pretrained`，在“训练任务”选择数据集并填写项目内模型路径。
5. Worker 串行使用 GPU 训练，实时更新 epoch 和进度；暂停会在 epoch checkpoint 后生效。
6. 成功训练产生的 `best.pt`、`last.pt` 和图表保存在 `runs/<任务ID>`，模型页可查看产物并创建 ONNX 导出。

语义分割多边形按 Ultralytics 支持的方式导出为 YOLO 多边形标签，并由训练加载器生成稠密语义掩码。姿态数据集需指定关键点数量；需要左右翻转时可通过 API 同时提供 `flipIdx`。

## API 与测试

REST API 前缀为 `/api/v1`，交互文档位于 `/docs`。统一资源包括素材、标注、数据集版本、训练任务、模型、导出、预标注和环境状态。

```powershell
$env:PYTHONPATH = "backend"
.\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v

Set-Location frontend
npm test
npm run build
```

## 安全与恢复

- 上传内容经过 Pillow 解码验证，文件名不会直接作为存储路径。
- 模型和数据库路径必须在项目根目录内，API 不接受外部绝对路径。
- 原始素材进入回收站状态，数据集快照复制素材并保持不可变。
- 训练参数通过 Pydantic 白名单验证，不拼接 shell 命令。
- 失败任务保留日志、请求参数和错误信息；暂停任务可使用最近的 `last.pt` 恢复。

## 许可证

平台代码与 Ultralytics 软件、模型的授权是两件事。Ultralytics 提供 AGPL-3.0 与 Enterprise License；将本平台用于内部业务工具、商业产品或对外服务前，应根据实际用途确认 Ultralytics 授权。参见 [Ultralytics License](https://github.com/ultralytics/ultralytics#license)。
