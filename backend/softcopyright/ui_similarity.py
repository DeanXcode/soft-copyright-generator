from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any


SIMILARITY_THRESHOLD = 0.78
MAX_VISUAL_IDENTITY_ATTEMPTS = 3


@dataclass(frozen=True)
class UiSimilarityGateResult:
    ready: bool
    max_score: float
    attempts: int
    nearest_hash: str
    layout_role_count: int
    package_max_similarity: float = 0.0
    reason: str = ""
    fingerprint: dict[str, Any] | None = None

    def to_checks(self) -> dict[str, Any]:
        return {
            "ui_similarity_gate_ready": self.ready,
            "ui_similarity_max_score": self.max_score,
            "ui_similarity_attempts": self.attempts,
            "ui_similarity_nearest_hash": self.nearest_hash,
            "ui_layout_role_count": self.layout_role_count,
            "ui_package_page_max_similarity": self.package_max_similarity,
            "ui_similarity_reason": self.reason,
        }


def ui_structure_fingerprint(ui_blueprint: Any, ui_screenshots: dict | None = None) -> dict[str, Any]:
    brief = getattr(ui_blueprint, "design_brief", {}) or {}
    experience = brief.get("product_experience_spec") if isinstance(brief.get("product_experience_spec"), dict) else {}
    identity = brief.get("visual_identity_spec") if isinstance(brief.get("visual_identity_spec"), dict) else {}
    screens = list(getattr(ui_blueprint, "screens", []) or [])
    view_sequence = [str(getattr(screen, "view_type", "") or "") for screen in screens if str(getattr(screen, "view_type", "") or "")]
    module_view_sequence = [
        str(getattr(screen, "view_type", "") or "")
        for screen in screens
        if str(getattr(screen, "module_key", "") or "").strip()
    ]
    page_kinds: list[str] = []
    module_keys: list[str] = []
    if isinstance(ui_screenshots, dict):
        for item in ui_screenshots.values():
            page_kinds.append(str(getattr(item, "page_kind", "") or "general"))
            module_key = str(getattr(item, "module_key", "") or "")
            if module_key:
                module_keys.append(module_key)
    component_tokens = _component_tokens(screens, brief)
    payload: dict[str, Any] = {
        "renderer": str(getattr(ui_blueprint, "renderer", "") or ""),
        "source": str(getattr(ui_blueprint, "source", "") or ""),
        "software_category": str(experience.get("software_category") or brief.get("software_category") or ""),
        "product_type": str(experience.get("product_type") or brief.get("product_type") or ""),
        "experience_shape": str(experience.get("experience_shape") or brief.get("experience_shape") or ""),
        "experience_shell": str(experience.get("shell") or brief.get("experience_shell") or ""),
        "layout_variant": str(identity.get("layout_variant") or brief.get("layout_variant") or brief.get("layout_family") or ""),
        "nav_model": str(identity.get("nav_model") or brief.get("nav_model") or ""),
        "workspace_shape": str(identity.get("workspace_shape") or brief.get("workspace_shape") or ""),
        "login_pattern": str(identity.get("login_pattern") or brief.get("login_pattern") or ""),
        "dashboard_composition": str(identity.get("dashboard_composition") or brief.get("dashboard_pattern") or ""),
        "module_composition_cycle": _string_list(identity.get("module_composition_cycle") or brief.get("module_composition_cycle")),
        "view_type_sequence": view_sequence,
        "module_view_type_sequence": module_view_sequence,
        "page_kinds": page_kinds,
        "module_keys": module_keys,
        "component_tokens": component_tokens,
        "palette_key": str(identity.get("palette_key") or brief.get("palette_key") or ""),
        "table_density": str(identity.get("table_density") or brief.get("table_density") or ""),
        "chart_style": str(identity.get("chart_style") or brief.get("chart_style") or ""),
        "surface_style": str(identity.get("surface_style") or brief.get("surface_style") or ""),
        "component_rhythm": str(identity.get("component_rhythm") or brief.get("component_rhythm") or ""),
        "visual_identity_signature": str(identity.get("identity_signature") or brief.get("identity_signature") or ""),
        "screen_count": len(screens),
        "page_count": len(page_kinds),
        "layout_role_count": _layout_role_count_from_sequences(view_sequence, module_view_sequence),
    }
    payload["fingerprint_hash"] = _hash_payload(payload)
    return payload


def ui_similarity_score(current: dict[str, Any], baseline: dict[str, Any]) -> float:
    weights = {
        "renderer": 0.04,
        "experience_shape": 0.03,
        "layout_variant": 0.14,
        "nav_model": 0.10,
        "workspace_shape": 0.10,
        "login_pattern": 0.06,
        "dashboard_composition": 0.08,
        "view_type_sequence": 0.16,
        "module_composition_cycle": 0.12,
        "page_kinds": 0.02,
        "component_tokens": 0.05,
        "palette_key": 0.06,
        "chart_style": 0.04,
    }
    score = 0.0
    for key, weight in weights.items():
        if key in {"view_type_sequence", "module_composition_cycle"}:
            part = _sequence_similarity(_string_list(current.get(key)), _string_list(baseline.get(key)))
        elif key in {"page_kinds", "component_tokens"}:
            part = _jaccard(_string_list(current.get(key)), _string_list(baseline.get(key)))
        else:
            part = 1.0 if str(current.get(key) or "") and str(current.get(key) or "") == str(baseline.get(key) or "") else 0.0
        score += weight * part
    return round(min(max(score, 0.0), 1.0), 4)


def evaluate_ui_similarity_gate(
    *,
    task: Any,
    ui_blueprint: Any,
    ui_screenshots: dict | None,
    output_root: Path,
    attempt: int,
    ignore_current_history: bool = False,
    evaluate_package_pages: bool = True,
) -> UiSimilarityGateResult:
    fingerprint = ui_structure_fingerprint(ui_blueprint, ui_screenshots)
    fingerprint["source_task_id"] = str(getattr(task, "task_id", "") or "")
    fingerprint["source_software_name"] = str(getattr(task, "software_name", "") or "")
    layout_role_count = int(fingerprint.get("layout_role_count") or 0)
    package_score, package_reason = _package_page_similarity(ui_screenshots) if evaluate_package_pages else (0.0, "")
    if _is_local_template_task(task):
        package_reason = ""
    if package_reason:
        return UiSimilarityGateResult(
            ready=False,
            max_score=0.0,
            attempts=attempt + 1,
            nearest_hash="",
            layout_role_count=layout_role_count,
            package_max_similarity=package_score,
            reason=package_reason,
            fingerprint=fingerprint,
        )
    role_ready, role_reason = _layout_role_ready(fingerprint)
    if not role_ready:
        return UiSimilarityGateResult(
            ready=False,
            max_score=0.0,
            attempts=attempt + 1,
            nearest_hash="",
            layout_role_count=layout_role_count,
            package_max_similarity=package_score,
            reason=role_reason,
            fingerprint=fingerprint,
        )
    baselines = _matching_history(output_root, fingerprint)
    if ignore_current_history:
        current_hash = str(fingerprint.get("fingerprint_hash") or "")
        current_task_id = str(fingerprint.get("source_task_id") or "")
        baselines = [
            baseline
            for baseline in baselines
            if str(baseline.get("source_task_id") or "") != current_task_id
            and str(baseline.get("fingerprint_hash") or "") != current_hash
        ]
    if not baselines:
        return UiSimilarityGateResult(
            ready=True,
            max_score=0.0,
            attempts=attempt + 1,
            nearest_hash="",
            layout_role_count=layout_role_count,
            package_max_similarity=package_score,
            reason="no_history_baseline",
            fingerprint=fingerprint,
        )
    nearest_score = 0.0
    nearest_hash = ""
    for baseline in baselines[-50:]:
        score = ui_similarity_score(fingerprint, baseline)
        if score > nearest_score:
            nearest_score = score
            nearest_hash = str(baseline.get("fingerprint_hash") or "")
    ready = nearest_score < SIMILARITY_THRESHOLD
    return UiSimilarityGateResult(
        ready=ready,
        max_score=nearest_score,
        attempts=attempt + 1,
        nearest_hash=nearest_hash,
        layout_role_count=layout_role_count,
        package_max_similarity=package_score,
        reason="" if ready else "ui_similarity_too_high",
        fingerprint=fingerprint,
    )


def append_ui_fingerprint_history(output_root: Path, fingerprint: dict[str, Any]) -> None:
    index_path = _history_index_path(output_root)
    records = _read_history_records(index_path)
    clean = dict(fingerprint)
    clean.pop("source", None)
    records.append(clean)
    if len(records) > 500:
        records = records[-500:]
    index_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = index_path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps({"version": 1, "records": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(index_path)


def _layout_role_ready(fingerprint: dict[str, Any]) -> tuple[bool, str]:
    renderer = str(fingerprint.get("renderer") or "")
    if renderer != "admin":
        return True, ""
    module_count = len(_string_list(fingerprint.get("module_keys"))) or len(_string_list(fingerprint.get("module_view_type_sequence")))
    required = 3 if module_count and module_count < 4 else 4
    actual = int(fingerprint.get("layout_role_count") or 0)
    if actual < required:
        return False, "ui_layout_role_count_low"
    return True, ""


def _matching_history(output_root: Path, fingerprint: dict[str, Any]) -> list[dict[str, Any]]:
    records = _read_history_records(_history_index_path(output_root))
    product_type = str(fingerprint.get("product_type") or "")
    experience_shape = str(fingerprint.get("experience_shape") or "")
    return [
        record
        for record in records
        if isinstance(record, dict)
        and str(record.get("product_type") or "") == product_type
        and str(record.get("experience_shape") or "") == experience_shape
    ][-50:]


def _package_page_similarity(ui_screenshots: dict | None) -> tuple[float, str]:
    if not isinstance(ui_screenshots, dict):
        return 0.0, ""
    vectors: list[tuple[set[str], str, str, str]] = []
    for item in ui_screenshots.values():
        page_kind = str(getattr(item, "page_kind", "") or "")
        if page_kind not in {"module", "operation", "dashboard", "statistics"}:
            continue
        html_path = Path(str(getattr(item, "html_path", "") or ""))
        if not html_path.exists():
            continue
        try:
            html = html_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        html = _react_component_structure_source(html_path, html)
        tokens = _page_structure_tokens(html, page_kind)
        if tokens:
            vectors.append(
                (
                    tokens,
                    page_kind,
                    str(getattr(item, "interaction_mode", "") or ""),
                    str(getattr(item, "interaction_surface", "") or ""),
                )
            )
    if len(vectors) < 4:
        return 0.0, ""
    max_score = 0.0
    for left_index, (left, left_kind, left_mode, left_surface) in enumerate(vectors):
        for right, right_kind, right_mode, right_surface in vectors[left_index + 1 :]:
            # Reusing the same query/form/result component across modules is a
            # deliberate design-system property. Diversity is required between
            # distinct operation surfaces and between primary module pages,
            # not between two instances of the same operation component.
            if (
                left_kind == right_kind == "operation"
                and left_mode
                and left_mode == right_mode
                and left_surface == right_surface
            ):
                continue
            score = _set_similarity(left, right)
            if score > max_score:
                max_score = score
    if max_score >= 0.86:
        return round(max_score, 4), "ui_package_pages_too_similar"
    return round(max_score, 4), ""


def _react_component_structure_source(html_path: Path, html: str) -> str:
    match = re.search(r'<meta\s+name=["\']soft-react-screen["\']\s+content=["\']([^"\']+)', html, flags=re.I)
    if not match:
        return html
    page_key = match.group(1)
    screens_dir = html_path.parent / "react-app" / "src" / "screens"
    if not screens_dir.exists():
        return html
    for meta_path in screens_dir.glob("*.meta.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if str(meta.get("page_key") or "") != page_key:
            continue
        jsx_path = meta_path.with_suffix("").with_suffix(".jsx")
        css_path = meta_path.with_suffix("").with_suffix(".css")
        parts = [html]
        for path in (jsx_path, css_path):
            try:
                parts.append(path.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                pass
        return "\n".join(parts)
    return html


def _is_local_template_task(task: Any) -> bool:
    provider = str(getattr(task, "model_provider", "") or "").strip().lower()
    return provider in {"", "local", "local-template", "template"}


def _page_structure_tokens(html: str, page_kind: str) -> set[str]:
    text = str(html or "")
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.S | re.I)
    tokens = {f"kind:{page_kind}"}
    class_hits = re.findall(r"class(?:Name)?=(?:\"([^\"]+)\"|'([^']+)')", text, flags=re.I)
    for left, right in class_hits:
        for cls in (left or right).split():
            if cls and not cls.startswith(("identity-", "density-", "chart-", "surface-", "rhythm-")):
                tokens.add("class:" + cls[:32])
    for tag in re.findall(r"</?([a-z][a-z0-9-]*)\b", text, flags=re.I):
        if tag.lower() in {"section", "aside", "main", "table", "nav", "header", "canvas", "article", "form"}:
            tokens.add("tag:" + tag.lower())
    for marker in [
        "table-frame",
        "runtime-record-panel",
        "map-pin",
        "operation-result",
        "query-grid",
        "upload-zone",
        "approval-step",
        "mini-chart",
        "kanban",
        "timeline",
        "matrix",
        "dashboard",
        "op-query-page",
        "op-import-page",
        "op-export-page",
        "op-stat-page",
        "op-review-page",
    ]:
        if marker in text:
            tokens.add("marker:" + marker)
    return tokens


def _set_similarity(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _history_index_path(output_root: Path) -> Path:
    return Path(output_root) / ".ui-fingerprint-history" / "index.json"


def _read_history_records(index_path: Path) -> list[dict[str, Any]]:
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    records = data.get("records") if isinstance(data, dict) else []
    if not isinstance(records, list):
        return []
    return [item for item in records if isinstance(item, dict)]


def _layout_role_count_from_sequences(view_sequence: list[str], module_view_sequence: list[str]) -> int:
    sequence = module_view_sequence or [
        value
        for value in view_sequence
        if value and value not in {"admin_login", "admin_dashboard", "admin_statistics", "mobile_login", "mobile_home", "mobile_statistics"}
    ]
    return len({value for value in sequence if value})


def _component_tokens(screens: list[Any], brief: dict[str, Any]) -> list[str]:
    tokens: list[str] = []
    for key in ["dashboard_pattern", "module_pattern", "workspace_shape", "chart_style", "table_density", "surface_style"]:
        value = str(brief.get(key) or "").strip()
        if value:
            tokens.append(value)
    for screen in screens:
        view_type = str(getattr(screen, "view_type", "") or "").strip()
        if view_type:
            tokens.append(view_type)
        for component in getattr(screen, "components", []) or []:
            value = str(component or "").strip()
            if value:
                tokens.append(value[:18])
    return sorted(set(tokens))


def _sequence_similarity(left: list[str], right: list[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    positional = sum(1 for index, value in enumerate(left) if index < len(right) and value == right[index]) / max(len(left), len(right))
    set_score = _jaccard(left, right)
    return (positional * 0.65) + (set_score * 0.35)


def _jaccard(left: list[str], right: list[str]) -> float:
    left_set = {str(item) for item in left if str(item)}
    right_set = {str(item) for item in right if str(item)}
    if not left_set and not right_set:
        return 1.0
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _hash_payload(payload: dict[str, Any]) -> str:
    stable = {key: value for key, value in payload.items() if key != "fingerprint_hash"}
    return sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]
