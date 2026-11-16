from __future__ import annotations

from dataclasses import fields
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .architecture import TechnicalArchitecture, create_technical_architecture
from .blueprint import FeatureModule, ProductBlueprint
from .models import GenerationTask
from .module_keys import is_placeholder_module_key, normalize_entity_names, semantic_module_key
from .ui_blueprint import UiBlueprint, UiScreenBlueprint


CACHE_SCHEMA_VERSION = 2
MANUAL_SECTION_KEYS = ("overview", "login_main", "statistics", "security", "faq")


def stage_cache_enabled() -> bool:
    value = os.getenv("SOFT_STAGE_CACHE_DISABLED", "").strip().lower()
    return value not in {"1", "true", "yes", "on"}


def build_stage_cache_context(task: GenerationTask, feature_hint_meta: dict[str, Any]) -> dict[str, Any]:
    enabled = stage_cache_enabled()
    fingerprint = _cache_fingerprint(task, feature_hint_meta)
    cache_dir = task.output_root / ".stage-cache" / fingerprint
    expected_titles = _expected_module_titles(feature_hint_meta)
    return {
        "enabled": enabled,
        "key": fingerprint,
        "dir": cache_dir,
        "expected_module_titles": expected_titles,
        "resume_existing_output": bool(getattr(task, "resume_existing_output", False)),
        "manifest": {
            "schema_version": CACHE_SCHEMA_VERSION,
            "software_name": task.software_name,
            "version": task.version,
            "product_type": task.product_type,
            "software_category": task.software_category,
            "model_provider": task.model_provider,
            "model_name": task.model_name,
            "randomness": task.randomness,
            "seed": task.seed,
            "cache_key": fingerprint,
        },
    }


def find_resume_stage_cache_context(task: GenerationTask) -> dict[str, Any] | None:
    """Find the exact stage cache created by an earlier run of the same task seed.

    Resume must not depend on a fresh LLM feature-inference response: the gateway may be
    temporarily unavailable even though the completed product blueprint is already local.
    """
    roots: list[Path] = [Path(task.output_root)]
    resume_output_dir = str(getattr(task, "resume_output_dir", "") or "").strip()
    if resume_output_dir:
        roots.append(Path(resume_output_dir).parent)
    seen: set[str] = set()
    for root in roots:
        cache_root = root / ".stage-cache"
        resolved = str(cache_root.resolve())
        if resolved in seen or not cache_root.is_dir():
            continue
        seen.add(resolved)
        for cache_dir in cache_root.iterdir():
            if not cache_dir.is_dir():
                continue
            manifest_path = cache_dir / "manifest.json"
            blueprint_path = cache_dir / "blueprint.json"
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                blueprint_data = json.loads(blueprint_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(manifest, dict) or not isinstance(blueprint_data, dict):
                continue
            expected = {
                "software_name": str(task.software_name or ""),
                "version": str(task.version or ""),
                "product_type": str(task.product_type or ""),
                "software_category": str(task.software_category or ""),
                "seed": str(task.seed or ""),
            }
            if any(str(manifest.get(key) or "") != value for key, value in expected.items()):
                continue
            modules = blueprint_data.get("modules")
            expected_titles = [
                str(item.get("title") or "").strip()
                for item in modules
                if isinstance(item, dict) and str(item.get("title") or "").strip()
            ] if isinstance(modules, list) else []
            return {
                "enabled": stage_cache_enabled(),
                "key": str(manifest.get("cache_key") or cache_dir.name),
                "dir": cache_dir,
                "expected_module_titles": expected_titles,
                "resume_existing_output": True,
                "manifest": manifest,
            }
    return None


def load_cached_blueprint(context: dict[str, Any]) -> ProductBlueprint | None:
    data = _read_stage(context, "blueprint.json")
    if not data:
        return None
    try:
        blueprint = product_blueprint_from_dict(data)
    except Exception:
        return None
    if len(blueprint.modules) < 6 or not blueprint.quality_score:
        return None
    return blueprint


def save_cached_blueprint(context: dict[str, Any], blueprint: ProductBlueprint) -> None:
    _write_stage(context, "blueprint.json", blueprint.to_dict())


def load_cached_architecture(context: dict[str, Any]) -> TechnicalArchitecture | None:
    data = _read_stage(context, "technical_architecture.json")
    if not data:
        return None
    try:
        return technical_architecture_from_dict(data)
    except Exception:
        return None


def save_cached_architecture(context: dict[str, Any], architecture: TechnicalArchitecture) -> None:
    _write_stage(context, "technical_architecture.json", architecture.to_dict())


def load_cached_manual_content(context: dict[str, Any], blueprint: ProductBlueprint) -> dict[str, Any] | None:
    data = _read_stage(context, "manual_content.json")
    data = remap_manual_content_for_blueprint(data, blueprint)
    if not _manual_content_ready(data, blueprint):
        return None
    return data


def save_cached_manual_content(context: dict[str, Any], manual_content: dict[str, Any]) -> None:
    payload = {key: value for key, value in manual_content.items() if key != "_warnings"}
    _write_stage(context, "manual_content.json", payload)


def load_partial_manual_content(context: dict[str, Any], blueprint: ProductBlueprint) -> dict[str, Any]:
    data = _read_stage(context, "manual_content.partial.json") or {}
    if data.get("blueprint_digest") != _manual_blueprint_digest(blueprint):
        return {"modules": {}}
    from .llm_manual import _module_content_from_data, _section_paragraphs_from_data, _section_specs

    result: dict[str, Any] = {"modules": {}}
    content = data.get("content")
    if not isinstance(content, dict):
        return result
    for key, _title, _hint, min_count, _budget, limit in _section_specs():
        paragraphs = _section_paragraphs_from_data(content, key, min_count, limit)
        if paragraphs:
            result[key] = paragraphs
    for module in blueprint.modules:
        raw_module = (content.get("modules") or {}).get(module.key) if isinstance(content.get("modules"), dict) else None
        if not isinstance(raw_module, dict) or str(raw_module.get("title") or "") != module.title:
            continue
        module_content = _module_content_from_data(content, module)
        if module_content:
            result["modules"][module.key] = module_content
    return result


def save_partial_manual_content(
    context: dict[str, Any], blueprint: ProductBlueprint, manual_content: dict[str, Any]
) -> None:
    payload = {key: value for key, value in manual_content.items() if key != "_warnings"}
    _write_stage(context, "manual_content.partial.json", {
        "blueprint_digest": _manual_blueprint_digest(blueprint),
        "content": payload,
    })


def _manual_blueprint_digest(blueprint: ProductBlueprint) -> str:
    serialized = json.dumps(blueprint.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def load_cached_ui_blueprint(context: dict[str, Any], blueprint: ProductBlueprint | None = None) -> UiBlueprint | None:
    data = _read_stage(context, "ui_blueprint.json")
    if not _ui_blueprint_ready(data):
        return None
    if blueprint is not None:
        data = remap_ui_blueprint_for_blueprint(data, blueprint)
    try:
        return ui_blueprint_from_dict(data)
    except Exception:
        return None


def save_cached_ui_blueprint(context: dict[str, Any], ui_blueprint: UiBlueprint) -> None:
    if ui_blueprint.source != "llm":
        return
    payload = ui_blueprint.to_dict()
    design_brief = dict(payload.get("design_brief") or {})
    design_brief.pop("source_ui_evidence", None)
    payload["design_brief"] = design_brief
    _write_stage(context, "ui_blueprint.json", payload)


def product_blueprint_from_dict(data: dict[str, Any]) -> ProductBlueprint:
    key_map: dict[str, str] = {}
    used_keys: set[str] = set()
    modules = [
        _feature_module_from_cached_item(item, index, key_map, used_keys)
        for index, item in enumerate(data.get("modules", []), start=1)
        if isinstance(item, dict) and str(item.get("title") or "").strip()
    ]
    kwargs = {
        "software_name": str(data.get("software_name") or ""),
        "version": str(data.get("version") or "V1.0"),
        "language": str(data.get("language") or "自动选择"),
        "product_type": str(data.get("product_type") or "APP"),
        "industry": str(data.get("industry") or ""),
        "purpose": str(data.get("purpose") or ""),
        "summary": str(data.get("summary") or ""),
        "modules": [module for module in modules if module is not None],
        "roles": _string_list(data.get("roles")),
        "pages": _string_list(data.get("pages")),
        "dev_environment": _string_dict(data.get("dev_environment")),
        "runtime_environment": _string_dict(data.get("runtime_environment")),
    }
    optional_names = {
        item.name
        for item in fields(ProductBlueprint)
        if item.name not in kwargs and item.name != "modules"
    }
    for name in optional_names:
        value = data.get(name)
        if name == "workflows" and isinstance(value, list):
            kwargs[name] = [_remap_module_key_in_mapping(item, key_map) for item in value if isinstance(item, dict)]
        elif name == "technical_architecture" and isinstance(value, dict):
            kwargs[name] = value
        elif isinstance(value, list):
            kwargs[name] = _string_list(value)
        elif isinstance(value, dict):
            kwargs[name] = value
        elif value is not None:
            kwargs[name] = value
    return ProductBlueprint(**kwargs)


def blueprint_key_map_from_dict(data: dict[str, Any], blueprint: ProductBlueprint) -> dict[str, str]:
    modules = data.get("modules") if isinstance(data, dict) else []
    if not isinstance(modules, list):
        return {}
    by_title = {module.title: module.key for module in blueprint.modules if module.title and module.key}
    by_order = [module.key for module in blueprint.modules if module.key]
    key_map: dict[str, str] = {}
    for index, item in enumerate(modules[: len(by_order)], start=0):
        if not isinstance(item, dict):
            continue
        old_key = str(item.get("key") or item.get("module_key") or item.get("moduleKey") or "").strip()
        title = str(item.get("title") or "").strip()
        new_key = by_title.get(title) or (by_order[index] if index < len(by_order) else "")
        if old_key and new_key and old_key != new_key:
            key_map[old_key] = new_key
    return key_map


def remap_manual_content_for_blueprint(data: Any, blueprint: ProductBlueprint) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    modules = data.get("modules")
    if not isinstance(modules, dict):
        return data
    expected = {module.key: module for module in blueprint.modules if module.key}
    if all(key in modules for key in expected):
        return data
    title_to_key = {module.title: module.key for module in blueprint.modules if module.title and module.key}
    remapped: dict[str, Any] = {}
    remaining = list(modules.items())
    for key, module_content in modules.items():
        if key in expected:
            remapped[key] = module_content
            continue
        if isinstance(module_content, dict):
            title = str(module_content.get("title") or "").strip()
            new_key = title_to_key.get(title)
            if new_key:
                remapped[new_key] = module_content
                continue
        remapped[key] = module_content
    for module in blueprint.modules:
        if module.key in remapped:
            continue
        match_index = next(
            (
                index
                for index, (_old_key, content) in enumerate(remaining)
                if isinstance(content, dict) and str(content.get("title") or "").strip() == module.title
            ),
            -1,
        )
        if match_index >= 0:
            _old_key, content = remaining.pop(match_index)
            remapped[module.key] = content
    payload = dict(data)
    payload["modules"] = remapped
    return payload


def remap_ui_blueprint_for_blueprint(data: Any, blueprint: ProductBlueprint) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    screens = data.get("screens")
    if not isinstance(screens, list):
        return data
    title_to_key = {module.title: module.key for module in blueprint.modules if module.title and module.key}
    expected_keys = {module.key for module in blueprint.modules if module.key}
    key_map: dict[str, str] = {}
    for item in screens:
        if not isinstance(item, dict):
            continue
        old_key = str(item.get("module_key") or item.get("key") or "").strip()
        title = str(item.get("title") or "").strip()
        new_key = title_to_key.get(title)
        if old_key and new_key and old_key != new_key:
            key_map[old_key] = new_key
    remapped_screens = []
    for item in screens:
        if not isinstance(item, dict):
            continue
        remapped = dict(item)
        module_key = str(remapped.get("module_key") or "").strip()
        if module_key in key_map:
            remapped["module_key"] = key_map[module_key]
        elif module_key in expected_keys:
            remapped["module_key"] = module_key
        elif str(remapped.get("title") or "").strip() in title_to_key:
            remapped["module_key"] = title_to_key[str(remapped.get("title") or "").strip()]
        key = str(remapped.get("key") or "").strip()
        remapped["key"] = _remap_screen_key(key, key_map, remapped.get("module_key"))
        remapped_screens.append(remapped)
    payload = dict(data)
    payload["screens"] = remapped_screens
    return payload


def _feature_module_from_cached_item(
    item: dict[str, Any],
    index: int,
    key_map: dict[str, str],
    used_keys: set[str],
) -> FeatureModule | None:
    title = str(item.get("title") or "").strip()
    if not title:
        return None
    raw_key = str(item.get("key") or "").strip()
    operations = _string_list(item.get("operations"))
    data_fields = _string_list(item.get("data_fields"))
    description = str(item.get("description") or "")
    key = semantic_module_key(
        title,
        index,
        raw_key=raw_key,
        used=used_keys,
        context_terms=[description, *operations[:4], *data_fields[:6], *_string_list(item.get("entities"))[:4]],
    )
    if raw_key and key != raw_key:
        key_map[raw_key] = key
    used_keys.add(key)
    return FeatureModule(
        key=key,
        title=title,
        description=description,
        entities=normalize_entity_names(_string_list(item.get("entities")), key, index, old_key=raw_key),
        operations=operations,
        data_fields=data_fields,
        pages=_string_list(item.get("pages")),
        rules=_string_list(item.get("rules")),
        operation_specs=_mapping_list(item.get("operation_specs") or item.get("operationSpecs")),
    )


def _remap_module_key_in_mapping(item: dict[str, Any], key_map: dict[str, str]) -> dict[str, Any]:
    result = dict(item)
    for field in ("module_key", "moduleKey", "key"):
        value = result.get(field)
        if isinstance(value, str) and value in key_map:
            result[field] = key_map[value]
    return result


def _remap_screen_key(key: str, key_map: dict[str, str], module_key: Any) -> str:
    if not key:
        return ""
    if key in {"login", "dashboard", "statistics", "workflow_review", "settings_audit", "module_list", "module_detail"}:
        return key
    for old_key, new_key in key_map.items():
        if key == old_key:
            return new_key
        if key.startswith(f"{old_key}_"):
            return f"{new_key}_{key[len(old_key) + 1:]}"
    if is_placeholder_module_key(key) and isinstance(module_key, str) and module_key:
        return module_key
    return key


def technical_architecture_from_dict(data: dict[str, Any]) -> TechnicalArchitecture:
    return create_technical_architecture(
        str(data.get("key") or ""),
        source=str(data.get("source") or "llm"),
        rationale=str(data.get("rationale") or ""),
        project_layout=_string_list(data.get("project_layout")),
        run_commands=_string_list(data.get("run_commands")),
        quality_checks=_string_list(data.get("quality_checks")),
    )


def ui_blueprint_from_dict(data: dict[str, Any]) -> UiBlueprint:
    screens = [
        UiScreenBlueprint(
            key=str(item.get("key") or ""),
            title=str(item.get("title") or ""),
            caption=str(item.get("caption") or ""),
            view_type=str(item.get("view_type") or ""),
            module_key=str(item.get("module_key") or ""),
            components=_string_list(item.get("components")),
            sample_data=item.get("sample_data") if isinstance(item.get("sample_data"), dict) else {},
        )
        for item in data.get("screens", [])
        if isinstance(item, dict) and str(item.get("key") or "").strip() and str(item.get("view_type") or "").strip()
    ]
    return UiBlueprint(
        renderer=str(data.get("renderer") or ""),
        visual_style=str(data.get("visual_style") or ""),
        screens=screens,
        source=str(data.get("source") or "llm"),
        warnings=_string_list(data.get("warnings")),
        design_brief=data.get("design_brief") if isinstance(data.get("design_brief"), dict) else {},
    )


def _cache_fingerprint(task: GenerationTask, feature_hint_meta: dict[str, Any]) -> str:
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "software_name": task.software_name,
        "version": task.version,
        "product_type": task.product_type,
        "software_category": task.software_category,
        "feature_hint": str(getattr(task, "input_feature_hint", task.feature_hint) or ""),
        "confirmed_outline": _stable_value(getattr(task, "confirmed_outline", {})),
        "model_provider": task.model_provider,
        "model_name": task.model_name,
        "randomness": task.randomness,
        "seed": task.seed,
        "generation_profile": os.getenv("SOFT_GENERATION_PROFILE", "balanced"),
        "blueprint_floor": os.getenv("SOFT_BLUEPRINT_QUALITY_FLOOR", ""),
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def _stable_value(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
            key_text = str(key)
            if key_text in {"id", "_plannedAt"} or "elapsed" in key_text.lower() or "time" in key_text.lower():
                continue
            result[key_text] = _stable_value(item)
        return result
    if isinstance(value, list):
        return [_stable_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _manual_content_ready(data: Any, blueprint: ProductBlueprint) -> bool:
    if not isinstance(data, dict) or data.get("_warnings"):
        return False
    if not all(isinstance(data.get(key), list) and data.get(key) for key in MANUAL_SECTION_KEYS):
        return False
    modules = data.get("modules")
    if not isinstance(modules, dict):
        return False
    expected_keys = [module.key for module in blueprint.modules if module.key]
    if not expected_keys:
        return False
    return all(isinstance(modules.get(key), dict) and modules.get(key, {}).get("paragraphs") for key in expected_keys)


def _ui_blueprint_ready(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    if data.get("source") != "llm":
        return False
    if str(data.get("renderer") or "") not in {"admin", "game", "mobile_app"}:
        return False
    screens = data.get("screens")
    if not isinstance(screens, list) or len(screens) < 4:
        return False
    design_brief = data.get("design_brief")
    if not isinstance(design_brief, dict):
        return False
    visual_identity = design_brief.get("visual_identity_spec")
    if not isinstance(visual_identity, dict) or not str(visual_identity.get("identity_signature") or "").strip():
        return False
    for item in screens:
        if not isinstance(item, dict):
            return False
        if not str(item.get("key") or "").strip() or not str(item.get("view_type") or "").strip():
            return False
    return True


def _read_stage(context: dict[str, Any], filename: str) -> dict[str, Any] | None:
    if not context.get("enabled"):
        return None
    path = Path(context["dir"]) / filename
    fallback_path = None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        fallback_path = _compatible_fallback_stage_file(context, filename)
        if not fallback_path:
            return None
        try:
            data = json.loads(fallback_path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return data if isinstance(data, dict) else None


def _write_stage(context: dict[str, Any], filename: str, data: dict[str, Any]) -> None:
    if not context.get("enabled"):
        return
    cache_dir = Path(context["dir"])
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest = dict(context.get("manifest") or {})
    manifest_path = cache_dir / "manifest.json"
    tmp_manifest = manifest_path.with_suffix(".json.tmp")
    tmp_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_manifest.replace(manifest_path)
    path = cache_dir / filename
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            result.append(text)
    return result


def _string_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items() if str(key).strip() and item is not None}


def _mapping_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _expected_module_titles(feature_hint_meta: dict[str, Any]) -> list[str]:
    modules = feature_hint_meta.get("feature_hint_blueprint_modules") if isinstance(feature_hint_meta, dict) else []
    if not isinstance(modules, list):
        return []
    return [
        str(item.get("title") or "").strip()
        for item in modules
        if isinstance(item, dict) and str(item.get("title") or "").strip()
    ][:10]


def _compatible_fallback_stage_file(context: dict[str, Any], filename: str) -> Path | None:
    if not context.get("resume_existing_output"):
        return None
    current_dir = Path(context["dir"])
    cache_root = current_dir.parent
    if not cache_root.exists():
        return None
    manifest = context.get("manifest") if isinstance(context.get("manifest"), dict) else {}
    for candidate_dir in sorted(cache_root.iterdir(), key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True):
        if not candidate_dir.is_dir() or candidate_dir == current_dir:
            continue
        candidate_file = candidate_dir / filename
        if not candidate_file.exists():
            continue
        if not _manifest_matches(candidate_dir / "manifest.json", manifest):
            continue
        return candidate_file
    return None


def _manifest_matches(path: Path, expected: dict[str, Any]) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    fields = ("software_name", "version", "product_type", "software_category", "model_provider", "model_name", "randomness")
    return all(str(data.get(field) or "") == str(expected.get(field) or "") for field in fields)


def _candidate_titles_match(path: Path, expected_titles: list[str]) -> bool:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    modules = data.get("modules") if isinstance(data, dict) else []
    if not isinstance(modules, list):
        return False
    candidate_titles = [
        str(item.get("title") or "").strip()
        for item in modules
        if isinstance(item, dict) and str(item.get("title") or "").strip()
    ]
    target = expected_titles[: min(6, len(expected_titles))]
    return bool(target) and candidate_titles[: len(target)] == target
