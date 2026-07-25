from __future__ import annotations

from typing import Literal


AugmentationPreset = Literal["none", "photometric", "robust", "full"]

PRESET_LABELS = {
    "none": "仅使用 YOLO 内置增强",
    "photometric": "光照与色彩",
    "robust": "噪声与压缩",
    "full": "综合增强",
}


def build_augmentations(preset: AugmentationPreset) -> list[object]:
    """Build task-safe Albumentations transforms for an Ultralytics train job.

    These presets intentionally contain pixel-level transforms only. Ultralytics
    applies them after loading labels, so detection, segmentation, pose, and OBB
    annotations are not silently desynchronized by a spatial transform.
    """
    if preset == "none":
        return []

    try:
        import albumentations as A
    except ImportError as error:
        raise RuntimeError(
            "当前环境未安装 Albumentations，无法使用素材增强方案；请安装 backend/requirements-base.txt 中的依赖后重试。"
        ) from error

    photometric = [
        A.RandomBrightnessContrast(brightness_limit=0.2, contrast_limit=0.2, p=0.35),
        A.HueSaturationValue(hue_shift_limit=10, sat_shift_limit=20, val_shift_limit=15, p=0.25),
        A.RandomGamma(gamma_limit=(80, 120), p=0.2),
        A.ToGray(p=0.05),
        A.CLAHE(clip_limit=(1, 4), p=0.05),
    ]
    robust = [
        A.Blur(blur_limit=3, p=0.08),
        A.MedianBlur(blur_limit=3, p=0.05),
        A.GaussNoise(p=0.08),
        A.ImageCompression(quality_range=(70, 100), p=0.08),
    ]
    if preset == "photometric":
        return photometric
    if preset == "robust":
        return robust
    return photometric + robust
