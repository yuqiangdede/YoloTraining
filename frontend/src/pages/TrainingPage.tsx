import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pause, Play, Plus, Square, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { EmptyState, ErrorState, LoadingRows } from "../components/States";
import { PageHeader } from "../components/PageHeader";
import { TrainingEvidence } from "../components/TrainingEvidence";
import { useToast } from "../components/Toast";
import { api } from "../lib/api";
import { MODEL_SIZES, RFDETR_MODELS, modelKindLabels, modelPathFor, modelSizeLabels, rfDetrLabel, type ModelSize, type RfDetrSize } from "../lib/modelCatalog";
import { jobStatusLabels, taskLabels } from "../lib/labels";

type NumericField = {
  key: string;
  label: string;
  defaultValue: number;
  help: string;
  min?: number;
  max?: number;
  exclusiveMin?: boolean;
};

const augmentationPresets = [
  { value: "none", label: "仅使用 YOLO 内置增强", help: "保留当前几何、HSV、Mosaic、MixUp 等训练增强。" },
  { value: "photometric", label: "光照与色彩", help: "参考 Albumentations：亮度、对比度、色相、灰度、Gamma 与 CLAHE。" },
  { value: "robust", label: "噪声与压缩", help: "参考 Albumentations：模糊、噪声、压缩伪影与局部遮挡。" },
  { value: "full", label: "综合增强", help: "同时启用光照色彩与噪声压缩方案；空间标注仍由 YOLO 内置增强处理。" },
] as const;

const numericFields: NumericField[] = [
  { key: "epochs", label: "训练轮次", defaultValue: 100, help: "完整遍历训练集的次数；建议从 100 开始。", min: 1, max: 10000 },
  { key: "imgsz", label: "图像尺寸", defaultValue: 640, help: "输入边长（像素）；建议 640，越大显存占用越高。", min: 32, max: 8192 },
  { key: "batch", label: "批量", defaultValue: 8, help: "每次更新使用的图片数；-1 为自动估算。", min: -1 },
  { key: "workers", label: "加载线程", defaultValue: 4, help: "读取数据的并行线程数；Windows 通常使用 2–4。", min: 0, max: 32 },
  { key: "patience", label: "早停耐心值", defaultValue: 100, help: "验证指标连续不提升多少轮后提前停止；0 表示关闭早停。", min: 0 },
  { key: "lr0", label: "初始学习率", defaultValue: 0.01, help: "训练开始的学习率；通常保持 0.01，必须大于 0。", min: 0, exclusiveMin: true },
  { key: "lrf", label: "最终学习率比例", defaultValue: 0.01, help: "训练结束时相对初始学习率的比例；通常保持 0.01，必须大于 0。", min: 0, exclusiveMin: true },
  { key: "momentum", label: "动量", defaultValue: 0.937, help: "平滑梯度更新；通常保持 0.937。", min: 0, max: 1 },
  { key: "weightDecay", label: "权重衰减", defaultValue: 0.0005, help: "抑制过拟合的正则化强度；通常保持 0.0005。", min: 0 },
  { key: "warmupEpochs", label: "预热轮次", defaultValue: 3, help: "训练开始时逐步提高学习率的轮次；通常使用 3。", min: 0 },
  { key: "degrees", label: "旋转角度", defaultValue: 0, help: "随机旋转的最大角度；0 表示关闭。", min: 0, max: 180 },
  { key: "translate", label: "平移", defaultValue: 0.1, help: "随机平移比例；建议 0.1。", min: 0, max: 1 },
  { key: "scale", label: "缩放", defaultValue: 0.5, help: "随机缩放幅度；建议 0.5。", min: 0 },
  { key: "shear", label: "剪切", defaultValue: 0, help: "随机剪切的最大角度；0 表示关闭。", min: 0, max: 180 },
  { key: "flipud", label: "上下翻转", defaultValue: 0, help: "上下翻转的概率；多数场景保持 0。", min: 0, max: 1 },
  { key: "fliplr", label: "左右翻转", defaultValue: 0.5, help: "左右翻转的概率；建议 0.5。", min: 0, max: 1 },
  { key: "hsvH", label: "色相", defaultValue: 0.015, help: "色相扰动幅度；建议 0.015。", min: 0, max: 1 },
  { key: "hsvS", label: "饱和度", defaultValue: 0.7, help: "饱和度扰动幅度；建议 0.7。", min: 0, max: 1 },
  { key: "hsvV", label: "亮度", defaultValue: 0.4, help: "亮度扰动幅度；建议 0.4。", min: 0, max: 1 },
  { key: "mosaic", label: "Mosaic", defaultValue: 1, help: "四图拼接增强的概率；1 表示始终启用。", min: 0, max: 1 },
  { key: "perspective", label: "透视", defaultValue: 0, help: "随机透视变换幅度；0 表示关闭。", min: 0, max: 0.001 },
  { key: "mixup", label: "MixUp", defaultValue: 0, help: "两张图像混合增强的概率；0 表示关闭。", min: 0, max: 1 },
  { key: "copyPaste", label: "Copy-Paste", defaultValue: 0, help: "实例复制粘贴增强的概率；主要用于分割任务。", min: 0, max: 1 },
];

const coreNumericFieldKeys = new Set(["epochs", "imgsz", "batch"]);
const rfDetrFields: NumericField[] = [
  ...numericFields.filter((field) => ["epochs", "batch", "lr0"].includes(field.key)),
  { key: "seed", label: "随机种子", defaultValue: 0, help: "控制训练的随机性。", min: 0, max: 2 ** 32 - 1 },
];

function validationMessage(field: NumericField, value: string | number | boolean): string | undefined {
  if (value === "" || typeof value === "boolean" || !Number.isFinite(Number(value))) return `${field.label}必须填写有效数字。`;
  const number = Number(value);
  if (field.exclusiveMin && number <= field.min!) return `${field.label}必须大于 ${field.min}。`;
  if (field.min !== undefined && number < field.min) return `${field.label}不能小于 ${field.min}。`;
  if (field.max !== undefined && number > field.max) return `${field.label}不能大于 ${field.max}。`;
  return undefined;
}

function formatValidationError(error: unknown): string {
  const apiError = error as { code?: string; details?: unknown; message?: string };
  if (apiError.code !== "VALIDATION_ERROR") return error instanceof Error ? error.message : "创建训练任务失败";
  const details = Array.isArray(apiError.details) ? apiError.details : [];
  const detail = details[0] as { loc?: unknown[]; msg?: string; ctx?: { ge?: number; gt?: number; le?: number } } | undefined;
  const key = typeof detail?.loc?.at(-1) === "string" ? detail.loc.at(-1) : undefined;
  const field = numericFields.find((item) => item.key === key);
  if (field && detail?.ctx?.gt !== undefined) return `${field.label}必须大于 ${detail.ctx.gt}。`;
  if (field && detail?.ctx?.ge !== undefined) return `${field.label}不能小于 ${detail.ctx.ge}。`;
  if (field && detail?.ctx?.le !== undefined) return `${field.label}不能大于 ${detail.ctx.le}。`;
  if (field) return `${field.label}填写不正确。`;
  return apiError.message ?? "请求参数无效";
}

function formatWait(seconds = 0): string {
  if (seconds < 60) return `${seconds} 秒`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} 分钟`;
  return `${Math.floor(minutes / 60)} 小时 ${minutes % 60} 分钟`;
}

function formatRuntime(startedAt: string | null | undefined): string | null {
  if (!startedAt) return null;
  return formatWait(Math.max(0, Math.floor((Date.now() - Date.parse(startedAt)) / 1000)));
}

export function TrainingPage() {
  const client = useQueryClient();
  const { notify } = useToast();
  const focusedJobId = new URLSearchParams(window.location.search).get("job");
  const datasets = useQuery({
    queryKey: ["datasetVersions"],
    queryFn: api.allDatasetVersions,
  });
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: api.jobs,
    refetchInterval: 2000,
  });
  const [logJobId, setLogJobId] = useState<string | null>(null);
  const [evidenceJobId, setEvidenceJobId] = useState<string | null>(null);
  const log = useQuery({
    queryKey: ["jobLog", logJobId],
    queryFn: () => api.jobLog(logJobId!),
    enabled: Boolean(logJobId),
    retry: false,
    refetchInterval: logJobId && ["QUEUED", "RUNNING"].includes(jobs.data?.data.find((job) => job.id === logJobId)?.status ?? "") ? 2000 : false,
  });
  const evidence = useQuery({
    queryKey: ["trainingEvidence", evidenceJobId],
    queryFn: () => api.artifacts(evidenceJobId!),
    enabled: Boolean(evidenceJobId),
    retry: false,
    refetchInterval: (query) => {
      const job = jobs.data?.data.find((item) => item.id === evidenceJobId);
      return job?.engine === "rfdetr" && (["QUEUED", "RUNNING"].includes(job.status) ||
        (job.status === "SUCCEEDED" && !query.state.data?.data.length)) ? 2000 : false;
    },
  });
  const [form, setForm] = useState<Record<string, string | number | boolean>>({
    name: "train-yolo-n",
    datasetVersionId: "",
    modelPath: "models/pretrained/yolo26n.pt",
    device: "0",
    optimizer: "auto",
    amp: true,
    deterministic: true,
    augmentationPreset: "none",
    ...Object.fromEntries(numericFields.map((field) => [field.key, field.defaultValue])),
  });
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [modelSize, setModelSize] = useState<ModelSize>("n");
  const [engine, setEngine] = useState<"yolo" | "rfdetr">("yolo");
  const isRfDetr = engine === "rfdetr";
  const [rfDetrSize, setRfDetrSize] = useState<RfDetrSize>("nano");
  const rfDetrPath = RFDETR_MODELS[rfDetrSize].path;
  const [rfDetrValues, setRfDetrValues] = useState<Record<string, string | number>>({
    epochs: 100, batch: 2, lr0: 0.0001, seed: 0,
  });
  const [nameEdited, setNameEdited] = useState(false);
  const [createdJobId, setCreatedJobId] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<{ id: string; name: string; action: "cancel" | "delete" } | null>(null);
  const selectedDataset =
    datasets.data?.data.find((item) => item.id === form.datasetVersionId) ??
    datasets.data?.data[0];
  const create = useMutation({
    mutationFn: () => {
      const nextErrors = Object.fromEntries(
        (isRfDetr ? rfDetrFields : numericFields).flatMap((field) => {
          const value = Number(rfDetrValues[field.key]);
          const message = isRfDetr && field.key === "batch" && (!Number.isInteger(value) || value < 1)
            ? "批量大小必须为正整数。"
            : isRfDetr && ["seed", "epochs"].includes(field.key) && !Number.isInteger(value)
              ? `${field.label}必须为整数。`
              : validationMessage(field, isRfDetr ? rfDetrValues[field.key] : form[field.key]);
          return message ? [[field.key, message]] : [];
        }),
      );
      if (!String(form.name).trim()) nextErrors.name = "任务名称不能为空。";
      if (isRfDetr && selectedDataset?.task !== "detect") nextErrors.engine = "RF-DETR 需要目标检测数据集版本。";
      setFormErrors(nextErrors);
      if (Object.keys(nextErrors).length) {
        requestAnimationFrame(() => document.querySelector<HTMLElement>(`[name="${Object.keys(nextErrors)[0]}"]`)?.focus());
        throw new Error("请先修正标记的训练参数。");
      }
      return api.createJob({
        ...(isRfDetr ? { ...rfDetrValues, name: form.name, modelPath: rfDetrPath, engine } : form),
        datasetVersionId: selectedDataset?.id,
        task: selectedDataset?.task,
      });
    },
    onSuccess: (job) => {
      setCreatedJobId(job.id);
      client.invalidateQueries({ queryKey: ["jobs"] });
      notify(`训练任务“${job.name}”已加入队列`);
      requestAnimationFrame(() => document.querySelector(`[data-job-id="${job.id}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" }));
    },
  });
  const action = useMutation({
    mutationFn: ({
      id,
      action,
    }: {
      id: string;
      action: "pause" | "resume" | "cancel";
    }) => api.jobAction(id, action),
    onSuccess: () => { client.invalidateQueries({ queryKey: ["jobs"] }); setConfirmation(null); },
  });
  const remove = useMutation({
    mutationFn: api.deleteJob,
    onSuccess: () => { client.invalidateQueries({ queryKey: ["jobs"] }); setConfirmation(null); notify("训练任务及关联产物已删除"); },
  });
  const update = (key: string, value: string | number | boolean) => {
    setForm((current) => ({ ...current, [key]: value }));
    if (formErrors[key]) setFormErrors((current) => { const next = { ...current }; delete next[key]; return next; });
  };
  const validateField = (field: NumericField) => {
    const message = validationMessage(field, form[field.key]);
    setFormErrors((current) => { const next = { ...current }; if (message) next[field.key] = message; else delete next[field.key]; return next; });
  };
  useEffect(() => {
    if (!selectedDataset) return;
    const nextSize: ModelSize = "n";
    setModelSize(nextSize);
    update("modelPath", modelPathFor(selectedDataset.task, nextSize));
    if (!nameEdited) update("name", isRfDetr ? `train-rfdetr-${rfDetrSize}` : `train-yolo-${nextSize}`);
  }, [selectedDataset?.id, selectedDataset?.task]);
  const coreNumericFields = numericFields.filter((field) =>
    coreNumericFieldKeys.has(field.key),
  );
  const advancedNumericFields = numericFields.filter(
    (field) => !coreNumericFieldKeys.has(field.key),
  );
  const advancedGroups = [
    { title: "性能", fields: advancedNumericFields.filter((field) => ["workers", "patience", "warmupEpochs"].includes(field.key)) },
    { title: "优化器", fields: advancedNumericFields.filter((field) => ["lr0", "lrf", "momentum", "weightDecay"].includes(field.key)) },
    { title: "数据增强", fields: advancedNumericFields.filter((field) => !["workers", "patience", "warmupEpochs", "lr0", "lrf", "momentum", "weightDecay"].includes(field.key)) },
  ];
  const worker = jobs.data?.worker;
  const confirmAction = () => { if (!confirmation) return; if (confirmation.action === "cancel") action.mutate({ id: confirmation.id, action: "cancel" }); else remove.mutate(confirmation.id); };
  return (
    <>
      <PageHeader
        title="训练任务"
        description="核心参数优先显示，更多设置可按需展开"
        actions={
          <button
            type="submit"
            form="training-create-form"
            className="button primary"
            disabled={!selectedDataset || create.isPending}
          >
            <Plus size={16} />
            创建任务
          </button>
        }
      />
      {datasets.isPending ? <LoadingRows /> : datasets.isError ? <ErrorState message={datasets.error.message} onRetry={() => datasets.refetch()} /> : !datasets.data.data.length ? <EmptyState title="还没有可训练版本" message="请先在数据集工作区完成素材审核并冻结一个训练版本。" action={<a className="button primary" href="/datasets">前往数据集</a>} /> : <form id="training-create-form" className="panel training-form" onSubmit={(event) => { event.preventDefault(); create.mutate(); }} noValidate>
          <div className="panel-heading">
          <div>
            <h2>新建训练</h2>
            <p>参数在创建时随数据集快照一同固化</p>
          </div>
        </div>
          <div className="form-grid">
          <label>
            任务名称
            <input
              name="name"
              aria-invalid={Boolean(formErrors.name)}
              value={form.name as string}
              onChange={(e) => { setNameEdited(true); update("name", e.target.value); }}
              onBlur={() => setFormErrors((current) => { const next = { ...current }; if (!String(form.name).trim()) next.name = "任务名称不能为空。"; else delete next.name; return next; })}
            />
            {formErrors.name && <small className="field-error">{formErrors.name}</small>}
          </label>
          <label>
            数据集版本
            <select
              value={selectedDataset?.id ?? ""}
              onChange={(e) => update("datasetVersionId", e.target.value)}
            >
              {datasets.data?.data.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} · {taskLabels[item.task]}
                </option>
              ))}
            </select>
          </label>
          <label>
            训练引擎
            <select name="engine" value={engine} onChange={(event) => {
              const nextEngine = event.target.value as "yolo" | "rfdetr";
              setEngine(nextEngine);
              setFormErrors({});
              if (!nameEdited) update("name", nextEngine === "rfdetr" ? `train-rfdetr-${rfDetrSize}` : `train-yolo-${modelSize}`);
            }}>
              <option value="yolo">YOLO</option>
              <option value="rfdetr">RF-DETR</option>
            </select>
            {formErrors.engine && <small className="field-error">{formErrors.engine}</small>}
          </label>
          <label>
            项目内模型路径
            <output className="model-setting-value">{isRfDetr ? rfDetrPath : form.modelPath as string}</output>
          </label>
          {isRfDetr && <label>
            模型档位
            <select value={rfDetrSize} onChange={(event) => {
              const size = event.target.value as RfDetrSize;
              setRfDetrSize(size);
              if (!nameEdited) update("name", `train-rfdetr-${size}`);
            }}>
              {Object.entries(RFDETR_MODELS).map(([size, model]) => <option key={size} value={size}>{model.label}</option>)}
            </select>
          </label>}
          {!isRfDetr && <><label>
            模型档位
            <select
              aria-label="模型档位"
              value={modelSize}
              disabled={!selectedDataset}
              onChange={(e) => {
                const nextSize = e.target.value as ModelSize;
                setModelSize(nextSize);
                if (selectedDataset) update("modelPath", modelPathFor(selectedDataset.task, nextSize));
                if (!nameEdited) update("name", `train-yolo-${nextSize}`);
              }}
            >
              {MODEL_SIZES.map((size) => <option key={size} value={size}>{modelSizeLabels[size]}</option>)}
            </select>
          </label>
          <label>
            模型分类
            <output className="model-setting-value">{selectedDataset ? modelKindLabels[selectedDataset.task] : "请先选择数据集"}</output>
          </label>
          <label>
            设备
            <input
              value={form.device as string}
              onChange={(e) => update("device", e.target.value)}
            />
          </label></>}
          {(isRfDetr ? rfDetrFields : coreNumericFields).map((field) => (
            <label key={field.key}>
              {field.label}
              <input
                name={field.key}
                type="number"
                step="any"
                aria-label={field.label}
                aria-invalid={Boolean(formErrors[field.key])}
                value={isRfDetr ? rfDetrValues[field.key] : form[field.key] as string | number}
                onChange={(e) => {
                  const value = e.target.value;
                  if (isRfDetr) {
                    setRfDetrValues((current) => ({ ...current, [field.key]: value }));
                    setFormErrors((current) => { const next = { ...current }; delete next[field.key]; return next; });
                  } else update(field.key, value);
                }}
                onBlur={() => { if (!isRfDetr) validateField(field); }}
              />
              {formErrors[field.key] && <small className="field-error">{formErrors[field.key]}</small>}
            </label>
          ))}
        </div>
        {!isRfDetr && <><label className="augmentation-preset-field">
          Albumentations 素材增强方案
          <select aria-label="Albumentations 素材增强方案" value={form.augmentationPreset as string} onChange={(event) => update("augmentationPreset", event.target.value)}>
            {augmentationPresets.map((preset) => <option key={preset.value} value={preset.value}>{preset.label}</option>)}
          </select>
          <small className="field-help">{augmentationPresets.find((preset) => preset.value === form.augmentationPreset)?.help}</small>
        </label>
        <details className="training-advanced">
          <summary>高级训练参数</summary>
          <div className="advanced-groups">{advancedGroups.map((group) => <fieldset key={group.title}><legend>{group.title}</legend><div className="form-grid">{group.fields.map((field) => <label key={field.key}>{field.label}<input name={field.key} type="number" step="any" aria-label={field.label} aria-invalid={Boolean(formErrors[field.key])} value={form[field.key] as string | number} onChange={(event) => update(field.key, event.target.value)} onBlur={() => validateField(field)} /><small className="field-help">{field.help}</small>{formErrors[field.key] && <small className="field-error">{formErrors[field.key]}</small>}</label>)}
            {group.title === "性能" && <><label className="check"><input type="checkbox" checked={form.amp as boolean} onChange={(event) => update("amp", event.target.checked)} />AMP 混合精度<small className="field-help">通常更快、更省显存。</small></label><label className="check"><input type="checkbox" checked={form.deterministic as boolean} onChange={(event) => update("deterministic", event.target.checked)} />确定性训练<small className="field-help">便于复现实验结果。</small></label></>}
            {group.title === "优化器" && <label>优化器<select value={form.optimizer as string} onChange={(event) => update("optimizer", event.target.value)}><option>auto</option><option>MuSGD</option><option>SGD</option><option>AdamW</option></select><small className="field-help">不确定时保持 auto。</small></label>}
          </div></fieldset>)}</div>
        </details></>}
        {create.error && <ErrorState message={formatValidationError(create.error)} />}
        <div className="form-actions"><button type="submit" className="button primary" disabled={create.isPending}><Plus size={16} />{create.isPending ? "正在创建…" : "加入训练队列"}</button></div>
      </form>}
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>任务队列</h2>
            <p>安全暂停会等待当前 epoch 保存 checkpoint</p>
          </div>
        </div>
        {worker && !worker.alive && (
          <div className="worker-warning" role="alert">
            工作线程当前不可用，排队任务不会自动开始。{worker.lastError ? ` 最近错误：${worker.lastError}` : "请重启训练服务。"}
          </div>
        )}
        {jobs.isPending ? <LoadingRows /> : jobs.isError ? <ErrorState message={jobs.error.message} onRetry={() => jobs.refetch()} /> : jobs.data?.data.length ? (
          jobs.data.data.map((job) => (
            <div data-job-id={job.id} className={`job-row ${job.id === focusedJobId ? "selected" : ""} ${job.id === createdJobId ? "is-new" : ""}`} key={job.id}>
              <div>
                <strong>{job.name}</strong>
                <span>
                  {job.engine === "rfdetr" && `${rfDetrLabel(job.modelVariant)} · `}{taskLabels[job.task]} · {job.status === "QUEUED"
                    ? `前方 ${Math.max(0, (job.queuePosition ?? 1) - 1)} 个任务 · 已等待 ${formatWait(job.waitSeconds)}`
                    : `Epoch ${job.currentEpoch}${job.status === "RUNNING" && worker?.currentJobId === job.id ? ` · 已运行 ${formatRuntime(worker.currentStartedAt)}` : ""}`}
                </span>
              </div>
              <div className="progress" role="progressbar" aria-label={`${job.name} 训练进度`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={job.progress}>
                <i style={{ width: `${job.progress}%` }} />
              </div>
              <span className={`badge ${job.status.toLowerCase()}`}>
                {jobStatusLabels[job.status] ?? job.status}
              </span>
              <div className="row-actions">
                <button
                  className="button ghost"
                  aria-label="查看训练依据"
                  onClick={() => setEvidenceJobId((current) => current === job.id ? null : job.id)}
                >
                  查看训练依据
                </button>
                {!['SUCCEEDED', 'CANCELLED'].includes(job.status) && (
                  <button
                    className="button ghost"
                    aria-label={"\u67e5\u770b\u65e5\u5fd7"}
                    onClick={() => setLogJobId((current) => current === job.id ? null : job.id)}
                  >
                    {"\u67e5\u770b\u65e5\u5fd7"}
                  </button>
                )}
                {job.status === "RUNNING" && job.engine !== "rfdetr" && (
                  <button
                    aria-label="暂停"
                    onClick={() =>
                      action.mutate({ id: job.id, action: "pause" })
                    }
                  >
                    <Pause size={15} />
                  </button>
                )}
                {job.status === "PAUSED" && job.engine !== "rfdetr" && (
                  <button
                    aria-label="恢复"
                    onClick={() =>
                      action.mutate({ id: job.id, action: "resume" })
                    }
                  >
                    <Play size={15} />
                  </button>
                )}
                {!["SUCCEEDED", "CANCELLED"].includes(job.status) && (
                  <button
                    aria-label="取消"
                    onClick={() => setConfirmation({ id: job.id, name: job.name, action: "cancel" })}
                  >
                    <Square size={15} />
                  </button>
                )}
                {!["RUNNING", "PAUSING"].includes(job.status) && (
                  <button
                    aria-label={`删除 ${job.name}`}
                    disabled={remove.isPending}
                    onClick={() => setConfirmation({ id: job.id, name: job.name, action: "delete" })}
                  >
                    <Trash2 size={15} />
                  </button>
                )}
              </div>
              {job.status === "FAILED" && job.errorMessage && (
                <p className="job-error" role="alert">{job.errorMessage}</p>
              )}
              {evidenceJobId === job.id && (
                <div className="job-evidence">
                  {evidence.isPending && <p className="quiet-state">正在加载训练结果摘要…</p>}
                  {evidence.isError && <ErrorState message={evidence.error.message} />}
                  <TrainingEvidence params={job.params} quality={evidence.data?.data[0]?.trainingQuality ?? evidence.data?.trainingQuality} />
                </div>
              )}
              {logJobId === job.id && (
                <div className="job-log" aria-live="polite">
                  {log.isPending && <span>{"\u6b63\u5728\u52a0\u8f7d\u65e5\u5fd7..."}</span>}
                  {log.isError && <ErrorState message={log.error.message} />}
                  {log.data && (log.data.content ? <pre>{log.data.content}</pre> : <span>{job.status === "QUEUED" ? "尚未被工作线程领取，暂无训练日志。" : "暂无日志输出。"}</span>)}
                </div>
              )}
            </div>
          ))
        ) : (
          <EmptyState
            title="训练队列为空"
            message="选择数据集和项目内预训练模型后创建任务"
          />
        )}
      </section>
      <ConfirmDialog open={Boolean(confirmation)} title={confirmation?.action === "cancel" ? "取消训练任务？" : "删除训练任务？"} description={confirmation?.action === "cancel" ? `任务“${confirmation?.name}”将停止训练，已完成的进度不会生成最终模型。` : `任务“${confirmation?.name}”的日志、运行目录和模型产物将被永久删除。`} confirmLabel={confirmation?.action === "cancel" ? "确认取消训练" : "确认删除"} pending={action.isPending || remove.isPending} onCancel={() => setConfirmation(null)} onConfirm={confirmAction} />
    </>
  );
}
