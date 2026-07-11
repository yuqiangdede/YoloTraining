# 架构说明

浏览器只访问 FastAPI。FastAPI 负责校验、元数据和文件索引；训练 Worker 是同一服务中的后台调度线程，每个训练、导出或预标注任务都在独立 Python 子进程中运行。

```text
React UI -> /api/v1 -> FastAPI -> SQLite
                         |          |
                         |          +-- 相对路径与任务状态
                         +-> Worker -> 独立 Ultralytics 子进程 -> ./runs
```

数据库不保存图片和权重。素材、快照、模型与结果全部保存在项目目录的稳定相对路径中。

## 状态机

训练和导出任务使用：`QUEUED -> RUNNING -> SUCCEEDED|FAILED|CANCELLED`。训练另外支持 `RUNNING -> PAUSING -> PAUSED -> QUEUED`。暂停控制文件由训练 callback 在 epoch 结束时读取，先保存 checkpoint 再结束子进程。

## 数据版本

素材原件只读。标注可以修改并递增版本号；只有 `REVIEWED` 标注能进入训练快照。快照一旦创建不再修改，`manifest.json` 记录完整输入和 SHA-256 内容哈希。
