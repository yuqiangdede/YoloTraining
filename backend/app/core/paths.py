from pathlib import Path, PureWindowsPath


class ProjectPaths:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def resolve(self, relative_path: str) -> Path:
        windows_path = PureWindowsPath(relative_path)
        if windows_path.is_absolute() or windows_path.drive:
            raise ValueError("只允许使用项目内相对路径")
        candidate = (self.root / Path(relative_path)).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("路径不能离开项目目录")
        return candidate

    def relative(self, path: Path) -> str:
        resolved = path.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise ValueError("路径不在项目目录内")
        return resolved.relative_to(self.root).as_posix()
