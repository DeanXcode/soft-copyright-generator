from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import zipfile
from uuid import uuid4


def write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)
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
    temp_path = zip_path.with_name(f".{zip_path.stem}.{uuid4().hex}.tmp.zip")
    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                if path.exists() and path.is_file():
                    archive.write(path, path.name)
        try:
            temp_path.replace(zip_path)
            return zip_path
        except PermissionError:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            fallback_path = zip_path.with_name(f"{zip_path.stem}-{timestamp}{zip_path.suffix}")
            temp_path.replace(fallback_path)
            return fallback_path
    finally:
        temp_path.unlink(missing_ok=True)

