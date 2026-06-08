from __future__ import annotations

from pathlib import Path
import json
import zipfile


def write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def make_zip(source_dir: Path, zip_path: Path) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in source_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.resolve() == zip_path.resolve():
                continue
            archive.write(path, path.relative_to(source_dir.parent))
    return zip_path


def make_zip_files(files: list[Path], zip_path: Path) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            if path.exists() and path.is_file():
                archive.write(path, path.name)
    return zip_path

