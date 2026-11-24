import hashlib
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


BACKUP_DIRECTORIES = ("data", "uploads", "models", "runs", "resources")


@dataclass(frozen=True)
class BackupRecord:
    label: str
    path: str
    created_at: str
    size_bytes: int


class BackupService:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.backups = self.root / "backups"
        self.backups.mkdir(parents=True, exist_ok=True)

    def create(self, label: str = "manual") -> BackupRecord:
        safe_label = re.sub(r"[^A-Za-z0-9_-]+", "-", label).strip("-") or "manual"
        created = datetime.now(timezone.utc)
        filename = f"vision-model-studio_{created.strftime('%Y%m%dT%H%M%SZ')}_{safe_label}.zip"
        output = self.backups / filename
        hashes: dict[str, str] = {}
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for directory in BACKUP_DIRECTORIES:
                source = self.root / directory
                if not source.is_dir():
                    continue
                for file_path in source.rglob("*"):
                    if not file_path.is_file() or file_path.is_symlink():
                        continue
                    relative = file_path.relative_to(self.root).as_posix()
                    archive.write(file_path, relative)
                    hashes[relative] = self._sha256(file_path)
            manifest = {
                "format": "vision-model-studio-backup/v1",
                "label": safe_label,
                "createdAt": created.isoformat(),
                "files": hashes,
            }
            archive.writestr("backup-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        return BackupRecord(safe_label, f"backups/{filename}", created.isoformat(), output.stat().st_size)

    def list(self) -> list[BackupRecord]:
        records = []
        for path in sorted(self.backups.glob("vision-model-studio_*.zip"), key=lambda item: item.stat().st_mtime, reverse=True):
            records.append(BackupRecord("saved", f"backups/{path.name}", datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(), path.stat().st_size))
        return records

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
