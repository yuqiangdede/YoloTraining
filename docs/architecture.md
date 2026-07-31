# 架构说明

浏览器只访问 FastAPI。FastAPI 负责校验、元数据和文件索引；Worker 是同一服务中的后台调度线程，统一串行调度训练、导出、预标注、视频推理和错误样本分析，避免本机 GPU 任务争抢显存。

```text
React UI -> /api/v1 -> FastAPI -> SQLite
                         |          |
                         |          +-- 相对路径与任务状态
                         +-> Worker -> 独立 Ultralytics 子进程 -> ./runs
```

数据库不保存图片和权重。素材、快照、模型与结果全部保存在项目目录的稳定相对路径中。

## 资源层级

```text
Project
└─ Dataset
   ├─ Asset -> Annotation
   ├─ AnnotationTask
   ├─ DatasetVersion -> TrainingJob -> ModelArtifact
   └─ AnalysisJob -> TP/FP/FN samples
```

旧数据库升级时，未指定项目的数据集自动归入稳定 ID 为 `default` 的“默认项目”。

## 状态机

训练、导出、预标注、视频推理和分析任务使用：`QUEUED -> RUNNING -> SUCCEEDED|FAILED|CANCELLED`。训练另外支持 `RUNNING -> PAUSING -> PAUSED -> QUEUED`。暂停控制文件由训练 callback 在 epoch 结束时读取，先保存 checkpoint 再结束子进程。

标注任务不包含审核阶段：`NEW -> IN_PROGRESS -> COMPLETED`。进度由任务素材中状态为 `COMPLETED`（兼容旧 `REVIEWED`）的数量自动计算。

## 数据版本

素材原件只读。标注可以修改并递增版本号；`COMPLETED` 与旧版 `REVIEWED` 标注可以进入训练快照。快照一旦创建不再修改，`manifest.json` 记录完整输入、来源、划分随机种子和 SHA-256 内容哈希。

## 错误样本分析

分析任务读取已完成标注，使用所选模型逐图推理。预测框与人工标注按类别和配置的 IoU 阈值做贪心一对一匹配，形成逐样本 TP、FP、FN；结果只读写入 `analysis_jobs.result_json`，不会修改原标注。
