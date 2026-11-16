from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
import random
import re

from .architecture import SOFTWARE_CATEGORIES, normalize_software_category


SUPPORTED_LANGUAGES = [
    "自动选择",
    "Java",
    "JavaScript",
    "Python",
    "PHP",
    "C#",
    "C++",
    "HTML",
]

PRODUCT_TYPES = [
    "APP",
    "游戏软件",
    "教育软件",
    "金融软件",
    "医疗软件",
    "地理信息软件",
    "云计算软件",
    "信息安全软件",
    "大数据软件",
    "人工智能软件",
    "VR软件",
    "5G软件",
    "小程序",
    "物联网软件",
    "智慧城市软件",
]


def slugify(value: str, fallback: str = "software") -> str:
    cleaned = re.sub(r"[\x00-\x1f\x7f]+", " ", str(value or ""))
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "", cleaned).strip()
    cleaned = re.sub(r"\s+", "-", cleaned)
    cleaned = cleaned.strip(". ")
    if len(cleaned) > 80:
        cleaned = cleaned[:80].rstrip(". -_")
    return cleaned or fallback


def make_seed() -> str:
    suffix = random.randint(1000, 9999)
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{suffix}"


@dataclass
class GenerationTask:
    software_name: str
    version: str = "V1.0"
    language: str = "自动选择"
    product_type: str = "智慧城市软件"
    software_category: str = "应用软件"
    feature_hint: str = ""
    model_provider: str = "custom"
    model_name: str = "gpt-5.5"
    llm_base_url: str = ""
    llm_api_key_configured: bool = False
    randomness: str = "standard"
    seed: str = field(default_factory=make_seed)
    output_root: Path = field(default_factory=lambda: Path("output"))
    confirmed_outline: dict = field(default_factory=dict)
    accepted_blueprint_path: str = ""
    resume_output_dir: str = ""
    resume_existing_output: bool = False

    @property
    def safe_name(self) -> str:
        return slugify(self.software_name)

    @property
    def task_id(self) -> str:
        return f"{self.safe_name}-{self.seed}"

    @property
    def output_dir(self) -> Path:
        if str(self.resume_output_dir or "").strip():
            return Path(str(self.resume_output_dir))
        return self.output_root / self.task_id

    def to_dict(self) -> dict:
        self.software_category = normalize_software_category(self.software_category)
        data = asdict(self)
        # Task snapshots are persisted in generation reports. Keep connection
        # details in the runtime configuration rather than exported metadata.
        data["llm_base_url"] = ""
        data["llm_endpoint_configured"] = bool(self.llm_base_url)
        data["output_root"] = str(self.output_root)
        data["accepted_blueprint_path"] = str(self.accepted_blueprint_path or "")
        data["resume_output_dir"] = str(self.resume_output_dir or "")
        data["output_dir"] = str(self.output_dir)
        return data
