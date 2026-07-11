import platform
import shutil
import subprocess
import sys

from fastapi import APIRouter, Request


router = APIRouter(prefix="/system", tags=["system"])


@router.get("/environment")
def environment(request: Request) -> dict:
    root = request.app.state.root
    gpu = {"isAvailable": False, "name": None, "cuda": None, "memoryBytes": None}
    try:
        import torch
        gpu = {
            "isAvailable": torch.cuda.is_available(),
            "name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "cuda": torch.version.cuda,
            "memoryBytes": torch.cuda.get_device_properties(0).total_memory if torch.cuda.is_available() else None,
        }
    except ImportError:
        pass
    disk = shutil.disk_usage(root)
    return {
        "python": sys.version.split()[0], "platform": platform.platform(), "gpu": gpu,
        "disk": {"totalBytes": disk.total, "freeBytes": disk.free},
        "projectRoot": root.as_posix(), "venvIsLocal": (root / ".venv").is_dir(),
    }
