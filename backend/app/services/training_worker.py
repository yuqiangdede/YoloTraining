import hashlib
import csv
import json
import os
import subprocess
import sys
import threading
import time
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, update

from app.core.database import Database
from app.models import Annotation, Asset, DatasetCategory, DatasetVersion, ExportJob, ModelArtifact, PrelabelJob, TrainingJob, VideoInferenceJob
from app.services.state_machine import JobStatus
from app.services.training_metrics import summarize_results


class TrainingWorker:
    def __init__(self, root: Path, database: Database) -> None:
        self.root = root
        self.database = database
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self._state_lock = threading.Lock()
        self._current_job_id: str | None = None
        self._current_kind: str | None = None
        self._current_started_at: datetime | None = None
        self._last_activity_at: datetime | None = None
        self._last_error: str | None = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self._recover_interrupted()
        self.thread = threading.Thread(target=self._loop, name="training-worker", daemon=True)
        self.thread.start()

    def health(self) -> dict:
        with self._state_lock:
            return {
                "alive": bool(self.thread and self.thread.is_alive()),
                "currentJobId": self._current_job_id,
                "currentKind": self._current_kind,
                "currentStartedAt": self._current_started_at.isoformat() if self._current_started_at else None,
                "lastActivityAt": self._last_activity_at.isoformat() if self._last_activity_at else None,
                "lastError": self._last_error,
            }

    def _touch(self) -> None:
        with self._state_lock:
            self._last_activity_at = datetime.now(timezone.utc)

    def _set_current(self, kind: str | None, job_id: str | None) -> None:
        with self._state_lock:
            self._current_kind = kind
            self._current_job_id = job_id
            self._current_started_at = datetime.now(timezone.utc) if job_id else None

    def _set_error(self, error: Exception | str | None) -> None:
        with self._state_lock:
            self._last_error = str(error) if error else None

    def _recover_interrupted(self) -> None:
        with self.database.session() as session:
            for model in (TrainingJob, ExportJob, PrelabelJob, VideoInferenceJob):
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
            self._touch()
            try:
                with self.database.session() as session:
                    kind, item = self._next_queued(session)
                    if kind and item:
                        self._set_current(kind, item.id)
                    if kind == "training":
                        self._run(session, item)
                    elif kind == "export":
                        self._run_export(session, item)
                    elif kind == "prelabel":
                        self._run_prelabel(session, item)
                    elif kind == "video":
                        self._run_video(session, item)
                    self._set_error(None)
            except Exception as error:
                self._set_error(error)
                self._mark_failed_after_worker_error()
            finally:
                self._set_current(None, None)
            self.stop_event.wait(1)

    def _mark_failed_after_worker_error(self) -> None:
        with self._state_lock:
            job_id, kind = self._current_job_id, self._current_kind
        if not job_id:
            return
        model = {"training": TrainingJob, "export": ExportJob, "prelabel": PrelabelJob, "video": VideoInferenceJob}.get(kind or "")
        if not model:
            return
        try:
            with self.database.session() as session:
                item = session.get(model, job_id)
                if item and item.status in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.PAUSING}:
                    item.status = JobStatus.FAILED
                    item.error_message = f"工作线程异常：{self._last_error}"
                    session.commit()
        except Exception:
            pass

    def _next_queued(self, session):
        candidates = [
            ("training", session.scalar(select(TrainingJob).where(TrainingJob.status == JobStatus.QUEUED).order_by(TrainingJob.created_at))),
            ("export", session.scalar(select(ExportJob).where(ExportJob.status == JobStatus.QUEUED).order_by(ExportJob.created_at))),
            ("prelabel", session.scalar(select(PrelabelJob).where(PrelabelJob.status == JobStatus.QUEUED).order_by(PrelabelJob.created_at))),
            ("video", session.scalar(select(VideoInferenceJob).where(VideoInferenceJob.status == JobStatus.QUEUED).order_by(VideoInferenceJob.created_at))),
        ]
        ready = [(kind, item) for kind, item in candidates if item]
        return min(ready, key=lambda candidate: candidate[1].created_at) if ready else (None, None)

    def _run_video(self, session, job: VideoInferenceJob) -> None:
        claimed = session.execute(
            update(VideoInferenceJob)
            .where(VideoInferenceJob.id == job.id, VideoInferenceJob.status == JobStatus.QUEUED)
            .values(status=JobStatus.RUNNING)
        ).rowcount
        if claimed != 1:
            session.rollback()
            return
        session.commit()
        session.refresh(job)
        work_dir = self.root / "runs" / "video-inference" / job.id
        temp_output = work_dir / "annotated-silent.mp4"
        output_path = self.root / job.output_path if job.output_path else work_dir / "output.mp4"
        work_dir.mkdir(parents=True, exist_ok=True)
        capture = None
        writer = None
        try:
            import cv2
            from app.api.models import _get_cached_model

            capture = cv2.VideoCapture(str(self.root / job.input_path))
            if not capture.isOpened():
                raise ValueError("视频无法打开，请确认文件编码和格式有效")
            total_frames = max(0, int(capture.get(cv2.CAP_PROP_FRAME_COUNT)))
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0) or 25.0
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if width <= 0 or height <= 0:
                raise ValueError("视频没有有效的画面尺寸")
            job.total_frames, job.fps, job.width, job.height = total_frames, fps, width, height
            session.commit()
            writer = cv2.VideoWriter(str(temp_output), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
            if not writer.isOpened():
                raise ValueError("无法创建视频输出文件")
            model = _get_cached_model(self.root / job.model_path)
            confidence = json.loads(job.params_json)["confidence"]
            frame_number = 0
            while True:
                if frame_number == 0 or frame_number % 5 == 0:
                    session.refresh(job)
                    if job.status == JobStatus.CANCELLED:
                        temp_output.unlink(missing_ok=True)
                        return
                ok, frame = capture.read()
                if not ok:
                    break
                result = model.predict(frame, conf=confidence, verbose=False)[0]
                writer.write(result.plot())
                frame_number += 1
                job.current_frame = frame_number
                job.progress = min(99, round(frame_number * 100 / total_frames)) if total_frames else 0
                if frame_number == 1 or frame_number % 5 == 0:
                    session.commit()
            if frame_number == 0:
                raise ValueError("视频没有可读取的画面")
            session.commit()
        except Exception as error:
            job.status = JobStatus.FAILED
            job.error_message = str(error)
            session.commit()
            return
        finally:
            if capture is not None:
                capture.release()
            if writer is not None:
                writer.release()
        try:
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise ValueError("未找到 FFmpeg，无法生成浏览器可播放的 MP4")
            subprocess.run([
                ffmpeg, "-y", "-i", str(temp_output), "-i", str(self.root / job.input_path),
                "-map", "0:v:0", "-map", "1:a?", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(output_path),
            ], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")
            job.output_path = output_path.resolve().relative_to(self.root.resolve()).as_posix()
            job.progress = 100
            job.status = JobStatus.SUCCEEDED
            session.commit()
        except subprocess.CalledProcessError as error:
            job.status = JobStatus.FAILED
            job.error_message = (error.stderr or "FFmpeg 视频编码失败")[-2000:]
            session.commit()
        except Exception as error:
            job.status = JobStatus.FAILED
            job.error_message = str(error)
            session.commit()
        finally:
            temp_output.unlink(missing_ok=True)

    def _run(self, session, job: TrainingJob) -> None:
        claimed = session.execute(
            update(TrainingJob)
            .where(TrainingJob.id == job.id, TrainingJob.status == JobStatus.QUEUED)
            .values(status=JobStatus.RUNNING)
        ).rowcount
        if claimed != 1:
            session.rollback()
            return
        session.commit()
        session.refresh(job)
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
        if params.get("mode") in {"yolo_sam", "sam"}:
            dataset_ids = {asset.dataset_id for asset in assets}
            if len(dataset_ids) != 1:
                raise ValueError("SAM prelabel assets must belong to one dataset")
            categories = list(session.scalars(select(DatasetCategory).where(DatasetCategory.dataset_id == next(iter(dataset_ids)))))
            request["samModelPath"] = "models/pretrained/sam3.pt"
            request["categoryNames"] = [category.name for category in categories]
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
        dataset_ids = {asset.dataset_id for asset in assets}
        if len(dataset_ids) != 1:
            raise ValueError("预标注素材必须属于同一个数据集")
        category_ids = {item.name.casefold(): item.id for item in session.scalars(select(DatasetCategory).where(DatasetCategory.dataset_id == next(iter(dataset_ids))))}
        applied, skipped, unmatched = 0, 0, {}
        for document in payload.get("documents", []):
            matched_shapes = []
            for shape in document.get("shapes", []):
                model_label = str(shape.get("labelId", ""))
                category_id = category_ids.get(model_label.casefold())
                if category_id is None:
                    unmatched[model_label] = unmatched.get(model_label, 0) + 1
                    continue
                shape["labelId"] = category_id
                matched_shapes.append(shape)
            document["shapes"] = matched_shapes
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
        job.result_json = json.dumps({"applied": applied, "skipped": skipped, "unmatchedCategories": unmatched}, ensure_ascii=False)
        session.commit()

    def _collect_artifacts(self, session, job: TrainingJob, run_dir: Path) -> None:
        metrics = {}
        rows = []
        results_csv = next(iter(run_dir.rglob("results.csv")), None)
        if results_csv:
            with results_csv.open(encoding="utf-8", errors="replace") as handle:
                rows = list(csv.DictReader(handle))
                if rows:
                    metrics = {key.strip(): value.strip() if isinstance(value, str) else value for key, value in rows[-1].items()}
        training_quality = summarize_results(rows, job.task)
        for path in run_dir.rglob("*.pt"):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            relative = path.relative_to(self.root).as_posix()
            artifact = ModelArtifact(
                id=str(uuid4()), training_job_id=job.id, task=job.task, name=path.name,
                path=relative, kind="PT", sha256=digest, metrics_json=json.dumps(metrics, ensure_ascii=False),
                training_quality_json=json.dumps(training_quality, ensure_ascii=False),
            )
            session.add(artifact)
            session.add(ExportJob(
                id=str(uuid4()), artifact_id=artifact.id, format="onnx", status=JobStatus.QUEUED, progress=0,
                params_json=json.dumps({"format": "onnx", "imgsz": 640}, ensure_ascii=False),
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
        export.progress = 10
        session.commit()
        result = subprocess.run(
            [sys.executable, "-m", "app.export_runner", "--root", str(self.root), "--request", str(request_path)],
            cwd=self.root / "backend", capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        result_path = export_dir / "result.json"
        payload = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
        if result.returncode == 0 and payload.get("outputPath"):
            export.status, export.progress, export.output_path = JobStatus.SUCCEEDED, 100, payload["outputPath"]
        else:
            export.status, export.progress = JobStatus.FAILED, 100
            export.error_message = payload.get("error") or result.stdout[-2000:] or result.stderr[-2000:]
        session.commit()
