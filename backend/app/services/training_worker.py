import hashlib
import csv
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.core.database import Database
from app.models import Annotation, Asset, DatasetVersion, ExportJob, ModelArtifact, PrelabelJob, TrainingJob
from app.services.state_machine import JobStatus


class TrainingWorker:
    def __init__(self, root: Path, database: Database) -> None:
        self.root = root
        self.database = database
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self._recover_interrupted()
        self.thread = threading.Thread(target=self._loop, name="training-worker", daemon=True)
        self.thread.start()

    def _recover_interrupted(self) -> None:
        with self.database.session() as session:
            for model in (TrainingJob, ExportJob, PrelabelJob):
                items = session.scalars(select(model).where(model.status.in_([JobStatus.RUNNING, JobStatus.PAUSING])))
                for item in items:
                    item.status = JobStatus.FAILED
                    item.error_message = "服务重启时任务仍在运行，请检查日志后重新创建或恢复任务"
            session.commit()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)

    def _loop(self) -> None:
        while not self.stop_event.is_set():
            with self.database.session() as session:
                job = session.scalar(select(TrainingJob).where(TrainingJob.status == JobStatus.QUEUED).order_by(TrainingJob.created_at))
                if job:
                    self._run(session, job)
                else:
                    export = session.scalar(select(ExportJob).where(ExportJob.status == JobStatus.QUEUED).order_by(ExportJob.created_at))
                    if export:
                        self._run_export(session, export)
                    else:
                        prelabel = session.scalar(select(PrelabelJob).where(PrelabelJob.status == JobStatus.QUEUED).order_by(PrelabelJob.created_at))
                        if prelabel:
                            self._run_prelabel(session, prelabel)
            self.stop_event.wait(1)

    def _run(self, session, job: TrainingJob) -> None:
        dataset = session.get(DatasetVersion, job.dataset_version_id)
        if not dataset:
            job.status, job.error_message = JobStatus.FAILED, "数据集版本不存在"
            session.commit()
            return
        run_dir = self.root / job.run_path
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "request.json").write_text(job.params_json, encoding="utf-8")
        command = [
            sys.executable, "-m", "app.worker_runner", "--root", str(self.root),
            "--job", job.id, "--data", str(self.root / dataset.snapshot_path / "data.yaml"),
        ]
        log_path = run_dir / "train.log"
        job.status = JobStatus.RUNNING
        with log_path.open("a", encoding="utf-8") as log:
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(self.root / "backend")
            environment["YOLO_CONFIG_DIR"] = str(self.root / "resources")
            process = subprocess.Popen(command, cwd=self.root / "models" / "pretrained", env=environment, stdout=log, stderr=subprocess.STDOUT)
            job.pid = process.pid
            session.commit()
            while process.poll() is None:
                progress_path = run_dir / "progress.json"
                if progress_path.exists():
                    try:
                        progress = json.loads(progress_path.read_text(encoding="utf-8"))
                        job.current_epoch = int(progress.get("epoch", 0))
                        job.progress = int(progress.get("progress", 0))
                        session.commit()
                    except (OSError, ValueError):
                        pass
                time.sleep(1)
        session.refresh(job)
        if job.status == JobStatus.CANCELLED:
            return
        result_path = run_dir / "result.json"
        result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
        outcome = result.get("status")
        if outcome == "paused":
            job.status = JobStatus.PAUSED
        elif process.returncode == 0:
            job.status, job.progress = JobStatus.SUCCEEDED, 100
            self._collect_artifacts(session, job, run_dir)
        else:
            job.status = JobStatus.FAILED
            job.error_message = result.get("error", f"训练进程退出码 {process.returncode}")
        session.commit()

    def _run_prelabel(self, session, job: PrelabelJob) -> None:
        params = json.loads(job.params_json)
        assets = list(session.scalars(select(Asset).where(Asset.id.in_(params["assetIds"]))))
        work_dir = self.root / "runs" / "prelabels" / job.id
        work_dir.mkdir(parents=True, exist_ok=True)
        request = {
            **params, "modelPath": job.model_path,
            "assets": [{"id": asset.id, "path": asset.storage_path, "width": asset.width, "height": asset.height} for asset in assets],
        }
        request_path = work_dir / "request.json"
        request_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        job.status = JobStatus.RUNNING
        session.commit()
        result = subprocess.run(
            [sys.executable, "-m", "app.prelabel_runner", "--root", str(self.root), "--request", str(request_path)],
            cwd=self.root / "backend", capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        result_path = work_dir / "result.json"
        payload = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
        if result.returncode != 0:
            job.status, job.error_message = JobStatus.FAILED, payload.get("error") or result.stderr[-2000:]
            session.commit()
            return
        applied, skipped = 0, 0
        for document in payload.get("documents", []):
            current = session.scalar(select(Annotation).where(Annotation.asset_id == document["assetId"]))
            if current and current.status != "UNLABELED":
                skipped += 1
                continue
            if current:
                current.document_json, current.status, current.task = json.dumps(document, ensure_ascii=False), "DRAFT", job.task
                current.version += 1
            else:
                session.add(Annotation(id=str(uuid4()), asset_id=document["assetId"], task=job.task, status="DRAFT", document_json=json.dumps(document, ensure_ascii=False)))
            applied += 1
        job.status = JobStatus.SUCCEEDED
        job.result_json = json.dumps({"applied": applied, "skipped": skipped}, ensure_ascii=False)
        session.commit()

    def _collect_artifacts(self, session, job: TrainingJob, run_dir: Path) -> None:
        metrics = {}
        results_csv = next(iter(run_dir.rglob("results.csv")), None)
        if results_csv:
            with results_csv.open(encoding="utf-8", errors="replace") as handle:
                rows = list(csv.DictReader(handle))
                if rows:
                    metrics = {key.strip(): value.strip() if isinstance(value, str) else value for key, value in rows[-1].items()}
        for path in run_dir.rglob("*.pt"):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            relative = path.relative_to(self.root).as_posix()
            session.add(ModelArtifact(
                id=str(uuid4()), training_job_id=job.id, task=job.task, name=path.name,
                path=relative, kind="PT", sha256=digest, metrics_json=json.dumps(metrics, ensure_ascii=False),
            ))

    def _run_export(self, session, export: ExportJob) -> None:
        artifact = session.get(ModelArtifact, export.artifact_id)
        if not artifact:
            export.status, export.error_message = JobStatus.FAILED, "模型产物不存在"
            session.commit()
            return
        export_dir = self.root / "runs" / "exports" / export.id
        export_dir.mkdir(parents=True, exist_ok=True)
        request_path = export_dir / "request.json"
        request_path.write_text(json.dumps({"modelPath": artifact.path, **json.loads(export.params_json)}), encoding="utf-8")
        export.status = JobStatus.RUNNING
        session.commit()
        result = subprocess.run(
            [sys.executable, "-m", "app.export_runner", "--root", str(self.root), "--request", str(request_path)],
            cwd=self.root / "backend", capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        result_path = export_dir / "result.json"
        payload = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
        if result.returncode == 0 and payload.get("outputPath"):
            export.status, export.output_path = JobStatus.SUCCEEDED, payload["outputPath"]
        else:
            export.status = JobStatus.FAILED
            export.error_message = payload.get("error") or result.stdout[-2000:] or result.stderr[-2000:]
        session.commit()
