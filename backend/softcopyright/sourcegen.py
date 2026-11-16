from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .blueprint import ProductBlueprint, FeatureModule
from .domain_profile import build_domain_profile
from .models import GenerationTask


SOURCE_MATERIAL_ORDER_FILE = ".source-material-order.json"
SOURCE_MATERIAL_SUFFIXES = {
    ".java",
    ".xml",
    ".py",
    ".js",
    ".ts",
    ".php",
    ".cs",
    ".cpp",
    ".h",
    ".hpp",
    ".html",
    ".css",
    ".sql",
    ".yml",
    ".yaml",
    ".properties",
}


def repair_generated_business_record_labels(source_dir: Path) -> int:
    """Migrate old generated service defaults that could leak generic labels into UI data."""
    changed = 0
    pattern = re.compile(
        r"(name:\s*payload\.name\s*\|\|\s*[\"'])([^\"']*?)业务记录([\"'])"
    )
    seeded_pattern = re.compile(r"([\"'])([^\"'\r\n]*?)记录(\d{2,})([\"'])")
    for path in source_dir.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in {".js", ".ts", ".py"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        updated, count = pattern.subn(r"\1\2对象\3", text)
        updated, seeded_count = seeded_pattern.subn(r"\1\2对象\3\4", updated)
        count += seeded_count
        if count:
            path.write_text(updated, encoding="utf-8")
            changed += count
    return changed


def repair_generated_domain_sample_leaks(source_dir: Path, blueprint: ProductBlueprint) -> int:
    """Replace transport-only seed values in cached non-transport JS services."""
    if build_domain_profile(blueprint=blueprint).requires_route_topology:
        return 0
    modules_by_token = {_snake(module.key): module for module in (getattr(blueprint, "modules", []) or [])}
    changed = 0
    for path in source_dir.rglob("*Service.js"):
        if not path.is_file():
            continue
        token = path.stem[:-7] if path.stem.endswith("Service") else ""
        module = modules_by_token.get(token)
        if module is None or _is_transport_module(module):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        updated = text
        regions = _business_record_regions(module, [str(item) for item in (module.data_fields or [])])
        for index in range(1, 5):
            replacements = {
                _transport_node_sequence(index): _business_process_sequence(module, index),
                ["北向", "南向", "双向", "东向"][index - 1]: _business_direction(index),
                _transport_service_scope(index): regions[(index - 1) % len(regions)],
            }
            for old, new in replacements.items():
                occurrence_count = updated.count(old)
                if occurrence_count:
                    updated = updated.replace(old, new)
                    changed += occurrence_count
        if updated != text:
            path.write_text(updated, encoding="utf-8")
    return changed


def generate_source_project(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    output_dir: Path,
    visual_reference_report: dict | None = None,
) -> dict:
    source_dir = output_dir / "generated_source"
    source_dir.mkdir(parents=True, exist_ok=True)

    architecture = getattr(blueprint, "technical_architecture", {}) or {}
    source_strategy = str(architecture.get("source_strategy") or "").strip()
    files: list[Path] = []
    if source_strategy == "java_with_web_console":
        files.extend(_generate_java_project(task, blueprint, source_dir))
        files.extend(_generate_javascript_project(task, blueprint, source_dir / "web-console", include_readme=False))
    elif source_strategy == "csharp_web_api":
        files.extend(_generate_csharp_project(task, blueprint, source_dir))
        files.extend(_generate_javascript_project(task, blueprint, source_dir / "web-console", include_readme=False))
    elif source_strategy == "javascript_with_java_api":
        files.extend(_generate_javascript_project(task, blueprint, source_dir))
        files.extend(_generate_java_project(task, blueprint, source_dir / "api-service", include_readme=False))
    elif source_strategy == "python_with_web_console":
        files.extend(_generate_python_project(task, blueprint, source_dir))
        files.extend(_generate_javascript_project(task, blueprint, source_dir / "web-console", include_readme=False))
    elif source_strategy == "java_with_node_gateway":
        files.extend(_generate_java_project(task, blueprint, source_dir))
        files.extend(_generate_javascript_project(task, blueprint, source_dir / "gateway-service", include_readme=False))
    elif source_strategy == "embedded_mixed":
        files.extend(_generate_embedded_mixed_project(task, blueprint, source_dir))
        files.extend(_generate_javascript_project(task, blueprint, source_dir / "web-console", include_readme=False))
    elif source_strategy == "system_service_mixed":
        files.extend(_generate_system_service_project(task, blueprint, source_dir))
        files.extend(_generate_javascript_project(task, blueprint, source_dir / "web-console", include_readme=False))
    elif task.language == "Java":
        files.extend(_generate_java_project(task, blueprint, source_dir))
        files.extend(_generate_javascript_project(task, blueprint, source_dir / "web-console", include_readme=False))
    elif task.language == "C#":
        files.extend(_generate_csharp_project(task, blueprint, source_dir))
        files.extend(_generate_javascript_project(task, blueprint, source_dir / "web-console", include_readme=False))
    elif task.language == "Python":
        files.extend(_generate_python_project(task, blueprint, source_dir))
    elif task.language == "JavaScript":
        files.extend(_generate_javascript_project(task, blueprint, source_dir))
    else:
        files.extend(_generate_generic_project(task, blueprint, source_dir))

    material_order_path = _write_source_material_order_manifest(source_dir)
    blueprint_path = _write(source_dir / "product-blueprint.json", json.dumps(blueprint.to_dict(), ensure_ascii=False, indent=2))
    files.append(blueprint_path)
    visual_contract_path = _write_visual_reference_contract(source_dir, visual_reference_report)
    if visual_contract_path:
        files.append(visual_contract_path)
    total_lines = sum(_count_lines(path) for path in files)
    relative_files = [path.relative_to(source_dir).as_posix() for path in files if path.exists()]
    persistence_required = source_strategy == "python_with_web_console" or task.language == "Python"
    repository_files = [path for path in relative_files if "/repositories/" in f"/{path}"]
    migration_files = [path for path in relative_files if path.startswith("migrations/")]
    test_files = [path for path in relative_files if path.startswith("tests/") and path.endswith(".py")]
    persistence_ready = (
        not persistence_required
        or (
            "app/core/database.py" in relative_files
            and bool(repository_files)
            and bool(migration_files)
            and bool(test_files)
        )
    )
    return {
        "source_dir": str(source_dir),
        "files": [str(path) for path in files],
        "blueprint_path": str(blueprint_path),
        "module_keys": [module.key for module in blueprint.modules],
        "module_titles": [module.title for module in blueprint.modules],
        "technical_architecture": architecture,
        "source_language": architecture.get("source_language") or task.language,
        "source_strategy": source_strategy or "language-single",
        "material_order_manifest": str(material_order_path),
        "material_order_strategy": "front-core-middle-support-tail-core",
        "visual_reference_contract": str(visual_contract_path) if visual_contract_path else "",
        "total_lines": total_lines,
        "source_persistence_required": persistence_required,
        "source_persistence_engine": "sqlite" if persistence_required else "",
        "source_persistence_ready": persistence_ready,
        "source_repository_file_count": len(repository_files),
        "source_migration_file_count": len(migration_files),
        "source_test_file_count": len(test_files),
    }


def refresh_generated_source_metadata(task: GenerationTask, blueprint: ProductBlueprint, source_info: dict) -> None:
    source_dir = Path(str(source_info.get("source_dir") or ""))
    if not source_dir.is_dir():
        return
    blueprint_path = _write(
        source_dir / "product-blueprint.json",
        json.dumps(blueprint.to_dict(), ensure_ascii=False, indent=2),
    )
    _write(source_dir / "README.md", _readme(task, blueprint))
    architecture = getattr(blueprint, "technical_architecture", {}) or {}
    source_info["blueprint_path"] = str(blueprint_path)
    source_info["technical_architecture"] = architecture
    source_info["source_language"] = architecture.get("source_language") or task.language
    source_info["source_strategy"] = architecture.get("source_strategy") or source_info.get("source_strategy") or "language-single"


def read_source_line_entries(source_dir: Path) -> list[dict]:
    entries: list[dict] = []
    for order_index, path in enumerate(_ordered_source_material_paths(source_dir, SOURCE_MATERIAL_SUFFIXES), start=1):
        relative = path.relative_to(source_dir).as_posix()
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="gbk", errors="ignore")
        for line_number, line in enumerate(content.splitlines(), start=1):
            sanitized = _sanitize_source_material_line(line.rstrip())
            if sanitized.strip() and not _is_comment_only_source_line(sanitized, path.suffix.lower()):
                entries.append(
                    {
                        "file": relative,
                        "line": line_number,
                        "text": sanitized,
                        "order_index": order_index,
                    }
                )
    return entries


def read_source_lines(source_dir: Path) -> list[str]:
    lines: list[str] = []
    for entry in read_source_line_entries(source_dir):
        text = str(entry.get("text", ""))
        if text.strip():
            lines.append(text)
    return lines


def source_project_stats(source_dir: Path) -> dict:
    lines = read_source_lines(source_dir)
    files = [
        str(path)
        for path in sorted(source_dir.rglob("*"))
        if path.is_file()
        and not _is_duplicate_served_prototype(path.relative_to(source_dir).as_posix())
        and not _is_internal_material_file(path.relative_to(source_dir).as_posix())
    ]
    return {
        "files": files,
        "total_lines": len(lines),
    }


def _write_visual_reference_contract(source_dir: Path, visual_reference_report: dict | None) -> Path | None:
    if not isinstance(visual_reference_report, dict) or not visual_reference_report.get("ready"):
        return None
    style_reference = visual_reference_report.get("style_reference")
    if not isinstance(style_reference, dict):
        style_reference = {}
    payload = {
        "version": "2026-07-08",
        "generation_order": "visual_reference_before_source_project",
        "mode": visual_reference_report.get("mode", ""),
        "source": visual_reference_report.get("source", ""),
        "image_model": visual_reference_report.get("image_model", ""),
        "image_size": visual_reference_report.get("image_size", ""),
        "style_reference": {
            "image_path": style_reference.get("image_path", ""),
            "image_sha256": style_reference.get("image_sha256", ""),
            "image_width": style_reference.get("image_width", 0),
            "image_height": style_reference.get("image_height", 0),
            "prompt_summary": style_reference.get("prompt_summary", ""),
        },
        "usage": "The source project and runnable UI prototype are generated after this visual reference is ready.",
    }
    return _write(source_dir / "ui-visual-reference-contract.json", json.dumps(payload, ensure_ascii=False, indent=2))


def _write_source_material_order_manifest(source_dir: Path) -> Path:
    ordered_paths = _heuristic_source_material_paths(source_dir, SOURCE_MATERIAL_SUFFIXES)
    files = []
    for index, path in enumerate(ordered_paths, start=1):
        relative = path.relative_to(source_dir).as_posix()
        files.append(
            {
                "order": index,
                "path": relative,
                "tier": _source_material_tier(relative),
                "lines": _count_lines(path),
            }
        )
    manifest = {
        "version": "2026-06-30",
        "strategy": "front-core-middle-support-tail-core",
        "description": "Internal source material reading order. Core business files are split between the front and tail so first/last 30-page extraction remains useful.",
        "files": files,
    }
    path = source_dir / SOURCE_MATERIAL_ORDER_FILE
    return _write(path, json.dumps(manifest, ensure_ascii=False, indent=2))


def _ordered_source_material_paths(source_dir: Path, allowed: set[str]) -> list[Path]:
    candidates = _source_material_candidate_paths(source_dir, allowed)
    candidate_by_relative = {path.relative_to(source_dir).as_posix(): path for path in candidates}
    manifest_order = _read_source_material_order_manifest(source_dir, candidate_by_relative)
    if not manifest_order:
        return _heuristic_source_material_paths(source_dir, allowed)
    # The manifest is written immediately after the runnable business project
    # is generated. Later screenshot/React assets must not silently enter the
    # last 30 source-material pages merely because they share a source suffix.
    return manifest_order


def _read_source_material_order_manifest(source_dir: Path, candidate_by_relative: dict[str, Path]) -> list[Path]:
    path = source_dir / SOURCE_MATERIAL_ORDER_FILE
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, list):
        return []
    result: list[Path] = []
    seen: set[str] = set()
    for item in files:
        relative = str(item.get("path") if isinstance(item, dict) else item).replace("\\", "/").strip()
        if not relative or relative in seen:
            continue
        path = candidate_by_relative.get(relative)
        if path and path.exists():
            result.append(path)
            seen.add(relative)
    return result


def _heuristic_source_material_paths(source_dir: Path, allowed: set[str]) -> list[Path]:
    return _arrange_source_material_paths(_source_material_candidate_paths(source_dir, allowed), source_dir)


def _source_material_candidate_paths(source_dir: Path, allowed: set[str]) -> list[Path]:
    candidates: list[Path] = []
    if not source_dir.exists():
        return candidates
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in allowed:
            continue
        relative = path.relative_to(source_dir).as_posix()
        if _is_duplicate_served_prototype(relative) or _is_internal_material_file(relative):
            continue
        if _is_prototype_landing_entry(path, relative):
            continue
        if "node_modules/" in relative or "/vendor/" in relative:
            continue
        candidates.append(path)
    return candidates


def _arrange_source_material_paths(paths: list[Path], source_dir: Path) -> list[Path]:
    core = [path for path in paths if _source_material_tier(path.relative_to(source_dir).as_posix()) == "core"]
    support = [path for path in paths if _source_material_tier(path.relative_to(source_dir).as_posix()) != "core"]
    core.sort(key=lambda path: _source_material_sort_key(path.relative_to(source_dir).as_posix()))
    support.sort(key=lambda path: _source_material_sort_key(path.relative_to(source_dir).as_posix()))
    front_core, tail_core = _split_core_material_paths(core, tail_effective_line_target=1700)
    return front_core + support + tail_core


def _split_core_material_paths(core: list[Path], tail_effective_line_target: int) -> tuple[list[Path], list[Path]]:
    if not core:
        return [], []
    effective_counts = {path: _source_material_effective_line_count(path) for path in core}
    total_effective = sum(effective_counts.values())
    if total_effective <= tail_effective_line_target * 2:
        front_core: list[Path] = []
        tail_core: list[Path] = []
        for index, path in enumerate(core):
            if index % 2 == 0:
                front_core.append(path)
            else:
                tail_core.append(path)
        return front_core, tail_core

    tail_core_reversed: list[Path] = []
    tail_lines = 0
    for path in reversed(core):
        tail_core_reversed.append(path)
        tail_lines += effective_counts.get(path, 0)
        if tail_lines >= tail_effective_line_target:
            break
    tail_core = list(reversed(tail_core_reversed))
    tail_set = set(tail_core)
    front_core = [path for path in core if path not in tail_set]
    return front_core, tail_core


def _source_material_effective_line_count(path: Path) -> int:
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = path.read_text(encoding="gbk", errors="ignore")
    except Exception:
        return 0
    count = 0
    suffix = path.suffix.lower()
    for line in content.splitlines():
        sanitized = _sanitize_source_material_line(line.rstrip())
        if sanitized.strip() and not _is_comment_only_source_line(sanitized, suffix):
            count += 1
    return count


def _source_material_tier(relative: str) -> str:
    normalized = relative.replace("\\", "/").lower()
    core_parts = (
        "/service/",
        "/services/",
        "/controller/",
        "/controllers/",
        "/repository/",
        "/repositories/",
        "/mapper/",
        "/routers/",
        "/routes/",
        "/api/",
        "/workflow/",
        "/business/",
        "/admin_cli/",
        "/edge/services/",
        "/firmware/src/",
        "/system/src/",
    )
    core_names = (
        "service",
        "controller",
        "repository",
        "router",
        "route",
        "mapper",
        "workflow",
        "operationtrace",
        "businessworkflow",
        "manager",
        "worker",
        "command",
        "daemon",
        "driver",
    )
    if any(part in normalized for part in core_parts):
        return "core"
    stem = Path(normalized).stem
    if any(name in stem for name in core_names):
        return "core"
    return "support"


def _source_material_sort_key(relative: str) -> tuple[int, str]:
    normalized = relative.replace("\\", "/").lower()
    priority = 50
    weighted_parts = [
        ("/service/", 1),
        ("/services/", 1),
        ("businessworkflow", 2),
        ("operationtrace", 3),
        ("/controller/", 4),
        ("/controllers/", 4),
        ("/routers/", 5),
        ("/routes/", 5),
        ("/repository/", 6),
        ("/repositories/", 6),
        ("/mapper/", 7),
        ("/firmware/src/", 8),
        ("/system/src/", 8),
        ("/edge/services/", 9),
        ("/admin_cli/", 9),
        ("/models/", 20),
        ("/domain/", 20),
        ("/dto/", 22),
        ("/queries/", 22),
        ("/schemas/", 22),
        ("/common/", 24),
        ("/config/", 25),
        ("/configuration/", 25),
        ("/resources/", 28),
        ("/src/", 30),
    ]
    for marker, value in weighted_parts:
        if marker in normalized:
            priority = min(priority, value)
    if normalized.endswith(("pom.xml", ".csproj", "package.json", "requirements.txt", "cmakelists.txt")):
        priority = 35
    return (priority, normalized)


def _is_duplicate_served_prototype(relative: str) -> bool:
    normalized = relative.replace("\\", "/").lower()
    return any(
        marker in normalized
        for marker in (
            "ui-prototype/",
            "src/main/resources/static/ui-prototype/",
            "wwwroot/ui-prototype/",
        )
    )


def _is_internal_material_file(relative: str) -> bool:
    normalized = relative.replace("\\", "/")
    name = Path(normalized).name.lower()
    return (
        name in {
            "readme.md",
            "ui_prototype_entry.md",
            "product-blueprint.json",
            "prototype-manifest.json",
            SOURCE_MATERIAL_ORDER_FILE,
        }
        or normalized.startswith("ui-prototype/")
    )


def _is_prototype_landing_entry(path: Path, relative: str) -> bool:
    normalized = relative.replace("\\", "/").lower()
    if not normalized.endswith("index.html"):
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    compact = re.sub(r"\s+", " ", text).lower()
    return (
        "/ui-prototype/index.html" in compact
        and (
            "http-equiv=\"refresh\"" in compact
            or "http-equiv='refresh'" in compact
            or "打开运行界面" in text
        )
    )


def _sanitize_source_material_line(line: str) -> str:
    replacements = {
        "自动生成": "自动形成",
        "AI生成": "智能形成",
        "AI 生成": "智能形成",
        "人工智能生成": "智能形成",
        "auto-generated": "prepared",
        "Auto-generated": "Prepared",
        "automatically generated": "prepared",
        "Automatically generated": "Prepared",
    }
    result = line
    for source, target in replacements.items():
        result = result.replace(source, target)
    return result


def _is_comment_only_source_line(line: str, suffix: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if suffix in {".js", ".ts", ".java", ".cs", ".cpp", ".h", ".hpp", ".php"}:
        return stripped.startswith(("//", "/*", "*/", "* "))
    if suffix == ".py":
        return stripped.startswith("#")
    if suffix in {".html", ".xml"}:
        return stripped.startswith(("<!--", "-->"))
    if suffix == ".css":
        return stripped.startswith(("/*", "*/", "* "))
    return False


def _generate_java_project(task: GenerationTask, blueprint: ProductBlueprint, source_dir: Path, include_readme: bool = True) -> list[Path]:
    base = source_dir / "src" / "main"
    java_root = base / "java" / "com" / "copyright" / _package_token(task.software_name)
    resources = base / "resources"
    mapper_dir = resources / "mapper"
    files: list[Path] = []

    for folder in [
        java_root / "controller",
        java_root / "service",
        java_root / "repository",
        java_root / "domain",
        java_root / "dto",
        java_root / "config",
        java_root / "common",
        resources / "static",
        mapper_dir,
    ]:
        folder.mkdir(parents=True, exist_ok=True)

    app_class = f"{_class_prefix(task.software_name)}Application"
    files.append(
        _write(
            java_root / f"{app_class}.java",
            f"""package com.copyright.{_package_token(task.software_name)};

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.view.RedirectView;

@SpringBootApplication
public class {app_class} {{
    public static void main(String[] args) {{
        SpringApplication.run({app_class}.class, args);
    }}

    @RestController
    public static class RuntimeController {{
        @GetMapping("/health")
        public java.util.Map<String, String> health() {{
            return java.util.Map.of(
                    "status", "ok",
                    "software", "{_java_literal(task.software_name)}",
                    "version", "{_java_literal(task.version)}");
        }}

        @GetMapping("/")
        public RedirectView index() {{
            return new RedirectView("/ui-prototype/index.html");
        }}
    }}

{_java_runtime_module_controllers(blueprint)}
}}
""",
        )
    )

    files.append(
        _write(
            resources / "application.yml",
            f"""server:
  port: ${{PORT:8080}}
spring:
  application:
    name: {_ascii_token(task.software_name)}-service
  datasource:
    url: jdbc:h2:mem:{_ascii_token(task.software_name)};MODE=MySQL;DB_CLOSE_DELAY=-1
    username: sa
    password:
    driver-class-name: org.h2.Driver
  sql:
    init:
      mode: never
software:
  name: "{task.software_name}"
  version: "{task.version}"
  productType: "{task.product_type}"
""",
        )
    )

    files.append(
        _write(
            source_dir / "pom.xml",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.copyright</groupId>
    <artifactId>{_ascii_token(task.software_name)}</artifactId>
    <version>1.0.0</version>
    <name>{task.software_name}</name>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
""",
        )
    )

    files.extend(_java_common_files(java_root, task, blueprint))

    for module in blueprint.modules:
        files.extend(_java_module_files(java_root, mapper_dir, module, task, blueprint))
        files.extend(_java_support_files(java_root, module, task))

    if include_readme:
        files.append(_write(source_dir / "README.md", _readme(task, blueprint)))
    files.append(_write(resources / "schema.sql", _java_schema_sql(blueprint)))
    files = _ensure_line_target(files, java_root, task, blueprint, target_lines=3400)
    files = _align_source_material_pages(files, source_dir, java_root / "service", ".java")
    return files


def _java_common_files(java_root: Path, task: GenerationTask, blueprint: ProductBlueprint) -> list[Path]:
    package = f"com.copyright.{_package_token(task.software_name)}"
    return [
        _write(
            java_root / "common" / "ApiResponse.java",
            f"""package {package}.common;

public class ApiResponse<T> {{
    private boolean success;
    private String message;
    private T data;

    public ApiResponse() {{
    }}

    public ApiResponse(boolean success, String message, T data) {{
        this.success = success;
        this.message = message;
        this.data = data;
    }}

    public static <T> ApiResponse<T> ok(T data) {{
        return new ApiResponse<>(true, "操作成功", data);
    }}

    public static <T> ApiResponse<T> fail(String message) {{
        return new ApiResponse<>(false, message, null);
    }}

    public boolean isSuccess() {{
        return success;
    }}

    public void setSuccess(boolean success) {{
        this.success = success;
    }}

    public String getMessage() {{
        return message;
    }}

    public void setMessage(String message) {{
        this.message = message;
    }}

    public T getData() {{
        return data;
    }}

    public void setData(T data) {{
        this.data = data;
    }}
}}
""",
        ),
        _write(
            java_root / "config" / "SoftwareProfile.java",
            f"""package {package}.config;

public class SoftwareProfile {{
    private final String softwareName = "{task.software_name}";
    private final String version = "{task.version}";
    private final String productType = "{task.product_type}";
    private final String industry = "{blueprint.industry}";
    private final String usageContext = "{_java_literal(blueprint.scenario)}";
    private final String positioning = "{_java_literal(blueprint.positioning)}";
    private final String fingerprint = "{blueprint.generation_fingerprint}";

    public String getSoftwareName() {{
        return softwareName;
    }}

    public String getVersion() {{
        return version;
    }}

    public String getProductType() {{
        return productType;
    }}

    public String getIndustry() {{
        return industry;
    }}

    public String getUsageContext() {{
        return usageContext;
    }}

    public String getPositioning() {{
        return positioning;
    }}

    public String getFingerprint() {{
        return fingerprint;
    }}
}}
""",
        ),
    ]


def _java_runtime_module_controllers(blueprint: ProductBlueprint) -> str:
    blocks: list[str] = []
    for module in blueprint.modules[:16]:
        route = _snake(module.key).replace("_", "-")
        title = _json_literal(module.title)
        description = _json_literal(module.description)
        field_values = ", ".join(_json_literal(item) for item in (module.data_fields[:4] or ["业务编号", "业务名称", "状态"]))
        operation_values = ", ".join(_json_literal(item) for item in (module.operations[:4] or ["查询", "新增", "编辑", "导出"]))
        class_name = f"{_pascal(module.key)}RuntimeController"
        blocks.append(
            f"""
    @RestController
    public static class {class_name} {{
        @GetMapping("/api/{route}")
        public java.util.Map<String, Object> list() {{
            return java.util.Map.of(
                    "module", {title},
                    "description", {description},
                    "fields", java.util.List.of({field_values}),
                    "operations", java.util.List.of({operation_values}),
                    "records", java.util.List.of(
                            java.util.Map.of("code", "{_snake(module.key).upper()}-1001", "status", "ENABLED"),
                            java.util.Map.of("code", "{_snake(module.key).upper()}-1002", "status", "PENDING")));
        }}
    }}
"""
        )
    return "\n".join(blocks)


def _java_module_files(
    java_root: Path,
    mapper_dir: Path,
    module: FeatureModule,
    task: GenerationTask,
    blueprint: ProductBlueprint,
) -> list[Path]:
    package = f"com.copyright.{_package_token(task.software_name)}"
    class_name = _pascal(module.key)
    entity_name = f"{class_name}Record"
    dto_name = f"{class_name}Query"
    files = [
        _write(
            java_root / "domain" / f"{entity_name}.java",
            f"""package {package}.domain;

import java.time.LocalDateTime;

public class {entity_name} {{
    private Long id;
    private String code;
    private String name;
    private String status;
    private String ownerRole;
    private String description;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    public Long getId() {{
        return id;
    }}

    public void setId(Long id) {{
        this.id = id;
    }}

    public String getCode() {{
        return code;
    }}

    public void setCode(String code) {{
        this.code = code;
    }}

    public String getName() {{
        return name;
    }}

    public void setName(String name) {{
        this.name = name;
    }}

    public String getStatus() {{
        return status;
    }}

    public void setStatus(String status) {{
        this.status = status;
    }}

    public String getOwnerRole() {{
        return ownerRole;
    }}

    public void setOwnerRole(String ownerRole) {{
        this.ownerRole = ownerRole;
    }}

    public String getDescription() {{
        return description;
    }}

    public void setDescription(String description) {{
        this.description = description;
    }}

    public LocalDateTime getCreatedAt() {{
        return createdAt;
    }}

    public void setCreatedAt(LocalDateTime createdAt) {{
        this.createdAt = createdAt;
    }}

    public LocalDateTime getUpdatedAt() {{
        return updatedAt;
    }}

    public void setUpdatedAt(LocalDateTime updatedAt) {{
        this.updatedAt = updatedAt;
    }}
}}
""",
        ),
        _write(
            java_root / "dto" / f"{dto_name}.java",
            f"""package {package}.dto;

public class {dto_name} {{
    private String keyword;
    private String status;
    private Integer pageNo = 1;
    private Integer pageSize = 20;

    public String getKeyword() {{
        return keyword;
    }}

    public void setKeyword(String keyword) {{
        this.keyword = keyword;
    }}

    public String getStatus() {{
        return status;
    }}

    public void setStatus(String status) {{
        this.status = status;
    }}

    public Integer getPageNo() {{
        return pageNo;
    }}

    public void setPageNo(Integer pageNo) {{
        this.pageNo = pageNo;
    }}

    public Integer getPageSize() {{
        return pageSize;
    }}

    public void setPageSize(Integer pageSize) {{
        this.pageSize = pageSize;
    }}
}}
""",
        ),
        _write(
            java_root / "repository" / f"{class_name}Repository.java",
            f"""package {package}.repository;

import {package}.domain.{entity_name};
import {package}.dto.{dto_name};
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

public class {class_name}Repository {{
    private final List<{entity_name}> records = new ArrayList<>();

    public List<{entity_name}> findByCondition({dto_name} query) {{
        List<{entity_name}> result = new ArrayList<>();
        for ({entity_name} record : records) {{
            boolean keywordMatched = query.getKeyword() == null
                    || record.getName().contains(query.getKeyword())
                    || record.getCode().contains(query.getKeyword());
            boolean statusMatched = query.getStatus() == null
                    || query.getStatus().equals(record.getStatus());
            if (keywordMatched && statusMatched) {{
                result.add(record);
            }}
        }}
        return result;
    }}

    public Optional<{entity_name}> findById(Long id) {{
        return records.stream().filter(item -> item.getId().equals(id)).findFirst();
    }}

    public {entity_name} save({entity_name} record) {{
        records.removeIf(item -> item.getId().equals(record.getId()));
        records.add(record);
        return record;
    }}

    public boolean deleteById(Long id) {{
        return records.removeIf(item -> item.getId().equals(id));
    }}
}}
""",
        ),
        _write(
            java_root / "service" / f"{class_name}Service.java",
            f"""package {package}.service;

import {package}.domain.{entity_name};
import {package}.dto.{dto_name};
import {package}.repository.{class_name}Repository;
import java.time.LocalDateTime;
import java.util.List;

public class {class_name}Service {{
    private final {class_name}Repository repository = new {class_name}Repository();

    public List<{entity_name}> query({dto_name} query) {{
        normalizeQuery(query);
        return repository.findByCondition(query);
    }}

    public {entity_name} create({entity_name} record) {{
        record.setStatus(record.getStatus() == null ? "ENABLED" : record.getStatus());
        record.setCreatedAt(LocalDateTime.now());
        record.setUpdatedAt(LocalDateTime.now());
        return repository.save(record);
    }}

    public {entity_name} update(Long id, {entity_name} request) {{
        {entity_name} record = repository.findById(id).orElseThrow(() -> new IllegalArgumentException("记录不存在"));
        record.setName(request.getName());
        record.setStatus(request.getStatus());
        record.setOwnerRole(request.getOwnerRole());
        record.setDescription(request.getDescription());
        record.setUpdatedAt(LocalDateTime.now());
        return repository.save(record);
    }}

    public boolean remove(Long id) {{
        return repository.deleteById(id);
    }}

    public String buildBusinessSummary({entity_name} record) {{
        return "{module.title}：" + record.getName() + "，状态：" + record.getStatus();
    }}

    private void normalizeQuery({dto_name} query) {{
        if (query.getPageNo() == null || query.getPageNo() < 1) {{
            query.setPageNo(1);
        }}
        if (query.getPageSize() == null || query.getPageSize() < 1) {{
            query.setPageSize(20);
        }}
    }}
}}
""",
        ),
        _write(
            java_root / "controller" / f"{class_name}Controller.java",
            f"""package {package}.controller;

import {package}.common.ApiResponse;
import {package}.domain.{entity_name};
import {package}.dto.{dto_name};
import {package}.service.{class_name}Service;
import java.util.List;

public class {class_name}Controller {{
    private final {class_name}Service service = new {class_name}Service();

    public ApiResponse<List<{entity_name}>> list({dto_name} query) {{
        return ApiResponse.ok(service.query(query));
    }}

    public ApiResponse<{entity_name}> create({entity_name} record) {{
        return ApiResponse.ok(service.create(record));
    }}

    public ApiResponse<{entity_name}> update(Long id, {entity_name} record) {{
        return ApiResponse.ok(service.update(id, record));
    }}

    public ApiResponse<Boolean> delete(Long id) {{
        return ApiResponse.ok(service.remove(id));
    }}

    public ApiResponse<String> summary({entity_name} record) {{
        return ApiResponse.ok(service.buildBusinessSummary(record));
    }}
}}
""",
        ),
        _write(
            mapper_dir / f"{class_name}Mapper.xml",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN"
        "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="{package}.repository.{class_name}Repository">
    <resultMap id="{class_name}ResultMap" type="{package}.domain.{entity_name}">
        <id property="id" column="id"/>
        <result property="code" column="code"/>
        <result property="name" column="name"/>
        <result property="status" column="status"/>
        <result property="ownerRole" column="owner_role"/>
        <result property="description" column="description"/>
        <result property="createdAt" column="created_at"/>
        <result property="updatedAt" column="updated_at"/>
    </resultMap>

    <select id="findByCondition" resultMap="{class_name}ResultMap">
        select id, code, name, status, owner_role, description, created_at, updated_at
        from {module.key}_record
        where 1 = 1
        <if test="keyword != null and keyword != ''">
            and (name like concat('%', #{{keyword}}, '%') or code like concat('%', #{{keyword}}, '%'))
        </if>
        <if test="status != null and status != ''">
            and status = #{{status}}
        </if>
        order by updated_at desc
    </select>
</mapper>
""",
        ),
    ]
    return files


def _java_support_files(java_root: Path, module: FeatureModule, task: GenerationTask) -> list[Path]:
    package = f"com.copyright.{_package_token(task.software_name)}"
    class_name = _pascal(module.key)
    entity_name = f"{class_name}Record"
    return [
        _write(
            java_root / "service" / f"{class_name}Validator.java",
            f"""package {package}.service;

import {package}.domain.{entity_name};
import java.util.ArrayList;
import java.util.List;

public class {class_name}Validator {{
    public List<String> validateForCreate({entity_name} record) {{
        List<String> errors = new ArrayList<>();
        if (record == null) {{
            errors.add("请求数据不能为空");
            return errors;
        }}
        if (isBlank(record.getCode())) {{
            errors.add("业务编码不能为空");
        }}
        if (isBlank(record.getName())) {{
            errors.add("业务名称不能为空");
        }}
        if (isBlank(record.getOwnerRole())) {{
            errors.add("负责角色不能为空");
        }}
        if (record.getDescription() != null && record.getDescription().length() > 500) {{
            errors.add("描述信息不能超过500个字符");
        }}
        return errors;
    }}

    public List<String> validateForUpdate(Long id, {entity_name} record) {{
        List<String> errors = validateForCreate(record);
        if (id == null || id <= 0) {{
            errors.add("记录编号不合法");
        }}
        if (record != null && !isSupportedStatus(record.getStatus())) {{
            errors.add("状态值不在允许范围内");
        }}
        return errors;
    }}

    public boolean isSupportedStatus(String status) {{
        if (status == null) {{
            return true;
        }}
        return "ENABLED".equals(status)
                || "DISABLED".equals(status)
                || "PENDING".equals(status)
                || "ARCHIVED".equals(status);
    }}

    public String normalizeCode(String code) {{
        if (code == null) {{
            return "";
        }}
        return code.trim().replace(" ", "-").toUpperCase();
    }}

    private boolean isBlank(String value) {{
        return value == null || value.trim().isEmpty();
    }}
}}
""",
        ),
        _write(
            java_root / "service" / f"{class_name}StatisticsService.java",
            f"""package {package}.service;

import {package}.domain.{entity_name};
import java.time.LocalDate;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class {class_name}StatisticsService {{
    public Map<String, Integer> countByStatus(List<{entity_name}> records) {{
        Map<String, Integer> result = new HashMap<>();
        for ({entity_name} record : records) {{
            String status = record.getStatus() == null ? "UNKNOWN" : record.getStatus();
            result.put(status, result.getOrDefault(status, 0) + 1);
        }}
        return result;
    }}

    public Map<String, Object> buildDailySummary(List<{entity_name}> records, LocalDate date) {{
        Map<String, Object> summary = new HashMap<>();
        summary.put("module", "{module.title}");
        summary.put("date", date.toString());
        summary.put("totalCount", records.size());
        summary.put("enabledCount", countByStatus(records).getOrDefault("ENABLED", 0));
        summary.put("pendingCount", countByStatus(records).getOrDefault("PENDING", 0));
        summary.put("archivedCount", countByStatus(records).getOrDefault("ARCHIVED", 0));
        summary.put("riskLevel", evaluateRiskLevel(records));
        return summary;
    }}

    public String evaluateRiskLevel(List<{entity_name}> records) {{
        int pending = countByStatus(records).getOrDefault("PENDING", 0);
        if (pending > 50) {{
            return "HIGH";
        }}
        if (pending > 10) {{
            return "MEDIUM";
        }}
        return "LOW";
    }}
}}
""",
        ),
        _write(
            java_root / "service" / f"{class_name}ExportService.java",
            f"""package {package}.service;

import {package}.domain.{entity_name};
import java.util.ArrayList;
import java.util.List;

public class {class_name}ExportService {{
    public List<String> exportAsCsv(List<{entity_name}> records) {{
        List<String> lines = new ArrayList<>();
        lines.add("id,code,name,status,ownerRole,description");
        for ({entity_name} record : records) {{
            lines.add(joinCsv(record));
        }}
        return lines;
    }}

    public List<String> exportAsPlainText(List<{entity_name}> records) {{
        List<String> lines = new ArrayList<>();
        lines.add("{module.title}导出结果");
        for ({entity_name} record : records) {{
            lines.add(record.getCode() + " - " + record.getName() + " - " + record.getStatus());
        }}
        return lines;
    }}

    public String buildExportFileName(String operator) {{
        String safeOperator = operator == null ? "system" : operator.replaceAll("[^a-zA-Z0-9_-]", "_");
        return "{module.key}_export_" + safeOperator + ".csv";
    }}

    private String joinCsv({entity_name} record) {{
        return record.getId() + ","
                + escape(record.getCode()) + ","
                + escape(record.getName()) + ","
                + escape(record.getStatus()) + ","
                + escape(record.getOwnerRole()) + ","
                + escape(record.getDescription());
    }}

    private String escape(String value) {{
        if (value == null) {{
            return "";
        }}
        return value.replace(",", "，").replace("\\n", " ");
    }}
}}
""",
        ),
        _write(
            java_root / "service" / f"{class_name}AuditService.java",
            f"""package {package}.service;

import {package}.domain.{entity_name};
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

public class {class_name}AuditService {{
    private final List<String> auditLines = new ArrayList<>();

    public void recordCreate(String operator, {entity_name} record) {{
        append(operator, "CREATE", record, "新增{module.title}记录");
    }}

    public void recordUpdate(String operator, {entity_name} record) {{
        append(operator, "UPDATE", record, "修改{module.title}记录");
    }}

    public void recordDelete(String operator, {entity_name} record) {{
        append(operator, "DELETE", record, "删除{module.title}记录");
    }}

    public void recordExport(String operator, int count) {{
        auditLines.add(LocalDateTime.now()
                + " | " + normalizeOperator(operator)
                + " | EXPORT | {module.title} | count=" + count);
    }}

    public List<String> listRecentAuditLines(int limit) {{
        int safeLimit = Math.max(1, limit);
        int fromIndex = Math.max(0, auditLines.size() - safeLimit);
        return new ArrayList<>(auditLines.subList(fromIndex, auditLines.size()));
    }}

    private void append(String operator, String action, {entity_name} record, String message) {{
        String code = record == null ? "-" : record.getCode();
        auditLines.add(LocalDateTime.now()
                + " | " + normalizeOperator(operator)
                + " | " + action
                + " | " + code
                + " | " + message);
    }}

    private String normalizeOperator(String operator) {{
        return operator == null || operator.trim().isEmpty() ? "system" : operator.trim();
    }}
}}
""",
        ),
    ]


def _java_schema_sql(blueprint: ProductBlueprint) -> str:
    blocks = []
    for module in blueprint.modules:
        blocks.append(
            f"""create table if not exists {module.key}_record (
    id bigint primary key,
    code varchar(64) not null,
    name varchar(128) not null,
    status varchar(32) not null,
    owner_role varchar(64),
    description varchar(500),
    created_at datetime,
    updated_at datetime
);

create index idx_{module.key}_status on {module.key}_record(status);
create index idx_{module.key}_code on {module.key}_record(code);
"""
        )
    return "\n".join(blocks)


def _python_database_module() -> str:
    return '''from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3


class Database:
    def __init__(self, path: str | Path | None = None):
        configured = path or os.getenv("SOFTWARE_DB_PATH") or "data/application.db"
        self.path = Path(configured)

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


default_database = Database()
'''


def _python_migrations_module() -> str:
    return '''from pathlib import Path
from app.core.database import Database, default_database


MIGRATION_FILE = Path(__file__).resolve().parents[2] / "migrations" / "001_initial.sql"


def initialize_database(database: Database | None = None) -> Database:
    current = database or default_database
    script = MIGRATION_FILE.read_text(encoding="utf-8")
    with current.connection() as connection:
        connection.executescript(script)
    return current
'''


def _python_schema_sql(blueprint: ProductBlueprint) -> str:
    blocks: list[str] = []
    owner_candidates = list(getattr(blueprint, "roles", []) or getattr(blueprint, "target_users", []) or ["业务操作员"])
    owner_role = str(owner_candidates[0] or "业务操作员")

    def sql_text(value: object) -> str:
        return str(value or "").replace("'", "''")

    for module_index, module in enumerate(blueprint.modules, start=1):
        table = f"{_snake(module.key)}_record"
        token = _snake(module.key)
        code_prefix = re.sub(r"[^A-Za-z0-9]", "", token).upper()[:4] or f"M{module_index}"
        operation_labels = [str(value).strip() for value in (module.operations or []) if str(value).strip()]
        status_cycle = ["ENABLED", "PENDING", "PROCESSING"]
        seed_rows = []
        for row_index in range(1, 4):
            operation = operation_labels[(row_index - 1) % len(operation_labels)] if operation_labels else "业务处理"
            code = f"{code_prefix}-{module_index:02d}{row_index:02d}"
            name = f"{module.title}{'待办' if row_index == 1 else '记录' if row_index == 2 else '任务'}"
            description = f"{module.title}：{operation}，用于运行界面数据加载与状态核验。"
            timestamp = f"2026-06-{20 + row_index:02d}T{8 + row_index:02d}:1{row_index}:00"
            seed_rows.append(
                "INSERT OR IGNORE INTO "
                f"{table} (code, name, status, owner_role, description, created_at, updated_at) VALUES "
                f"('{sql_text(code)}', '{sql_text(name)}', '{status_cycle[row_index - 1]}', "
                f"'{sql_text(owner_role)}', '{sql_text(description)}', '{timestamp}', '{timestamp}');"
            )
        blocks.append(
            f'''CREATE TABLE IF NOT EXISTS {table} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    owner_role TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_{table}_status ON {table}(status);
CREATE INDEX IF NOT EXISTS idx_{table}_updated_at ON {table}(updated_at);
{chr(10).join(seed_rows)}
'''
        )
    return "\n".join(blocks)


def _python_repository_module(module: FeatureModule) -> str:
    token = _snake(module.key)
    class_name = _pascal(token)
    table = f"{token}_record"
    return f'''from datetime import datetime
from app.core.database import Database, default_database
from app.core.migrations import initialize_database
from app.models.{token}_model import {class_name}Record


class {class_name}Repository:
    def __init__(self, database: Database | None = None):
        self.database = initialize_database(database or default_database)

    def list(self, keyword: str | None = None, status: str | None = None) -> list[{class_name}Record]:
        clauses = []
        parameters: list[str] = []
        if keyword:
            clauses.append("(name LIKE ? OR code LIKE ?)")
            parameters.extend([f"%{{keyword}}%", f"%{{keyword}}%"])
        if status:
            clauses.append("status = ?")
            parameters.append(status)
        where = f" WHERE {{' AND '.join(clauses)}}" if clauses else ""
        sql = "SELECT * FROM {table}" + where + " ORDER BY updated_at DESC, id DESC"
        with self.database.connection() as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return [self._to_record(row) for row in rows]

    def find_by_id(self, record_id: int) -> {class_name}Record | None:
        with self.database.connection() as connection:
            row = connection.execute("SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
        return self._to_record(row) if row else None

    def find_by_code(self, code: str) -> {class_name}Record | None:
        with self.database.connection() as connection:
            row = connection.execute("SELECT * FROM {table} WHERE code = ?", (code,)).fetchone()
        return self._to_record(row) if row else None

    def create(self, code: str, name: str, owner_role: str, description: str) -> {class_name}Record:
        now = datetime.now().isoformat(timespec="seconds")
        with self.database.connection() as connection:
            cursor = connection.execute(
                "INSERT INTO {table} (code, name, status, owner_role, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (code, name, "ENABLED", owner_role, description, now, now),
            )
            record_id = int(cursor.lastrowid)
        record = self.find_by_id(record_id)
        if record is None:
            raise RuntimeError("保存后未找到业务记录")
        return record

    def update_status(self, record_id: int, status: str) -> {class_name}Record:
        now = datetime.now().isoformat(timespec="seconds")
        with self.database.connection() as connection:
            cursor = connection.execute(
                "UPDATE {table} SET status = ?, updated_at = ? WHERE id = ?",
                (status, now, record_id),
            )
            if cursor.rowcount != 1:
                raise ValueError("记录不存在")
        record = self.find_by_id(record_id)
        if record is None:
            raise RuntimeError("更新后未找到业务记录")
        return record

    @staticmethod
    def _to_record(row) -> {class_name}Record:
        return {class_name}Record(
            id=int(row["id"]), code=str(row["code"]), name=str(row["name"]),
            status=str(row["status"]), owner_role=str(row["owner_role"]),
            description=str(row["description"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
        )
'''


def _python_service_module(module: FeatureModule) -> str:
    token = _snake(module.key)
    class_name = _pascal(token)
    return f'''from app.models.{token}_model import {class_name}Record
from app.repositories.{token}_repository import {class_name}Repository


class {class_name}Service:
    """{module.title}业务服务。"""

    def __init__(self, repository: {class_name}Repository | None = None):
        self.repository = repository or {class_name}Repository()

    def list_records(self, keyword: str | None = None, status: str | None = None) -> list[{class_name}Record]:
        return self.repository.list(keyword=keyword, status=status)

    def create_record(self, code: str, name: str, owner_role: str, description: str) -> {class_name}Record:
        if not code.strip() or not name.strip():
            raise ValueError("业务编号和名称不能为空")
        if self.repository.find_by_code(code.strip()):
            raise ValueError("业务编号已存在")
        return self.repository.create(code.strip(), name.strip(), owner_role.strip() or "业务操作员", description.strip())

    def update_status(self, record_id: int, status: str) -> {class_name}Record:
        allowed = {{"PENDING", "ENABLED", "PROCESSING", "COMPLETED", "ARCHIVED"}}
        if status not in allowed:
            raise ValueError("状态不在允许范围内")
        return self.repository.update_status(record_id, status)

    def count_by_status(self) -> dict[str, int]:
        result: dict[str, int] = {{}}
        for record in self.repository.list():
            result[record.status] = result.get(record.status, 0) + 1
        return result
'''


def _python_persistence_test(blueprint: ProductBlueprint) -> str:
    module = blueprint.modules[0] if blueprint.modules else FeatureModule("business", "业务模块", "业务处理", ["BusinessRecord"])
    token = _snake(module.key)
    class_name = _pascal(token)
    return f'''from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

# Support discovery with an isolated/embedded Python interpreter as well.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import Database
from app.repositories.{token}_repository import {class_name}Repository
from app.services.{token}_service import {class_name}Service


class PersistenceTests(unittest.TestCase):
    def test_record_survives_repository_reopen(self):
        with TemporaryDirectory() as temp_dir:
            database = Database(Path(temp_dir) / "application.db")
            service = {class_name}Service({class_name}Repository(database))
            created = service.create_record("TEST-001", "持久化测试记录", "tester", "验证 SQLite 仓储")
            self.assertEqual(created.status, "ENABLED")

            reopened = {class_name}Service({class_name}Repository(Database(database.path)))
            records = reopened.list_records(keyword="TEST-001")
            self.assertEqual(len(records), 1)
            updated = reopened.update_status(records[0].id, "COMPLETED")
            self.assertEqual(updated.status, "COMPLETED")
            self.assertEqual(reopened.count_by_status()["COMPLETED"], 1)

    def test_duplicate_code_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            service = {class_name}Service({class_name}Repository(Database(Path(temp_dir) / "application.db")))
            service.create_record("TEST-002", "首条记录", "tester", "")
            with self.assertRaisesRegex(ValueError, "业务编号已存在"):
                service.create_record("TEST-002", "重复记录", "tester", "")


if __name__ == "__main__":
    unittest.main()
'''


def _generate_python_project(task: GenerationTask, blueprint: ProductBlueprint, source_dir: Path, include_readme: bool = True) -> list[Path]:
    app_dir = source_dir / "app"
    for folder in [
        app_dir / "routers",
        app_dir / "services",
        app_dir / "repositories",
        app_dir / "models",
        app_dir / "schemas",
        app_dir / "core",
        source_dir / "migrations",
        source_dir / "tests",
        source_dir / "data",
    ]:
        folder.mkdir(parents=True, exist_ok=True)
    files = [
        _write(source_dir / "requirements.txt", "fastapi\nuvicorn\npydantic\n"),
        _write(app_dir / "__init__.py", ""),
        _write(app_dir / "core" / "__init__.py", ""),
        _write(app_dir / "repositories" / "__init__.py", ""),
        _write(source_dir / "tests" / "__init__.py", ""),
        _write(app_dir / "core" / "database.py", _python_database_module()),
        _write(app_dir / "core" / "migrations.py", _python_migrations_module()),
        _write(source_dir / "migrations" / "001_initial.sql", _python_schema_sql(blueprint)),
        _write(
            app_dir / "main.py",
            f'''from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from app.core.migrations import initialize_database

initialize_database()
app = FastAPI(title="{task.software_name}", version="{task.version}")
app.mount("/ui-prototype", StaticFiles(directory="ui-prototype", html=True), name="ui_prototype")


@app.get("/health")
def health_check():
    return {{"status": "ok", "software": "{task.software_name}", "version": "{task.version}"}}


@app.get("/")
def prototype_entry():
    return RedirectResponse(url="/ui-prototype/index.html")
''',
        ),
    ]
    if include_readme:
        files.insert(0, _write(source_dir / "README.md", _readme(task, blueprint)))
    for module in blueprint.modules:
        token = _snake(module.key)
        title = module.title
        files.extend(
            [
                _write(
                    app_dir / "models" / f"{token}_model.py",
                    f'''from dataclasses import dataclass
from datetime import datetime


@dataclass
class {_pascal(token)}Record:
    id: int
    code: str
    name: str
    status: str
    owner_role: str
    description: str
    created_at: datetime
    updated_at: datetime
''',
                ),
                _write(
                    app_dir / "repositories" / f"{token}_repository.py",
                    _python_repository_module(module),
                ),
                _write(
                    app_dir / "services" / f"{token}_service.py",
                    _python_service_module(module),
                ),
                _write(
                    app_dir / "routers" / f"{token}_router.py",
                    f'''from fastapi import APIRouter
from app.services.{token}_service import {_pascal(token)}Service

router = APIRouter(prefix="/{token}", tags=["{title}"])
service = {_pascal(token)}Service()


@router.get("/")
def list_records(keyword: str | None = None, status: str | None = None):
    return service.list_records(keyword=keyword, status=status)


@router.post("/")
def create_record(code: str, name: str, owner_role: str, description: str):
    return service.create_record(code, name, owner_role, description)
''',
                ),
            ]
        )
    router_imports = "\n".join(
        f"from app.routers.{_snake(module.key)}_router import router as {_snake(module.key)}_router"
        for module in blueprint.modules
    )
    router_mounts = "\n".join(f"app.include_router({_snake(module.key)}_router)" for module in blueprint.modules)
    files.append(
        _write(
            app_dir / "runtime_routes.py",
            f'''from app.main import app
{router_imports}

{router_mounts}
''',
        )
    )
    files.append(
        _write(
            source_dir / "tests" / "test_persistence.py",
            _python_persistence_test(blueprint),
        )
    )
    files = _ensure_generic_line_target(files, app_dir / "services", task, blueprint, target_lines=3200, extension=".py")
    files = _align_source_material_pages(files, source_dir, app_dir / "services", ".py")
    return files


def _generate_javascript_project_legacy(task: GenerationTask, blueprint: ProductBlueprint, source_dir: Path, include_readme: bool = True) -> list[Path]:
    src = source_dir / "src"
    for folder in [src / "routes", src / "services", src / "models", src / "middleware"]:
        folder.mkdir(parents=True, exist_ok=True)
    route_mounts = "\n".join(
        f'app.use("/{_snake(module.key)}", require("./routes/{_snake(module.key)}Route"));'
        for module in blueprint.modules
    )
    files = [
        _write(
            source_dir / "package.json",
            f'''{{
  "name": "{_ascii_token(task.software_name)}",
  "version": "1.0.0",
  "description": "{task.software_name}",
  "main": "src/server.js",
  "scripts": {{
    "start": "node src/server.js"
  }},
  "dependencies": {{
    "express": "^4.18.2"
  }}
}}
''',
        ),
        _write(
            src / "server.js",
            f'''const express = require("express");
const path = require("path");
const app = express();
const port = Number(process.env.PORT || 8080);
app.use(express.json());
app.use("/ui-prototype", express.static(path.join(__dirname, "..", "ui-prototype")));
{route_mounts}

app.get("/health", (req, res) => {{
  res.json({{ status: "ok", software: "{task.software_name}", version: "{task.version}" }});
}});

app.get("/", (req, res) => {{
  res.redirect("/ui-prototype/index.html");
}});

app.listen(port, () => {{
  console.log("{task.software_name} service started on " + port);
}});
''',
        ),
    ]
    if include_readme:
        files.insert(0, _write(source_dir / "README.md", _readme(task, blueprint)))
    for module in blueprint.modules:
        token = _snake(module.key)
        title = module.title
        files.extend(
            [
                _write(
                    src / "models" / f"{token}Record.js",
                    f'''class {_pascal(token)}Record {{
  constructor(data) {{
    this.id = data.id;
    this.code = data.code;
    this.name = data.name;
    this.status = data.status || "ENABLED";
    this.ownerRole = data.ownerRole;
    this.description = data.description;
    this.createdAt = data.createdAt || new Date();
    this.updatedAt = data.updatedAt || new Date();
  }}
}}

module.exports = {_pascal(token)}Record;
''',
                ),
                _write(
                    src / "services" / f"{token}Service.js",
                    f'''const {_pascal(token)}Record = require("../models/{token}Record");

class {_pascal(token)}Service {{
  constructor() {{
    this.records = [];
  }}

  list(query) {{
    return this.records.filter((record) => {{
      const keywordMatched = !query.keyword || record.name.includes(query.keyword) || record.code.includes(query.keyword);
      const statusMatched = !query.status || query.status === record.status;
      return keywordMatched && statusMatched;
    }});
  }}

  create(payload) {{
    const record = new {_pascal(token)}Record({{ ...payload, id: this.records.length + 1 }});
    this.records.push(record);
    return record;
  }}

  changeStatus(id, status) {{
    const record = this.records.find((item) => item.id === Number(id));
    if (!record) {{
      throw new Error("记录不存在");
    }}
    record.status = status;
    record.updatedAt = new Date();
    return record;
  }}
}}

module.exports = new {_pascal(token)}Service();
''',
                ),
                _write(
                    src / "routes" / f"{token}Route.js",
                    f'''const express = require("express");
const service = require("../services/{token}Service");
const router = express.Router();

router.get("/", (req, res) => {{
  res.json(service.list(req.query));
}});

router.post("/", (req, res) => {{
  res.json(service.create(req.body));
}});

router.patch("/:id/status", (req, res) => {{
  res.json(service.changeStatus(req.params.id, req.body.status));
}});

module.exports = router;
''',
                ),
            ]
        )
    files = _ensure_generic_line_target(files, src / "services", task, blueprint, target_lines=3200, extension=".js")
    files = _align_source_material_pages(files, source_dir, src / "services", ".js")
    return files


def _generate_javascript_project(task: GenerationTask, blueprint: ProductBlueprint, source_dir: Path, include_readme: bool = True) -> list[Path]:
    src = source_dir / "src"
    for folder in [src / "routes", src / "services", src / "models", src / "middleware"]:
        folder.mkdir(parents=True, exist_ok=True)
    files = [
        _write(
            source_dir / "package.json",
            f'''{{
  "name": "{_ascii_token(task.software_name)}",
  "version": "1.0.0",
  "description": "{task.software_name}",
  "main": "src/server.js",
  "scripts": {{
    "start": "node src/server.js"
  }}
}}
''',
        ),
        _write(src / "server.js", _javascript_runtime_server(task, blueprint)),
    ]
    if include_readme:
        files.insert(0, _write(source_dir / "README.md", _readme(task, blueprint)))
    for module in blueprint.modules:
        token = _snake(module.key)
        files.extend(
            [
                _write(src / "models" / f"{token}Record.js", _javascript_model_source(module, token)),
                _write(src / "services" / f"{token}Service.js", _javascript_service_source(module, token)),
                _write(src / "routes" / f"{token}Route.js", _javascript_route_source(module, token)),
            ]
        )
    files = _ensure_generic_line_target(files, src / "services", task, blueprint, target_lines=3200, extension=".js")
    files = _align_source_material_pages(files, source_dir, src / "services", ".js")
    return files


def _javascript_runtime_server(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    route_registrations = "\n".join(
        f'registerRoute(require("./routes/{_snake(module.key)}Route"));'
        for module in blueprint.modules
    )
    return f'''const fs = require("fs");
const http = require("http");
const path = require("path");
const url = require("url");

const SOFTWARE_NAME = {_json_literal(task.software_name)};
const SOFTWARE_VERSION = {_json_literal(task.version)};
const PORT = Number(process.env.PORT || 8080);
const UI_ROOT = path.resolve(__dirname, "..", "ui-prototype");
const routes = [];

function registerRoute(routeModule) {{
  if (!routeModule || !Array.isArray(routeModule.routes)) {{
    return;
  }}
  for (const route of routeModule.routes) {{
    routes.push({{
      basePath: normalizePath(routeModule.basePath || route.basePath || "/"),
      method: String(route.method || "GET").toUpperCase(),
      path: normalizePath(route.path || "/"),
      handler: route.handler,
    }});
  }}
}}

{route_registrations}

function normalizePath(value) {{
  const text = String(value || "/").trim();
  const withSlash = text.startsWith("/") ? text : "/" + text;
  return withSlash.replace(/\\/+/g, "/").replace(/\\/$/, "") || "/";
}}

function joinRoute(basePath, routePath) {{
  if (routePath === "/") {{
    return normalizePath(basePath);
  }}
  return normalizePath(basePath + "/" + routePath.replace(/^\\//, ""));
}}

function matchRoute(method, pathname) {{
  const requestSegments = normalizePath(pathname).split("/").filter(Boolean);
  for (const route of routes) {{
    if (route.method !== method) {{
      continue;
    }}
    const fullPath = joinRoute(route.basePath, route.path);
    const routeSegments = fullPath.split("/").filter(Boolean);
    if (routeSegments.length !== requestSegments.length) {{
      continue;
    }}
    const params = {{}};
    let matched = true;
    for (let index = 0; index < routeSegments.length; index += 1) {{
      const expected = routeSegments[index];
      const actual = requestSegments[index];
      if (expected.startsWith(":")) {{
        params[expected.slice(1)] = decodeURIComponent(actual);
      }} else if (expected !== actual) {{
        matched = false;
        break;
      }}
    }}
    if (matched) {{
      return {{ route, params }};
    }}
  }}
  return null;
}}

function sendJson(res, status, payload) {{
  const body = JSON.stringify(payload);
  res.writeHead(status, {{
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store",
  }});
  res.end(body);
}}

function redirect(res, location) {{
  res.writeHead(302, {{ Location: location }});
  res.end();
}}

function mimeType(filePath) {{
  const ext = path.extname(filePath).toLowerCase();
  return {{
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml; charset=utf-8",
  }}[ext] || "application/octet-stream";
}}

function servePrototype(pathname, res) {{
  const relative = decodeURIComponent(pathname.replace(/^\\/ui-prototype\\/?/, "")) || "index.html";
  const requested = path.resolve(UI_ROOT, relative);
  if (!requested.startsWith(UI_ROOT)) {{
    sendJson(res, 403, {{ error: "forbidden" }});
    return;
  }}
  fs.stat(requested, (statError, stat) => {{
    if (statError || !stat.isFile()) {{
      sendJson(res, 404, {{ error: "not_found" }});
      return;
    }}
    res.writeHead(200, {{
      "Content-Type": mimeType(requested),
      "Cache-Control": "no-store",
    }});
    fs.createReadStream(requested).pipe(res);
  }});
}}

function readBody(req) {{
  return new Promise((resolve, reject) => {{
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => {{
      const raw = Buffer.concat(chunks).toString("utf8").trim();
      if (!raw) {{
        resolve({{}});
        return;
      }}
      try {{
        resolve(JSON.parse(raw));
      }} catch (error) {{
        reject(new Error("invalid_json_body"));
      }}
    }});
    req.on("error", reject);
  }});
}}

const server = http.createServer(async (req, res) => {{
  const parsed = url.parse(req.url || "/", true);
  const pathname = decodeURIComponent(parsed.pathname || "/");
  const method = String(req.method || "GET").toUpperCase();

  if (method === "GET" && pathname === "/health") {{
    sendJson(res, 200, {{
      status: "ok",
      software: SOFTWARE_NAME,
      version: SOFTWARE_VERSION,
      routeCount: routes.length,
      servedPrototype: fs.existsSync(path.join(UI_ROOT, "index.html")),
    }});
    return;
  }}
  if (method === "GET" && pathname === "/") {{
    redirect(res, "/ui-prototype/index.html");
    return;
  }}
  if (method === "GET" && pathname.startsWith("/ui-prototype")) {{
    servePrototype(pathname, res);
    return;
  }}

  const matched = matchRoute(method, pathname);
  if (!matched) {{
    sendJson(res, 404, {{ error: "route_not_found", path: pathname }});
    return;
  }}

  try {{
    const body = ["POST", "PUT", "PATCH"].includes(method) ? await readBody(req) : {{}};
    const result = await matched.route.handler({{
      query: parsed.query || {{}},
      params: matched.params,
      body,
      method,
      path: pathname,
    }});
    sendJson(res, 200, {{ success: true, data: result }});
  }} catch (error) {{
    sendJson(res, 400, {{ success: false, error: error.message || "request_failed" }});
  }}
}});

server.listen(PORT, "127.0.0.1", () => {{
  console.log(`${{SOFTWARE_NAME}} service started on ${{PORT}}`);
}});
'''


def _javascript_model_source(module: FeatureModule, token: str) -> str:
    return f'''class {_pascal(token)}Record {{
  constructor(data) {{
    Object.assign(this, data);
    this.id = data.id;
    this.code = data.code;
    this.name = data.name;
    this.status = data.status || "ENABLED";
    this.ownerRole = data.ownerRole;
    this.description = data.description;
    this.moduleTitle = data.moduleTitle || {_json_literal(module.title)};
    this.region = data.region;
    this.priority = data.priority;
    this.result = data.result;
    this.createdAt = data.createdAt || new Date();
    this.updatedAt = data.updatedAt || new Date();
  }}
}}

module.exports = {_pascal(token)}Record;
'''


def _javascript_service_source(module: FeatureModule, token: str) -> str:
    record_name = f"{_pascal(token)}Record"
    seed_records = _json_block_literal(_javascript_seed_records(module, token), indent=6)
    default_description = _business_record_description(module, index=1)
    return f'''const {record_name} = require("../models/{token}Record");

class {_pascal(token)}Service {{
  constructor() {{
    this.records = {seed_records}.map((item) => new {record_name}(item));
  }}

  list(query = {{}}) {{
    return this.records.filter((record) => {{
      const keyword = String(query.keyword || "").trim();
      const keywordMatched = !keyword
        || record.name.includes(keyword)
        || record.code.includes(keyword)
        || String(record.region || "").includes(keyword);
      const statusMatched = !query.status || query.status === record.status;
      return keywordMatched && statusMatched;
    }});
  }}

  find(id) {{
    const record = this.records.find((item) => item.id === Number(id));
    if (!record) {{
      throw new Error("record_not_found");
    }}
    return record;
  }}

  create(payload = {{}}) {{
    const record = new {record_name}({{
      ...payload,
      id: this.records.length + 1,
      code: payload.code || this.createCode(),
      name: payload.name || {_json_literal((module.title or "业务") + "对象")},
      status: payload.status || "PENDING",
      moduleTitle: {_json_literal(module.title)},
      ownerRole: payload.ownerRole || {_json_literal(_javascript_owner_role(module))},
      description: payload.description || {_json_literal(default_description)},
      updatedAt: new Date().toISOString(),
    }});
    this.records.push(record);
    return record;
  }}

  changeStatus(id, status) {{
    const record = this.find(id);
    record.status = status || "PROCESSING";
    record.updatedAt = new Date();
    record.result = this.statusText(record.status);
    return record;
  }}

  summary() {{
    const total = this.records.length;
    const pending = this.records.filter((item) => item.status === "PENDING").length;
    const completed = this.records.filter((item) => item.status === "COMPLETED").length;
    return {{
      module: {_json_literal(module.title)},
      total,
      pending,
      completed,
      latestRecord: this.records[0] || null,
    }};
  }}

  createCode() {{
    const sequence = String(this.records.length + 1).padStart(4, "0");
    return "{_business_code_prefix(module, token)}-" + sequence;
  }}

  statusText(status) {{
    return {{
      ENABLED: "enabled",
      PENDING: "pending_review",
      PROCESSING: "processing",
      COMPLETED: "completed",
      ARCHIVED: "archived",
    }}[status] || "processing";
  }}
}}

module.exports = new {_pascal(token)}Service();
'''


def _javascript_route_source(module: FeatureModule, token: str) -> str:
    return f'''const service = require("../services/{token}Service");

function createRouter(basePath) {{
  const routes = [];
  const router = {{
    get(path, handler) {{
      routes.push({{ method: "GET", path, handler }});
    }},
    post(path, handler) {{
      routes.push({{ method: "POST", path, handler }});
    }},
    patch(path, handler) {{
      routes.push({{ method: "PATCH", path, handler }});
    }},
  }};
  return {{ basePath, routes, router }};
}}

const route = createRouter("/{token}");
const router = route.router;

router.get("/", (request) => service.list(request.query));
router.get("/summary", () => service.summary());
router.get("/:id", (request) => service.find(request.params.id));
router.post("/", (request) => service.create(request.body));
router.patch("/:id/status", (request) => service.changeStatus(request.params.id, request.body.status));

module.exports = {{
  basePath: route.basePath,
  moduleKey: "{token}",
  moduleTitle: {_json_literal(module.title)},
  routes: route.routes,
}};
'''


def _javascript_seed_records(module: FeatureModule, token: str) -> list[dict[str, object]]:
    fields = [str(item) for item in (module.data_fields or []) if str(item).strip()]
    operations = [str(item) for item in (module.operations or []) if str(item).strip()]
    statuses = ["ENABLED", "PENDING", "PROCESSING", "COMPLETED"]
    prefix = _business_code_prefix(module, token)
    names = _business_record_names(module)
    regions = _business_record_regions(module, fields)
    transport = _is_transport_module(module)
    records: list[dict[str, object]] = []
    for index in range(1, 5):
        code = f"{prefix}-{1000 + index}"
        name = names[(index - 1) % len(names)]
        region = regions[(index - 1) % len(regions)] if regions else module.title
        operation = operations[(index - 1) % len(operations)] if operations else "business_processing"
        record: dict[str, object] = {
            "id": index,
            "code": code,
            "name": name,
            "status": statuses[(index - 1) % len(statuses)],
            "ownerRole": _javascript_owner_role(module),
            "description": _business_record_description(module, operation=operation, region=region, index=index),
            "moduleTitle": module.title,
            "region": region,
            "priority": "P" + str((index % 3) + 1),
            "result": operation,
            "createdAt": f"2026-06-{20 + index:02d}T09:{10 + index:02d}:00",
            "updatedAt": f"2026-06-{24 + index:02d}T15:{20 + index:02d}:00",
            "nodeSequence": _transport_node_sequence(index) if transport else _business_process_sequence(module, index),
            "direction": ["北向", "南向", "双向", "东向"][(index - 1) % 4] if transport else _business_direction(index),
            "serviceScope": _transport_service_scope(index) if transport else region,
            "fieldValues": {},
        }
        field_values: dict[str, object] = {}
        for field_index, field in enumerate(fields[:10]):
            value = _business_field_value(module, field, index, code, name)
            record[field] = value
            field_values[field] = value
        record["fieldValues"] = field_values
        records.append(record)
    return records


def _business_record_description(
    module: FeatureModule,
    *,
    operation: str = "",
    region: str = "",
    index: int = 1,
) -> str:
    title = str(getattr(module, "title", "") or "业务模块")
    operations = [str(item) for item in (getattr(module, "operations", []) or []) if str(item).strip()]
    operation_text = operation or (operations[(index - 1) % len(operations)] if operations else "业务处理")
    if region:
        region_text = region
    elif _is_transport_module(module):
        region_text = _transport_service_scope(index)
    else:
        regions = _business_record_regions(
            module,
            [str(item) for item in (getattr(module, "data_fields", []) or []) if str(item).strip()],
        )
        region_text = regions[(index - 1) % len(regions)] if regions else f"{title}服务区域{index}"
    phase = ["建档", "复核", "匹配", "归档"][(index - 1) % 4]
    return f"{title}-{operation_text}-{region_text}-{phase}"


def _business_field_value(module: FeatureModule, field: str, index: int, code: str, name: str) -> str:
    title = str(getattr(module, "title", "") or "")
    text = str(field or "")
    if re.search(r"编号|编码|单号|代码|ID", text, re.I):
        return code
    if re.search(r"名称|标题|线路|路径", text):
        return name
    transport = _is_transport_module(module)
    if transport and re.search(r"途经|节点序列|站点序列", text):
        return _transport_node_sequence(index)
    if transport and re.search(r"方向|通行", text):
        return ["北向", "南向", "双向", "东向"][(index - 1) % 4]
    if re.search(r"范围|服务|覆盖|片区|区域", text):
        return _transport_service_scope(index) if transport else f"{title}服务区域{index}"
    if re.search(r"状态|进度", text):
        return ["已启用", "待复核", "处理中", "已完成"][(index - 1) % 4]
    if re.search(r"时间|日期|更新|创建|生效", text):
        return f"2026-06-{24 + index:02d} 15:{20 + index:02d}"
    if re.search(r"等级|优先级|适配", text):
        return ["一级适配", "二级适配", "重点复核", "冲突校验"][(index - 1) % 4]
    if re.search(r"角色|责任|人员|单位|部门", text):
        return _javascript_owner_role(module)
    if re.search(r"结果|结论|说明|备注", text):
        return f"{title}已完成{['建档', '复核', '匹配', '归档'][(index - 1) % 4]}"
    return [code, name, f"{title}业务对象{index}", f"{title}处理结果{index}"][(index - 1) % 4]


def _transport_node_sequence(index: int) -> str:
    sequences = [
        "沪杭枢纽-浦东东区-临港接驳点",
        "虹桥枢纽-外环货运站-南环联络口",
        "机场北站-航站楼集散点-东区短驳口",
        "外高桥港区-保税仓节点-主干线入口",
    ]
    return sequences[(index - 1) % len(sequences)]


def _transport_service_scope(index: int) -> str:
    scopes = ["浦东东区至临港片区", "虹桥枢纽至南环货运带", "机场枢纽至东部接驳区", "港区集疏运服务圈"]
    return scopes[(index - 1) % len(scopes)]


def _business_process_sequence(module: FeatureModule, index: int) -> str:
    operations = [str(item).strip() for item in (getattr(module, "operations", []) or []) if str(item).strip()]
    if not operations:
        return "业务受理-规则校验-状态更新"
    rotated = operations[(index - 1) % len(operations) :] + operations[: (index - 1) % len(operations)]
    return "-".join(rotated[:3])


def _business_direction(index: int) -> str:
    return ["受理方向", "复核方向", "协同方向", "归档方向"][(index - 1) % 4]


def _javascript_owner_role(module: FeatureModule) -> str:
    roles = [str(item) for item in (getattr(module, "roles", []) or []) if str(item).strip()]
    return roles[0] if roles else "业务操作员"


def _is_transport_module(module: FeatureModule) -> bool:
    text = " ".join(
        [
            str(getattr(module, "title", "") or ""),
            str(getattr(module, "description", "") or ""),
            " ".join(str(item) for item in (getattr(module, "data_fields", []) or [])),
        ]
    )
    return build_domain_profile(context_text=text).requires_route_topology


def _business_code_prefix(module: FeatureModule, fallback_token: str) -> str:
    title = str(getattr(module, "title", "") or "")
    if "干线" in title:
        return "TR-HX"
    if "支线" in title:
        return "BR-JR"
    if "节点" in title or "衔接" in title:
        return "TN-JD"
    if "匹配" in title or "评估" in title:
        return "MT-PG"
    if "规则" in title:
        return "CR-GZ"
    if "问题" in title:
        return "WT-CZ"
    if "发布" in title or "方案" in title:
        return "FA-FB"
    if "统计" in title or "报表" in title:
        return "TJ-BB"
    token = re.sub(r"[^A-Za-z0-9]+", "", fallback_token or "YW").upper()
    return (token[:2] or "YW") + "-YW"


def _business_record_names(module: FeatureModule) -> list[str]:
    title = str(getattr(module, "title", "") or "业务记录")
    if "干线" in title:
        return ["沪杭干线北向联络线", "城际货运南环干线", "机场枢纽快速干线", "港区集疏运主干线"]
    if "支线" in title:
        return ["临港园区接驳支线", "东部片区社区支线", "冷链仓储短驳支线", "客运站微循环支线"]
    if "节点" in title or "衔接" in title:
        return ["综合客运枢纽A区", "铁路货场换装节点", "港区东门接驳点", "机场北侧集散节点"]
    if "匹配" in title or "评估" in title:
        return ["干支线接驳时效评估", "覆盖盲区匹配复核", "节点容量冲突评估", "跨区线路组合测算"]
    if "规则" in title:
        return ["接驳距离阈值规则", "等待时长上限规则", "节点容量窗口规则", "服务范围重叠规则"]
    if "问题" in title and _is_transport_module(module):
        return ["支线覆盖缺口工单", "节点容量冲突工单", "方向不一致处置单", "服务范围越界工单"]
    if "发布" in title or "方案" in title:
        return ["临港干支线适配方案", "机场枢纽接驳发布单", "港区集疏运生效方案", "城际线路换乘方案"]
    if "统计" in title or "报表" in title:
        return ["日运行适配汇总", "区域衔接效率报表", "规则命中趋势分析", "问题闭环统计清单"]
    return [f"{title}待办", f"{title}复核单", f"{title}处理单", f"{title}归档单"]


def _business_record_regions(module: FeatureModule, fields: list[str]) -> list[str]:
    title = str(getattr(module, "title", "") or "")
    if _is_transport_module(module):
        return ["浦东东区", "临港新片区", "虹桥枢纽片区", "外高桥港区"]
    return [f"{title}服务区域{index}" for index in range(1, 5)]


def _generate_generic_project(task: GenerationTask, blueprint: ProductBlueprint, source_dir: Path) -> list[Path]:
    files = [_write(source_dir / "README.md", _readme(task, blueprint))]
    extension = {
        "PHP": ".php",
        "C#": ".cs",
        "C++": ".cpp",
        "HTML": ".html",
    }.get(task.language, ".txt")
    for module in blueprint.modules:
        files.append(
            _write(
                source_dir / f"{_snake(module.key)}{extension}",
                _generic_source_content(task, module, extension),
            )
        )
    files = _ensure_generic_line_target(files, source_dir, task, blueprint, target_lines=3200, extension=extension)
    files = _align_source_material_pages(files, source_dir, source_dir, extension)
    return files


def _generate_embedded_mixed_project(task: GenerationTask, blueprint: ProductBlueprint, source_dir: Path) -> list[Path]:
    for folder in [source_dir / "firmware" / "src", source_dir / "firmware" / "include", source_dir / "edge" / "services", source_dir / "scripts", source_dir / "config"]:
        folder.mkdir(parents=True, exist_ok=True)
    files = [_write(source_dir / "README.md", _readme(task, blueprint))]
    files.append(
        _write(
            source_dir / "CMakeLists.txt",
            f"""cmake_minimum_required(VERSION 3.20)
project({_ascii_token(task.software_name)}_embedded)
set(CMAKE_CXX_STANDARD 17)
add_executable(edge_monitor firmware/src/main.cpp firmware/src/device_driver.c)
""",
        )
    )
    files.append(
        _write(
            source_dir / "firmware" / "include" / "device_driver.h",
            """#pragma once
#ifdef __cplusplus
extern "C" {
#endif
typedef struct SensorSample {
    int channel;
    double value;
    long long timestamp;
} SensorSample;
int device_driver_open(const char* port_name);
SensorSample device_driver_read(int channel);
void device_driver_close(void);
#ifdef __cplusplus
}
#endif
""",
        )
    )
    files.append(
        _write(
            source_dir / "firmware" / "src" / "device_driver.c",
            f"""#include "../include/device_driver.h"
#include <time.h>

static const char* SOFTWARE_NAME = "{_c_literal(task.software_name)}";
static int driver_ready = 0;

int device_driver_open(const char* port_name) {{
    (void)SOFTWARE_NAME;
    (void)port_name;
    driver_ready = 1;
    return driver_ready;
}}

SensorSample device_driver_read(int channel) {{
    SensorSample sample;
    sample.channel = channel;
    sample.value = 20.0 + channel;
    sample.timestamp = (long long)time(0);
    return sample;
}}

void device_driver_close(void) {{
    driver_ready = 0;
}}
""",
        )
    )
    files.append(
        _write(
            source_dir / "firmware" / "src" / "main.cpp",
            _cpp_runtime_main(task, blueprint),
        )
    )
    for module in blueprint.modules:
        files.append(_write(source_dir / "firmware" / "src" / f"{_snake(module.key)}_service.cpp", _generic_source_content(task, module, ".cpp")))
        files.append(_write(source_dir / "edge" / "services" / f"{_snake(module.key)}_worker.py", _python_edge_worker(task, module)))
    files.append(_write(source_dir / "scripts" / "device_smoke_test.py", _python_device_smoke(task, blueprint)))
    files.append(_write(source_dir / "scripts" / "start_edge_service.sh", _shell_start_script(task)))
    files.append(_write(source_dir / "config" / "device-profile.yml", _device_profile_yaml(task, blueprint)))
    files = _ensure_generic_line_target(files, source_dir / "edge" / "services", task, blueprint, target_lines=3200, extension=".py")
    files = _align_source_material_pages(files, source_dir, source_dir / "edge" / "services", ".py")
    return files


def _generate_system_service_project(task: GenerationTask, blueprint: ProductBlueprint, source_dir: Path) -> list[Path]:
    for folder in [source_dir / "system" / "src", source_dir / "system" / "include", source_dir / "admin_cli", source_dir / "scripts", source_dir / "config"]:
        folder.mkdir(parents=True, exist_ok=True)
    files = [_write(source_dir / "README.md", _readme(task, blueprint))]
    files.append(
        _write(
            source_dir / "system" / "include" / "service_registry.h",
            """#pragma once
typedef struct ServiceStatus {
    const char* name;
    const char* state;
    long long updated_at;
} ServiceStatus;
ServiceStatus registry_query(const char* service_name);
int registry_update(const char* service_name, const char* state);
""",
        )
    )
    files.append(
        _write(
            source_dir / "system" / "src" / "service_registry.c",
            f"""#include "../include/service_registry.h"
#include <time.h>

static const char* SOFTWARE_NAME = "{_c_literal(task.software_name)}";
static const char* current_state = "RUNNING";

ServiceStatus registry_query(const char* service_name) {{
    ServiceStatus status;
    status.name = service_name ? service_name : SOFTWARE_NAME;
    status.state = current_state;
    status.updated_at = (long long)time(0);
    return status;
}}

int registry_update(const char* service_name, const char* state) {{
    (void)service_name;
    current_state = state ? state : "UNKNOWN";
    return 1;
}}
""",
        )
    )
    files.append(_write(source_dir / "system" / "src" / "daemon_main.cpp", _cpp_runtime_main(task, blueprint)))
    for module in blueprint.modules:
        files.append(_write(source_dir / "system" / "src" / f"{_snake(module.key)}_manager.cpp", _generic_source_content(task, module, ".cpp")))
        files.append(_write(source_dir / "admin_cli" / f"{_snake(module.key)}_command.py", _python_edge_worker(task, module)))
    files.append(_write(source_dir / "scripts" / "install_service.sh", _shell_start_script(task)))
    files.append(_write(source_dir / "config" / "service-policy.yml", _device_profile_yaml(task, blueprint)))
    files = _ensure_generic_line_target(files, source_dir / "admin_cli", task, blueprint, target_lines=3200, extension=".py")
    files = _align_source_material_pages(files, source_dir, source_dir / "admin_cli", ".py")
    return files


def _generate_csharp_project(task: GenerationTask, blueprint: ProductBlueprint, source_dir: Path, include_readme: bool = True) -> list[Path]:
    root_namespace = _pascal(_ascii_token(task.software_name))
    src = source_dir / "src"
    for folder in [
        src / "Controllers",
        src / "Services",
        src / "Repositories",
        src / "Models",
        src / "Queries",
        src / "Common",
        src / "Configuration",
    ]:
        folder.mkdir(parents=True, exist_ok=True)

    files = [
        _write(
            source_dir / f"{root_namespace}.csproj",
            f"""<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <AssemblyName>{root_namespace}</AssemblyName>
    <RootNamespace>{root_namespace}</RootNamespace>
  </PropertyGroup>
</Project>
""",
        ),
        _write(
            src / "Program.cs",
            f"""using {root_namespace}.Configuration;
using {root_namespace}.Repositories;
using {root_namespace}.Services;

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddControllers();
builder.Services.AddSingleton(new SoftwareProfile(
    "{task.software_name}",
    "{task.version}",
    "{task.product_type}",
    "{blueprint.industry}"
));
{_csharp_service_registrations(blueprint)}
var app = builder.Build();
app.UseStaticFiles();
app.MapControllers();
app.MapGet("/health", () => Results.Ok(new {{
    Status = "ok",
    Software = "{task.software_name}",
    Version = "{task.version}"
}}));
app.MapGet("/", () => Results.Redirect("/ui-prototype/index.html"));
app.Run();
""",
        ),
    ]
    if include_readme:
        files.insert(0, _write(source_dir / "README.md", _readme(task, blueprint)))
    files.extend(_csharp_common_files(src, root_namespace, task, blueprint))
    for module in blueprint.modules:
        files.extend(_csharp_module_files(src, root_namespace, module))
    files.append(_write(src / "Services" / "OperationTraceService.cs", _csharp_operation_trace_service(root_namespace, task, blueprint)))
    files = _ensure_generic_line_target(files, src / "Services", task, blueprint, target_lines=3200, extension=".cs")
    files = _align_source_material_pages(files, source_dir, src / "Services", ".cs")
    return files


def _csharp_common_files(src: Path, namespace: str, task: GenerationTask, blueprint: ProductBlueprint) -> list[Path]:
    return [
        _write(
            src / "Common" / "ApiResult.cs",
            f"""namespace {namespace}.Common;

public class ApiResult<T>
{{
    public bool Success {{ get; set; }}
    public string Message {{ get; set; }} = string.Empty;
    public T? Data {{ get; set; }}

    public static ApiResult<T> Ok(T data)
    {{
        return new ApiResult<T> {{ Success = true, Message = "操作成功", Data = data }};
    }}

    public static ApiResult<T> Fail(string message)
    {{
        return new ApiResult<T> {{ Success = false, Message = message }};
    }}
}}
""",
        ),
        _write(
            src / "Common" / "PagedResult.cs",
            f"""namespace {namespace}.Common;

public class PagedResult<T>
{{
    public IReadOnlyList<T> Items {{ get; set; }} = Array.Empty<T>();
    public int PageNo {{ get; set; }}
    public int PageSize {{ get; set; }}
    public int TotalCount {{ get; set; }}

    public int TotalPages => PageSize <= 0 ? 0 : (int)Math.Ceiling(TotalCount / (double)PageSize);

    public static PagedResult<T> Create(IEnumerable<T> source, int pageNo, int pageSize)
    {{
        var safePageNo = Math.Max(1, pageNo);
        var safePageSize = Math.Max(1, pageSize);
        var list = source.ToList();
        return new PagedResult<T>
        {{
            Items = list.Skip((safePageNo - 1) * safePageSize).Take(safePageSize).ToList(),
            PageNo = safePageNo,
            PageSize = safePageSize,
            TotalCount = list.Count
        }};
    }}
}}
""",
        ),
        _write(
            src / "Configuration" / "SoftwareProfile.cs",
            f"""namespace {namespace}.Configuration;

public record SoftwareProfile(
    string SoftwareName,
    string Version,
    string ProductType,
    string Industry
)
{{
    public string Summary => $"{task.software_name} {task.version} / {task.product_type} / {blueprint.industry}";
}}
""",
        ),
    ]


def _csharp_module_files(src: Path, namespace: str, module: FeatureModule) -> list[Path]:
    class_name = _pascal(module.key)
    record_name = f"{class_name}Record"
    query_name = f"{class_name}Query"
    title = module.title
    description = module.description
    return [
        _write(src / "Models" / f"{record_name}.cs", _csharp_record(namespace, record_name, title, description)),
        _write(src / "Queries" / f"{query_name}.cs", _csharp_query(namespace, query_name, title)),
        _write(src / "Repositories" / f"I{class_name}Repository.cs", _csharp_repository_interface(namespace, class_name, record_name, query_name)),
        _write(src / "Repositories" / f"InMemory{class_name}Repository.cs", _csharp_repository(namespace, class_name, record_name, query_name)),
        _write(src / "Services" / f"{class_name}Validator.cs", _csharp_validator(namespace, class_name, record_name, title)),
        _write(src / "Services" / f"{class_name}Service.cs", _csharp_service(namespace, class_name, record_name, query_name, title)),
        _write(src / "Services" / f"{class_name}StatisticsService.cs", _csharp_statistics(namespace, class_name, record_name, title)),
        _write(src / "Services" / f"{class_name}AuditService.cs", _csharp_audit(namespace, class_name, record_name, title)),
        _write(src / "Services" / f"{class_name}ExportService.cs", _csharp_export(namespace, class_name, record_name, title)),
        _write(src / "Controllers" / f"{class_name}Controller.cs", _csharp_controller(namespace, class_name, record_name, query_name, title)),
    ]


def _csharp_service_registrations(blueprint: ProductBlueprint) -> str:
    lines: list[str] = []
    for module in blueprint.modules:
        class_name = _pascal(module.key)
        lines.extend(
            [
                f"builder.Services.AddSingleton<I{class_name}Repository, InMemory{class_name}Repository>();",
                f"builder.Services.AddSingleton<{class_name}Validator>();",
                f"builder.Services.AddSingleton<{class_name}Service>();",
            ]
        )
    return "\n".join(lines)


def _csharp_record(namespace: str, record_name: str, title: str, description: str) -> str:
    return f"""namespace {namespace}.Models;

public class {record_name}
{{
    public long Id {{ get; set; }}
    public string Code {{ get; set; }} = string.Empty;
    public string Name {{ get; set; }} = string.Empty;
    public string Status {{ get; set; }} = "Enabled";
    public string OwnerRole {{ get; set; }} = string.Empty;
    public string Description {{ get; set; }} = string.Empty;
    public int SortNo {{ get; set; }}
    public decimal Score {{ get; set; }}
    public bool Enabled {{ get; set; }} = true;
    public DateTime CreatedAt {{ get; set; }} = DateTime.Now;
    public DateTime UpdatedAt {{ get; set; }} = DateTime.Now;

    public string ModuleTitle => "{title}";
    public string ModuleDescription => "{description}";

    public void MarkUpdated(string operatorName)
    {{
        UpdatedAt = DateTime.Now;
        Description = string.IsNullOrWhiteSpace(Description)
            ? $"最后操作人：{{operatorName}}"
            : Description + $"；最后操作人：{{operatorName}}";
    }}

    public string BuildDisplayName()
    {{
        return $"{{Code}} - {{Name}} - {{Status}}";
    }}
}}
"""


def _csharp_query(namespace: str, query_name: str, title: str) -> str:
    return f"""namespace {namespace}.Queries;

public class {query_name}
{{
    public string? Keyword {{ get; set; }}
    public string? Status {{ get; set; }}
    public string? OwnerRole {{ get; set; }}
    public DateTime? StartTime {{ get; set; }}
    public DateTime? EndTime {{ get; set; }}
    public int PageNo {{ get; set; }} = 1;
    public int PageSize {{ get; set; }} = 20;

    public void Normalize()
    {{
        Keyword = Keyword?.Trim();
        Status = Status?.Trim();
        OwnerRole = OwnerRole?.Trim();
        PageNo = PageNo <= 0 ? 1 : PageNo;
        PageSize = PageSize <= 0 ? 20 : Math.Min(PageSize, 200);
        if (StartTime.HasValue && EndTime.HasValue && StartTime.Value > EndTime.Value)
        {{
            (StartTime, EndTime) = (EndTime, StartTime);
        }}
    }}

    public string BuildSummary()
    {{
        return $"{title} 查询条件：关键字={{Keyword ?? "全部"}}，状态={{Status ?? "全部"}}，页码={{PageNo}}";
    }}
}}
"""


def _csharp_repository_interface(namespace: str, class_name: str, record_name: str, query_name: str) -> str:
    return f"""using {namespace}.Models;
using {namespace}.Queries;

namespace {namespace}.Repositories;

public interface I{class_name}Repository
{{
    IReadOnlyList<{record_name}> Query({query_name} query);
    {record_name}? FindById(long id);
    {record_name} Save({record_name} record);
    bool Delete(long id);
    bool ExistsByCode(string code, long? excludeId = null);
}}
"""


def _csharp_repository(namespace: str, class_name: str, record_name: str, query_name: str) -> str:
    return f"""using {namespace}.Models;
using {namespace}.Queries;

namespace {namespace}.Repositories;

public class InMemory{class_name}Repository : I{class_name}Repository
{{
    private readonly List<{record_name}> _records = new();
    private long _nextId = 1;

    public IReadOnlyList<{record_name}> Query({query_name} query)
    {{
        query.Normalize();
        IEnumerable<{record_name}> result = _records;
        if (!string.IsNullOrWhiteSpace(query.Keyword))
        {{
            result = result.Where(item => item.Name.Contains(query.Keyword) || item.Code.Contains(query.Keyword));
        }}
        if (!string.IsNullOrWhiteSpace(query.Status))
        {{
            result = result.Where(item => item.Status.Equals(query.Status, StringComparison.OrdinalIgnoreCase));
        }}
        if (!string.IsNullOrWhiteSpace(query.OwnerRole))
        {{
            result = result.Where(item => item.OwnerRole.Equals(query.OwnerRole, StringComparison.OrdinalIgnoreCase));
        }}
        if (query.StartTime.HasValue)
        {{
            result = result.Where(item => item.UpdatedAt >= query.StartTime.Value);
        }}
        if (query.EndTime.HasValue)
        {{
            result = result.Where(item => item.UpdatedAt <= query.EndTime.Value);
        }}
        return result.OrderByDescending(item => item.UpdatedAt).ToList();
    }}

    public {record_name}? FindById(long id)
    {{
        return _records.FirstOrDefault(item => item.Id == id);
    }}

    public {record_name} Save({record_name} record)
    {{
        if (record.Id <= 0)
        {{
            record.Id = _nextId++;
            record.CreatedAt = DateTime.Now;
        }}
        _records.RemoveAll(item => item.Id == record.Id);
        record.UpdatedAt = DateTime.Now;
        _records.Add(record);
        return record;
    }}

    public bool Delete(long id)
    {{
        return _records.RemoveAll(item => item.Id == id) > 0;
    }}

    public bool ExistsByCode(string code, long? excludeId = null)
    {{
        return _records.Any(item => item.Code == code && (!excludeId.HasValue || item.Id != excludeId.Value));
    }}
}}
"""


def _csharp_validator(namespace: str, class_name: str, record_name: str, title: str) -> str:
    return f"""using {namespace}.Models;
using {namespace}.Repositories;

namespace {namespace}.Services;

public class {class_name}Validator
{{
    private readonly I{class_name}Repository _repository;

    public {class_name}Validator(I{class_name}Repository repository)
    {{
        _repository = repository;
    }}

    public IReadOnlyList<string> ValidateForCreate({record_name} record)
    {{
        var errors = ValidateBasicFields(record).ToList();
        if (_repository.ExistsByCode(record.Code))
        {{
            errors.Add("{title}编码已经存在");
        }}
        return errors;
    }}

    public IReadOnlyList<string> ValidateForUpdate(long id, {record_name} record)
    {{
        var errors = ValidateBasicFields(record).ToList();
        if (id <= 0)
        {{
            errors.Add("记录编号不合法");
        }}
        if (_repository.ExistsByCode(record.Code, id))
        {{
            errors.Add("{title}编码与其他记录重复");
        }}
        return errors;
    }}

    private IEnumerable<string> ValidateBasicFields({record_name} record)
    {{
        if (string.IsNullOrWhiteSpace(record.Code))
        {{
            yield return "业务编码不能为空";
        }}
        if (string.IsNullOrWhiteSpace(record.Name))
        {{
            yield return "业务名称不能为空";
        }}
        if (string.IsNullOrWhiteSpace(record.OwnerRole))
        {{
            yield return "负责角色不能为空";
        }}
        if (!IsSupportedStatus(record.Status))
        {{
            yield return "状态值不在允许范围内";
        }}
        if (record.Description.Length > 500)
        {{
            yield return "描述信息不能超过500个字符";
        }}
    }}

    public bool IsSupportedStatus(string status)
    {{
        var allowed = new[] {{ "Enabled", "Disabled", "Pending", "Archived", "Locked" }};
        return allowed.Contains(status, StringComparer.OrdinalIgnoreCase);
    }}
}}
"""


def _csharp_service(namespace: str, class_name: str, record_name: str, query_name: str, title: str) -> str:
    return f"""using {namespace}.Common;
using {namespace}.Models;
using {namespace}.Queries;
using {namespace}.Repositories;

namespace {namespace}.Services;

public class {class_name}Service
{{
    private readonly I{class_name}Repository _repository;
    private readonly {class_name}Validator _validator;
    private readonly {class_name}AuditService _auditService = new();

    public {class_name}Service(I{class_name}Repository repository, {class_name}Validator validator)
    {{
        _repository = repository;
        _validator = validator;
    }}

    public PagedResult<{record_name}> Query({query_name} query)
    {{
        var records = _repository.Query(query);
        return PagedResult<{record_name}>.Create(records, query.PageNo, query.PageSize);
    }}

    public ApiResult<{record_name}> Create({record_name} record, string operatorName)
    {{
        var errors = _validator.ValidateForCreate(record);
        if (errors.Count > 0)
        {{
            return ApiResult<{record_name}>.Fail(string.Join("；", errors));
        }}
        record.MarkUpdated(operatorName);
        var saved = _repository.Save(record);
        _auditService.RecordCreate(operatorName, saved);
        return ApiResult<{record_name}>.Ok(saved);
    }}

    public ApiResult<{record_name}> Update(long id, {record_name} request, string operatorName)
    {{
        var existing = _repository.FindById(id);
        if (existing == null)
        {{
            return ApiResult<{record_name}>.Fail("{title}记录不存在");
        }}
        var errors = _validator.ValidateForUpdate(id, request);
        if (errors.Count > 0)
        {{
            return ApiResult<{record_name}>.Fail(string.Join("；", errors));
        }}
        existing.Code = request.Code;
        existing.Name = request.Name;
        existing.Status = request.Status;
        existing.OwnerRole = request.OwnerRole;
        existing.Description = request.Description;
        existing.SortNo = request.SortNo;
        existing.Score = request.Score;
        existing.Enabled = request.Enabled;
        existing.MarkUpdated(operatorName);
        var saved = _repository.Save(existing);
        _auditService.RecordUpdate(operatorName, saved);
        return ApiResult<{record_name}>.Ok(saved);
    }}

    public ApiResult<bool> Delete(long id, string operatorName)
    {{
        var existing = _repository.FindById(id);
        if (existing == null)
        {{
            return ApiResult<bool>.Fail("{title}记录不存在");
        }}
        var deleted = _repository.Delete(id);
        _auditService.RecordDelete(operatorName, existing);
        return ApiResult<bool>.Ok(deleted);
    }}
}}
"""


def _csharp_statistics(namespace: str, class_name: str, record_name: str, title: str) -> str:
    return f"""using {namespace}.Models;

namespace {namespace}.Services;

public class {class_name}StatisticsService
{{
    public Dictionary<string, int> CountByStatus(IEnumerable<{record_name}> records)
    {{
        return records
            .GroupBy(item => string.IsNullOrWhiteSpace(item.Status) ? "Unknown" : item.Status)
            .ToDictionary(group => group.Key, group => group.Count());
    }}

    public Dictionary<string, object> BuildSummary(IEnumerable<{record_name}> records, DateTime date)
    {{
        var list = records.ToList();
        var status = CountByStatus(list);
        return new Dictionary<string, object>
        {{
            ["Module"] = "{title}",
            ["Date"] = date.ToString("yyyy-MM-dd"),
            ["TotalCount"] = list.Count,
            ["EnabledCount"] = status.GetValueOrDefault("Enabled"),
            ["PendingCount"] = status.GetValueOrDefault("Pending"),
            ["ArchivedCount"] = status.GetValueOrDefault("Archived"),
            ["AverageScore"] = list.Count == 0 ? 0 : list.Average(item => item.Score),
            ["RiskLevel"] = EvaluateRiskLevel(list)
        }};
    }}

    public string EvaluateRiskLevel(IEnumerable<{record_name}> records)
    {{
        var list = records.ToList();
        var disabled = list.Count(item => !item.Enabled || item.Status == "Disabled");
        var pending = list.Count(item => item.Status == "Pending");
        if (disabled > 10 || pending > 20)
        {{
            return "High";
        }}
        if (disabled > 3 || pending > 5)
        {{
            return "Medium";
        }}
        return "Low";
    }}
}}
"""


def _csharp_audit(namespace: str, class_name: str, record_name: str, title: str) -> str:
    return f"""using {namespace}.Models;

namespace {namespace}.Services;

public class {class_name}AuditService
{{
    private readonly List<string> _auditLines = new();

    public void RecordCreate(string operatorName, {record_name} record)
    {{
        Append(operatorName, "Create", record, "新增{title}记录");
    }}

    public void RecordUpdate(string operatorName, {record_name} record)
    {{
        Append(operatorName, "Update", record, "修改{title}记录");
    }}

    public void RecordDelete(string operatorName, {record_name} record)
    {{
        Append(operatorName, "Delete", record, "删除{title}记录");
    }}

    public void RecordExport(string operatorName, int count)
    {{
        _auditLines.Add($"{{DateTime.Now:yyyy-MM-dd HH:mm:ss}} | {{Normalize(operatorName)}} | Export | {title} | count={{count}}");
    }}

    public IReadOnlyList<string> ListRecent(int limit)
    {{
        var safeLimit = Math.Max(1, limit);
        return _auditLines.Skip(Math.Max(0, _auditLines.Count - safeLimit)).ToList();
    }}

    private void Append(string operatorName, string action, {record_name} record, string message)
    {{
        _auditLines.Add($"{{DateTime.Now:yyyy-MM-dd HH:mm:ss}} | {{Normalize(operatorName)}} | {{action}} | {{record.Code}} | {{message}}");
    }}

    private string Normalize(string value)
    {{
        return string.IsNullOrWhiteSpace(value) ? "system" : value.Trim();
    }}
}}
"""


def _csharp_export(namespace: str, class_name: str, record_name: str, title: str) -> str:
    return f"""using {namespace}.Models;

namespace {namespace}.Services;

public class {class_name}ExportService
{{
    public IReadOnlyList<string> ExportCsv(IEnumerable<{record_name}> records)
    {{
        var lines = new List<string>
        {{
            "Id,Code,Name,Status,OwnerRole,Score,UpdatedAt"
        }};
        foreach (var record in records)
        {{
            lines.Add(string.Join(",",
                record.Id,
                Escape(record.Code),
                Escape(record.Name),
                Escape(record.Status),
                Escape(record.OwnerRole),
                record.Score,
                record.UpdatedAt.ToString("yyyy-MM-dd HH:mm:ss")));
        }}
        return lines;
    }}

    public string BuildFileName(string operatorName)
    {{
        var safeOperator = string.IsNullOrWhiteSpace(operatorName) ? "system" : operatorName.Trim();
        return "{class_name.lower()}_" + safeOperator + "_" + DateTime.Now.ToString("yyyyMMddHHmmss") + ".csv";
    }}

    public string BuildExportRemark(int count)
    {{
        return "{title}导出完成，共 " + count + " 条记录。";
    }}

    private string Escape(string value)
    {{
        return string.IsNullOrWhiteSpace(value) ? string.Empty : value.Replace(",", "，").Replace("\\n", " ");
    }}
}}
"""


def _csharp_controller(namespace: str, class_name: str, record_name: str, query_name: str, title: str) -> str:
    route = _snake(class_name).replace("_", "-")
    return f"""using Microsoft.AspNetCore.Mvc;
using {namespace}.Common;
using {namespace}.Models;
using {namespace}.Queries;
using {namespace}.Services;

namespace {namespace}.Controllers;

[ApiController]
[Route("api/{route}")]
public class {class_name}Controller : ControllerBase
{{
    private readonly {class_name}Service _service;

    public {class_name}Controller({class_name}Service service)
    {{
        _service = service;
    }}

    [HttpGet]
    public ActionResult<PagedResult<{record_name}>> Query([FromQuery] {query_name} query)
    {{
        return _service.Query(query);
    }}

    [HttpPost]
    public ActionResult<ApiResult<{record_name}>> Create([FromBody] {record_name} record)
    {{
        return _service.Create(record, User.Identity?.Name ?? "system");
    }}

    [HttpPut("{{id:long}}")]
    public ActionResult<ApiResult<{record_name}>> Update(long id, [FromBody] {record_name} record)
    {{
        return _service.Update(id, record, User.Identity?.Name ?? "system");
    }}

    [HttpDelete("{{id:long}}")]
    public ActionResult<ApiResult<bool>> Delete(long id)
    {{
        return _service.Delete(id, User.Identity?.Name ?? "system");
    }}

    [HttpGet("module-title")]
    public ActionResult<string> ModuleTitle()
    {{
        return "{title}";
    }}
}}
"""


def _generic_source_content(task: GenerationTask, module: FeatureModule, extension: str) -> str:
    title = module.title
    if extension == ".html":
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{task.software_name} - {title}</title>
</head>
<body>
  <main id="{_snake(module.key)}">
    <h1>{title}</h1>
    <section class="query-panel">
      <input placeholder="请输入查询关键字">
      <button>查询</button>
      <button>新增</button>
    </section>
    <section class="data-table">
      <div>编码</div>
      <div>名称</div>
      <div>状态</div>
      <div>更新时间</div>
    </section>
  </main>
</body>
</html>
"""
    if extension == ".php":
        return f"""<?php
class {_pascal(module.key)}Service {{
    private array $records = [];

    public function listRecords(?string $keyword, ?string $status): array {{
        return array_values(array_filter($this->records, function ($record) use ($keyword, $status) {{
            $keywordMatched = $keyword === null || str_contains($record['name'], $keyword);
            $statusMatched = $status === null || $record['status'] === $status;
            return $keywordMatched && $statusMatched;
        }}));
    }}

    public function createRecord(array $payload): array {{
        $payload['id'] = count($this->records) + 1;
        $payload['status'] = $payload['status'] ?? 'ENABLED';
        $payload['module'] = '{title}';
        $this->records[] = $payload;
        return $payload;
    }}
}}
"""
    return "\n".join(
        [
            f"const char* softwareName = {_cpp_literal(task.software_name)};",
            f"const char* moduleTitle = {_cpp_literal(title)};",
            f"const char* moduleDescription = {_cpp_literal(module.description)};",
            f"class {_pascal(module.key)}Service {{",
            "public:",
            "    void createRecord();",
            "    void updateRecord();",
            "    void deleteRecord();",
            "    void queryRecord();",
            "};",
        ]
    )


def _cpp_runtime_main(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    modules = ", ".join(f'"{_cpp_escape(module.title)}"' for module in blueprint.modules[:8])
    return f"""#include <iostream>
#include <map>
#include <string>
#include <vector>

class RuntimeModuleRegistry {{
public:
    void registerModule(const std::string& name, const std::string& status) {{
        modules[name] = status;
    }}

    std::string statusOf(const std::string& name) const {{
        auto iter = modules.find(name);
        return iter == modules.end() ? "UNKNOWN" : iter->second;
    }}

    void printSummary() const {{
        for (const auto& item : modules) {{
            std::cout << item.first << ":" << item.second << std::endl;
        }}
    }}

private:
    std::map<std::string, std::string> modules;
}};

int main() {{
    RuntimeModuleRegistry registry;
    std::vector<std::string> moduleNames = {{{modules}}};
    for (const auto& name : moduleNames) {{
        registry.registerModule(name, "READY");
    }}
    std::cout << "{_cpp_escape(task.software_name)} {task.version}" << std::endl;
    registry.printSummary();
    return 0;
}}
"""


def _python_edge_worker(task: GenerationTask, module: FeatureModule) -> str:
    fields = ", ".join(repr(field) for field in module.data_fields[:8])
    operations = ", ".join(repr(operation) for operation in module.operations[:6])
    return f'''from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class {_pascal(module.key)}WorkerState:
    software_name: str = "{task.software_name}"
    module_title: str = "{module.title}"
    status: str = "READY"
    fields: list[str] = field(default_factory=lambda: [{fields}])
    operations: list[str] = field(default_factory=lambda: [{operations}])
    updated_at: datetime = field(default_factory=datetime.now)


class {_pascal(module.key)}Worker:
    def __init__(self):
        self.state = {_pascal(module.key)}WorkerState()
        self.records = []

    def collect(self, payload: dict) -> dict:
        record = dict(payload or {{}})
        record["module"] = self.state.module_title
        record["collected_at"] = datetime.now().isoformat()
        self.records.append(record)
        return record

    def validate(self, record: dict) -> list[str]:
        missing = [field for field in self.state.fields[:3] if not record.get(field)]
        return missing

    def submit(self, payload: dict) -> dict:
        record = self.collect(payload)
        record["missing_fields"] = self.validate(record)
        record["status"] = "INVALID" if record["missing_fields"] else "ACCEPTED"
        return record
'''


def _python_device_smoke(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    module_titles = ", ".join(repr(module.title) for module in blueprint.modules[:8])
    return f'''SOFTWARE_NAME = "{task.software_name}"
MODULES = [{module_titles}]


def run_smoke_test():
    results = []
    for index, title in enumerate(MODULES, start=1):
        results.append({{"index": index, "module": title, "status": "PASS"}})
    return results


if __name__ == "__main__":
    for item in run_smoke_test():
        print(f"{{SOFTWARE_NAME}}|{{item['index']}}|{{item['module']}}|{{item['status']}}")
'''


def _shell_start_script(task: GenerationTask) -> str:
    return f"""#!/usr/bin/env sh
set -eu
APP_NAME="{task.software_name}"
APP_VERSION="{task.version}"
echo "starting $APP_NAME $APP_VERSION"
python3 scripts/device_smoke_test.py 2>/dev/null || python3 admin_cli/*_command.py --help 2>/dev/null || true
"""


def _device_profile_yaml(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    modules = "\n".join(f"  - key: {_snake(module.key)}\n    title: {module.title}" for module in blueprint.modules[:8])
    return f"""software:
  name: {task.software_name}
  version: {task.version}
  category: {task.software_category}
  language: {task.language}
modules:
{modules}
runtime:
  support: {blueprint.runtime_environment.get('support', 'runtime support')}
"""


def _align_source_material_pages(files: list[Path], source_dir: Path, target_dir: Path, extension: str) -> list[Path]:
    current_lines = len(read_source_lines(source_dir))
    if current_lines < 3000:
        lines_needed = 3000 - current_lines
    else:
        remainder = current_lines % 50
        lines_needed = 50 - remainder if remainder else 0
    if lines_needed <= 0:
        return files
    path = _source_alignment_path(target_dir, extension)
    files.append(_write(path, _source_alignment_lines(lines_needed, extension, source_dir=source_dir, target_dir=target_dir)))
    return files


def _source_alignment_path(target_dir: Path, extension: str) -> Path:
    if extension in {".js", ".ts"}:
        return target_dir / "workflowTransitionSupport.js"
    if extension == ".py":
        return target_dir / "workflow_transition_support.py"
    if extension == ".java":
        return target_dir / "WorkflowTransitionSupport.java"
    if extension == ".cs":
        return target_dir / "WorkflowTransitionSupport.cs"
    return target_dir / "workflow-state-support.properties"


def _source_alignment_lines(lines_needed: int, extension: str, *, source_dir: Path, target_dir: Path) -> str:
    if extension == ".java":
        return _java_source_alignment_lines(lines_needed, source_dir=source_dir, target_dir=target_dir)
    if extension == ".cs":
        return _csharp_source_alignment_lines(lines_needed, source_dir=source_dir, target_dir=target_dir)
    if extension in {".js", ".ts"}:
        base = [
            "const workflowTransitionSupport = {};",
            "workflowTransitionSupport.visible = new Set([\"PENDING\", \"PROCESSING\", \"COMPLETED\"]);",
            "workflowTransitionSupport.closed = new Set([\"COMPLETED\", \"ARCHIVED\"]);",
            "workflowTransitionSupport.normalizeRecord = (record) => ({ ...(record || {}), status: String(record?.status || \"PENDING\").trim() });",
            "workflowTransitionSupport.canModify = (record) => !workflowTransitionSupport.closed.has(workflowTransitionSupport.normalizeRecord(record).status);",
            "workflowTransitionSupport.resolveNextStatus = (record) => workflowTransitionSupport.normalizeRecord(record).status === \"PENDING\" ? \"PROCESSING\" : \"COMPLETED\";",
            "workflowTransitionSupport.applyTransition = (record, operatorName) => ({ ...workflowTransitionSupport.normalizeRecord(record), operatorName: operatorName || \"system\", updatedAt: new Date() });",
            "workflowTransitionSupport.buildAuditLine = (record) => [record.code || \"-\", record.module || \"-\", record.operation || \"-\", record.status || \"PENDING\"].join(\"|\");",
            "workflowTransitionSupport.toQuery = (record) => ({ code: record?.code || \"\", status: record?.status || \"PENDING\", updatedAt: record?.updatedAt || new Date() });",
            "module.exports = workflowTransitionSupport;",
        ]
    elif extension == ".py":
        base = [
            "WORKFLOW_VISIBLE_STATES = {'PENDING', 'PROCESSING', 'COMPLETED'}",
            "WORKFLOW_CLOSED_STATES = {'COMPLETED', 'ARCHIVED'}",
            "def normalize_workflow_record(record): return {**dict(record or {}), 'status': str(dict(record or {}).get('status') or 'PENDING').strip() or 'PENDING'}",
            "def can_modify_workflow(record): return normalize_workflow_record(record)['status'] not in WORKFLOW_CLOSED_STATES",
            "def resolve_next_workflow_status(record): return 'PROCESSING' if normalize_workflow_record(record)['status'] == 'PENDING' else 'COMPLETED'",
            "def apply_workflow_transition(record, operator_name): return {**normalize_workflow_record(record), 'operator_name': operator_name or 'system'}",
            "def build_workflow_audit_line(record): return '|'.join(str(record.get(key, '-')) for key in ('code', 'module', 'operation', 'status'))",
        ]
    else:
        base = [
            "workflow.transition.visible.states=PENDING,PROCESSING,COMPLETED",
            "workflow.transition.closed.states=COMPLETED,ARCHIVED",
            "workflow.transition.default.operator=system",
            "workflow.transition.pending.next=PROCESSING",
            "workflow.transition.processing.next=COMPLETED",
            "workflow.transition.audit.format=code,module,operation,operator,status,updatedAt",
        ]
    rows = list(base[:lines_needed])
    index = 1
    while len(rows) < lines_needed:
        if extension in {".js", ".ts"}:
            rows.append(f"workflowTransitionSupport.transitionSnapshot{index:02d} = \"PENDING|PROCESSING|COMPLETED|ARCHIVED|BUSINESS-FLOW-{index:02d}\";")
        elif extension == ".py":
            rows.append(f"WORKFLOW_TRANSITION_SNAPSHOT_{index:02d} = 'PENDING|PROCESSING|COMPLETED|ARCHIVED|BUSINESS-FLOW-{index:02d}'")
        else:
            rows.append(f"workflow.transition.snapshot.{index:02d}=PENDING,PROCESSING,COMPLETED,ARCHIVED,BUSINESS-FLOW-{index:02d}")
        index += 1
    return "\n".join(rows)


def _java_source_alignment_lines(lines_needed: int, *, source_dir: Path, target_dir: Path) -> str:
    package = _java_package_for_directory(source_dir, target_dir)
    rows: list[str] = []
    if package and lines_needed >= 2:
        rows.append(f"package {package};")
    remaining = max(0, lines_needed - len(rows))
    if remaining <= 1:
        rows.append("public class WorkflowTransitionSupport {}")
        return "\n".join(rows[:lines_needed])
    rows.append("public class WorkflowTransitionSupport {")
    method_templates = [
        '    public String resolveNextStatus(String status) { return "PENDING".equals(status) ? "PROCESSING" : "PROCESSING".equals(status) ? "COMPLETED" : "ARCHIVED"; }',
        '    public boolean canModify(String status) { return !"COMPLETED".equals(status) && !"ARCHIVED".equals(status); }',
        '    public String normalizeOperator(String operator) { return operator == null || operator.isBlank() ? "system" : operator.trim(); }',
        '    public String buildAuditLine(String code, String module, String operation, String operator, String status) { return code + "|" + module + "|" + operation + "|" + operator + "|" + status; }',
    ]
    index = 1
    while len(rows) < lines_needed - 1:
        if index <= len(method_templates):
            rows.append(method_templates[index - 1])
        else:
            rows.append(f'    public String transitionSnapshot{index - len(method_templates):02d}() {{ return "PENDING|PROCESSING|COMPLETED|ARCHIVED|BUSINESS-FLOW-{index:02d}"; }}')
        index += 1
    rows.append("}")
    return "\n".join(rows[:lines_needed])


def _csharp_source_alignment_lines(lines_needed: int, *, source_dir: Path, target_dir: Path) -> str:
    namespace = _csharp_namespace_for_directory(source_dir, target_dir)
    rows: list[str] = []
    if namespace and lines_needed >= 3:
        rows.append(f"namespace {namespace};")
    remaining = max(0, lines_needed - len(rows))
    if remaining <= 1:
        rows.append("public class WorkflowTransitionSupport {}")
        return "\n".join(rows[:lines_needed])
    if remaining == 2:
        rows.extend(["public class WorkflowTransitionSupport", "{}"])
        return "\n".join(rows[:lines_needed])
    rows.extend(["public class WorkflowTransitionSupport", "{"])
    method_templates = [
        '    public string ResolveNextStatus(string? status) => status == "PENDING" ? "PROCESSING" : status == "PROCESSING" ? "COMPLETED" : "ARCHIVED";',
        '    public bool CanModify(string? status) => status != "COMPLETED" && status != "ARCHIVED";',
        '    public string NormalizeOperator(string? operatorName) => string.IsNullOrWhiteSpace(operatorName) ? "system" : operatorName.Trim();',
        '    public string BuildAuditLine(string code, string module, string operation, string operatorName, string status) => string.Join("|", code, module, operation, operatorName, status);',
    ]
    index = 1
    while len(rows) < lines_needed - 1:
        if index <= len(method_templates):
            rows.append(method_templates[index - 1])
        else:
            rows.append(f'    public string TransitionSnapshot{index - len(method_templates):02d}() => "PENDING|PROCESSING|COMPLETED|ARCHIVED|BUSINESS-FLOW-{index:02d}";')
        index += 1
    rows.append("}")
    return "\n".join(rows[:lines_needed])


def _java_package_for_directory(source_dir: Path, target_dir: Path) -> str:
    try:
        relative = target_dir.relative_to(source_dir).as_posix()
    except ValueError:
        return ""
    marker = "src/main/java/"
    if marker not in relative:
        return ""
    return relative.split(marker, 1)[1].replace("/", ".").strip(".")


def _csharp_namespace_for_directory(source_dir: Path, target_dir: Path) -> str:
    project = next(source_dir.glob("*.csproj"), None)
    if not project:
        return ""
    try:
        relative = target_dir.relative_to(source_dir / "src").as_posix()
    except ValueError:
        return project.stem
    suffix = relative.replace("/", ".").strip(".")
    return f"{project.stem}.{suffix}" if suffix else project.stem


def _ensure_line_target(
    files: list[Path],
    java_root: Path,
    task: GenerationTask,
    blueprint: ProductBlueprint,
    target_lines: int,
) -> list[Path]:
    total_lines = sum(_count_lines(path) for path in files)
    if total_lines >= target_lines:
        return files
    files.append(_write(java_root / "service" / "OperationTraceService.java", _operation_trace_service(task, blueprint)))
    return files


def _ensure_generic_line_target(
    files: list[Path],
    target_dir: Path,
    task: GenerationTask,
    blueprint: ProductBlueprint,
    target_lines: int,
    extension: str,
) -> list[Path]:
    total_lines = sum(_count_lines(path) for path in files)
    if total_lines >= target_lines:
        return files
    missing_lines = target_lines - total_lines
    if extension in {".cs", ".js", ".py"}:
        files.extend(
            _write_generic_workflow_shards(
                target_dir=target_dir,
                task=task,
                blueprint=blueprint,
                missing_lines=missing_lines,
                extension=extension,
            )
        )
    else:
        files.append(_write(target_dir / f"business_workflow{extension}", _generic_scenario_catalog(task, blueprint, missing_lines, extension)))
    return files


def _write_generic_workflow_shards(
    *,
    target_dir: Path,
    task: GenerationTask,
    blueprint: ProductBlueprint,
    missing_lines: int,
    extension: str,
) -> list[Path]:
    modules = list(blueprint.modules) or [FeatureModule("business", "业务模块", "业务处理", ["BusinessRecord"])]
    shard_count = max(len(modules), (max(1, missing_lines) + 379) // 380)
    shard_count = min(24, shard_count)
    target_per_shard = max(180, (max(1, missing_lines) + shard_count - 1) // shard_count)
    result: list[Path] = []
    for shard_index in range(shard_count):
        module = modules[shard_index % len(modules)]
        occurrence = shard_index // len(modules) + 1
        token = _snake(module.key) or f"business_{shard_index + 1:02d}"
        class_name = f"{_pascal(token)}WorkflowOrchestrator{occurrence if occurrence > 1 else ''}"
        index_offset = shard_index * 100
        if extension == ".py":
            file_name = f"{token}_workflow_orchestrator{f'_{occurrence}' if occurrence > 1 else ''}.py"
            content = _python_scenario_catalog(
                task,
                blueprint,
                target_per_shard,
                module_pool=[module],
                class_name=class_name,
                index_offset=index_offset,
                scenario_minimum=4,
                scenario_padding=1,
            )
        elif extension == ".js":
            file_name = f"{token}WorkflowOrchestrator{occurrence if occurrence > 1 else ''}.js"
            content = _javascript_scenario_catalog(
                task,
                blueprint,
                target_per_shard,
                module_pool=[module],
                class_name=class_name,
                index_offset=index_offset,
                scenario_minimum=4,
                scenario_padding=1,
            )
        else:
            file_name = f"{class_name}.cs"
            content = _csharp_scenario_catalog(
                task,
                blueprint,
                target_per_shard,
                module_pool=[module],
                class_name=class_name,
                index_offset=index_offset,
                scenario_minimum=4,
                scenario_padding=1,
            )
        result.append(_write(target_dir / file_name, content))
    return result


def _python_scenario_method_rows(
    index: int,
    module: FeatureModule,
    operation: str,
    field: str,
    method_name: str,
) -> list[str]:
    variant = index % 5
    if variant == 0:
        return [
            f"    def {method_name}(self, records: list[dict], keyword: str = '', status: str = '') -> list[dict]:",
            "        matched = []",
            "        for item in records:",
            "            current = self.normalize_record(item)",
            "            if keyword and keyword not in str(current.get('name', '')) and keyword not in current['code']:",
            "                continue",
            "            if status and current.get('status') != status:",
            "                continue",
            f"            current['matched_field'] = {_python_literal(field)}",
            "            matched.append(current)",
            "        return sorted(matched, key=lambda item: item.get('updated_at', ''), reverse=True)",
        ]
    if variant == 1:
        return [
            f"    def {method_name}(self, record: dict | None, decision: str, operator_name: str) -> dict:",
            "        current = self.normalize_record(record)",
            "        allowed = {'APPROVED', 'REJECTED', 'RETURNED'}",
            "        if decision not in allowed:",
            "            raise ValueError('复核结论不在允许范围内')",
            f"        current['module'] = {_python_literal(module.title)}",
            f"        current['operation'] = {_python_literal(operation)}",
            "        current['reviewed_by'] = self.normalize_operator(operator_name)",
            "        current['reviewed_at'] = datetime.now().isoformat(timespec='seconds')",
            "        current['status'] = 'COMPLETED' if decision == 'APPROVED' else 'PROCESSING'",
            "        self.append_audit_line({**current, 'operator': current['reviewed_by'], 'after_status': current['status']})",
            "        return self.build_response(current)",
        ]
    if variant == 2:
        return [
            f"    def {method_name}(self, records: list[dict]) -> dict:",
            "        summary: dict[str, int] = {}",
            "        overdue = []",
            "        for item in records:",
            "            status = str(item.get('status') or 'PENDING')",
            "            summary[status] = summary.get(status, 0) + 1",
            "            if item.get('overdue') and status not in {'COMPLETED', 'ARCHIVED'}:",
            "                overdue.append(item.get('code', '-'))",
            f"        return {{'module': {_python_literal(module.title)}, 'metric': {_python_literal(field)},",
            "                'total': len(records), 'status_summary': summary, 'overdue_codes': overdue}",
        ]
    if variant == 3:
        return [
            f"    def {method_name}(self, records: list[dict], operator_name: str) -> list[str]:",
            f"        rows = [{_python_literal('编号,模块,操作,状态,负责人,更新时间')}]",
            "        operator = self.normalize_operator(operator_name)",
            "        for item in records:",
            "            current = self.normalize_record(item)",
            f"            current['module'] = {_python_literal(module.title)}",
            f"            current['operation'] = {_python_literal(operation)}",
            "            values = [current['code'], current['module'], current['operation'],",
            "                      str(current.get('status', 'PENDING')), operator, str(current.get('updated_at', ''))]",
            "            rows.append(','.join(value.replace(',', '，') for value in values))",
            "        return rows",
        ]
    return [
        f"    def {method_name}(self, record: dict | None, operator_name: str) -> dict:",
        "        current = self.normalize_record(record)",
        f"        current['module'] = {_python_literal(module.title)}",
        f"        current['operation'] = {_python_literal(operation)}",
        f"        current['focus_field'] = {_python_literal(field)}",
        "        current['operator'] = self.normalize_operator(operator_name)",
        "        current['before_status'] = current.get('status', 'PENDING')",
        "        current['after_status'] = self.next_status(current['before_status'])",
        "        current['updated_at'] = datetime.now().isoformat(timespec='seconds')",
        "        self.validate_record(current)",
        "        self.append_audit_line(current)",
        "        return self.build_response(current)",
    ]


def _javascript_scenario_method_rows(
    index: int,
    module: FeatureModule,
    operation: str,
    field: str,
    method_name: str,
) -> list[str]:
    variant = index % 5
    if variant == 0:
        return [
            f"  {method_name}(records, keyword = '', status = '') {{",
            "    return (records || []).map((item) => this.normalizeRecord(item)).filter((item) => {",
            "      const keywordMatched = !keyword || String(item.name || '').includes(keyword) || item.code.includes(keyword);",
            "      const statusMatched = !status || item.status === status;",
            "      return keywordMatched && statusMatched;",
            "    }).sort((left, right) => String(right.updatedAt || '').localeCompare(String(left.updatedAt || '')));",
            "  }",
        ]
    if variant == 1:
        return [
            f"  {method_name}(record, decision, operatorName) {{",
            "    const allowed = new Set(['APPROVED', 'REJECTED', 'RETURNED']);",
            "    if (!allowed.has(decision)) throw new Error('复核结论不在允许范围内');",
            "    const current = this.normalizeRecord(record);",
            f"    current.module = {_json_literal(module.title)};",
            f"    current.operation = {_json_literal(operation)};",
            "    current.reviewedBy = this.normalizeOperator(operatorName);",
            "    current.reviewedAt = new Date();",
            "    current.afterStatus = decision === 'APPROVED' ? 'COMPLETED' : 'PROCESSING';",
            "    this.applyStatus(current, current.afterStatus);",
            "    this.appendAuditLine(current);",
            "    return this.buildResponse(current);",
            "  }",
        ]
    if variant == 2:
        return [
            f"  {method_name}(records) {{",
            "    const statusSummary = {};",
            "    const overdueCodes = [];",
            "    for (const item of records || []) {",
            "      const status = String(item.status || 'PENDING');",
            "      statusSummary[status] = (statusSummary[status] || 0) + 1;",
            "      if (item.overdue && !['COMPLETED', 'ARCHIVED'].includes(status)) overdueCodes.push(item.code || '-');",
            "    }",
            f"    return {{ module: {_json_literal(module.title)}, metric: {_json_literal(field)}, total: (records || []).length, statusSummary, overdueCodes }};",
            "  }",
        ]
    if variant == 3:
        return [
            f"  {method_name}(records, operatorName) {{",
            "    const operator = this.normalizeOperator(operatorName);",
            "    const rows = ['编号,模块,操作,状态,负责人,更新时间'];",
            "    for (const item of records || []) {",
            "      const current = this.normalizeRecord(item);",
            f"      const values = [current.code, {_json_literal(module.title)}, {_json_literal(operation)}, current.status || 'PENDING', operator, current.updatedAt || ''];",
            "      rows.push(values.map((value) => String(value).replaceAll(',', '，')).join(','));",
            "    }",
            "    return rows;",
            "  }",
        ]
    return [
        f"  {method_name}(record, operatorName) {{",
        "    const current = this.normalizeRecord(record);",
        f"    current.module = {_json_literal(module.title)};",
        f"    current.operation = {_json_literal(operation)};",
        f"    current.focusField = {_json_literal(field)};",
        "    current.operatorName = this.normalizeOperator(operatorName);",
        "    current.beforeStatus = current.status || \"PENDING\";",
        "    current.afterStatus = this.nextStatus(current.beforeStatus);",
        "    current.updatedAt = new Date();",
        "    this.validateRecord(current);",
        "    this.applyStatus(current, current.afterStatus);",
        "    this.appendAuditLine(current);",
        "    return this.buildResponse(current);",
        "  }",
    ]


def _javascript_scenario_catalog(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    missing_lines: int,
    *,
    module_pool: list[FeatureModule] | None = None,
    class_name: str = "BusinessWorkflowEngine",
    index_offset: int = 0,
    scenario_minimum: int = 96,
    scenario_padding: int = 16,
) -> str:
    rows: list[str] = [
        f"class {class_name} {{",
        "  constructor() {",
        "    this.auditLines = [];",
        "    this.statusFlow = [\"PENDING\", \"PROCESSING\", \"COMPLETED\", \"ARCHIVED\"];",
        "    this.defaultOwner = \"system\";",
        "  }",
    ]
    for index, module in _scenario_modules(
        blueprint,
        missing_lines,
        lines_per_item=12,
        module_pool=module_pool,
        index_offset=index_offset,
        minimum_count=scenario_minimum,
        padding=scenario_padding,
    ):
        operation = module.operations[(index - 1) % len(module.operations)] if module.operations else f"{module.title}处理"
        field = module.data_fields[(index - 1) % len(module.data_fields)] if module.data_fields else "业务状态"
        method_name = f"handle{_pascal(module.key)}{_pascal(_operation_token(operation))}{index:04d}"
        rows.extend(_javascript_scenario_method_rows(index, module, operation, field, method_name))
    rows.extend(
        [
            "  normalizeRecord(record) {",
            "    const safeRecord = record || {};",
            "    return { ...safeRecord, code: safeRecord.code || this.createBusinessCode() };",
            "  }",
            "  normalizeOperator(operatorName) {",
            "    return operatorName && operatorName.trim() ? operatorName.trim() : this.defaultOwner;",
            "  }",
            "  validateRecord(record) {",
            "    if (!record.code || !record.module || !record.operation) {",
            "      throw new Error(\"业务记录缺少必要字段\");",
            "    }",
            "    if (String(record.description || \"\").length > 500) {",
            "      throw new Error(\"描述信息不能超过500个字符\");",
            "    }",
            "  }",
            "  applyStatus(record, status) {",
            "    record.status = status;",
            "    record.statusText = this.statusText(status);",
            "    record.closed = status === \"ARCHIVED\";",
            "  }",
            "  nextStatus(status) {",
            "    const index = this.statusFlow.indexOf(status);",
            "    return this.statusFlow[Math.min(index + 1, this.statusFlow.length - 1)] || \"PROCESSING\";",
            "  }",
            "  statusText(status) {",
            "    const labels = { PENDING: \"待处理\", PROCESSING: \"处理中\", COMPLETED: \"已完成\", ARCHIVED: \"已归档\" };",
            "    return labels[status] || \"处理中\";",
            "  }",
            "  appendAuditLine(record) {",
            "    const line = [record.code, record.module, record.operation, record.operatorName, record.afterStatus].join(\"|\");",
            "    this.auditLines.push(line);",
            "  }",
            "  buildResponse(record) {",
            "    return { success: true, data: record, auditCount: this.auditLines.length };",
            "  }",
            "  createBusinessCode() {",
            "    return `BUS-${String(this.auditLines.length + 1).padStart(6, \"0\")}`;",
            "  }",
            "  exportAuditLines() {",
            "    return this.auditLines.slice();",
            "  }",
            "}",
            f"module.exports = new {class_name}();",
        ]
    )
    return "\n".join(rows)


def _python_scenario_catalog(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    missing_lines: int,
    *,
    module_pool: list[FeatureModule] | None = None,
    class_name: str = "BusinessWorkflowService",
    index_offset: int = 0,
    scenario_minimum: int = 96,
    scenario_padding: int = 16,
) -> str:
    rows: list[str] = [
        "from datetime import datetime",
        f"class {class_name}:",
        "    def __init__(self):",
        "        self.audit_lines = []",
        "        self.status_flow = ['PENDING', 'PROCESSING', 'COMPLETED', 'ARCHIVED']",
        "        self.default_owner = 'system'",
    ]
    for index, module in _scenario_modules(
        blueprint,
        missing_lines,
        lines_per_item=12,
        module_pool=module_pool,
        index_offset=index_offset,
        minimum_count=scenario_minimum,
        padding=scenario_padding,
    ):
        operation = module.operations[(index - 1) % len(module.operations)] if module.operations else f"{module.title}处理"
        field = module.data_fields[(index - 1) % len(module.data_fields)] if module.data_fields else "业务状态"
        method_name = f"handle_{_snake(module.key)}_{_snake(_operation_token(operation))}_{index:04d}"
        rows.extend(_python_scenario_method_rows(index, module, operation, field, method_name))
    rows.extend(
        [
            "    def normalize_record(self, record: dict | None) -> dict:",
            "        current = dict(record or {})",
            "        current['code'] = current.get('code') or self.create_business_code()",
            "        return current",
            "    def normalize_operator(self, operator_name: str) -> str:",
            "        return operator_name.strip() if operator_name and operator_name.strip() else self.default_owner",
            "    def validate_record(self, record: dict) -> None:",
            "        if not record.get('code') or not record.get('module') or not record.get('operation'):",
            "            raise ValueError('业务记录缺少必要字段')",
            "        if len(str(record.get('description', ''))) > 500:",
            "            raise ValueError('描述信息不能超过500个字符')",
            "    def next_status(self, status: str) -> str:",
            "        try:",
            "            index = self.status_flow.index(status)",
            "        except ValueError:",
            "            return 'PROCESSING'",
            "        return self.status_flow[min(index + 1, len(self.status_flow) - 1)]",
            "    def append_audit_line(self, record: dict) -> None:",
            "        line = '|'.join([record['code'], record['module'], record['operation'], record['operator'], record['after_status']])",
            "        self.audit_lines.append(line)",
            "    def build_response(self, record: dict) -> dict:",
            "        return {'success': True, 'data': record, 'audit_count': len(self.audit_lines)}",
            "    def create_business_code(self) -> str:",
            "        return f\"BUS-{len(self.audit_lines) + 1:06d}\"",
            f"workflow_service = {class_name}()",
        ]
    )
    return "\n".join(rows)


def _generic_scenario_catalog(task: GenerationTask, blueprint: ProductBlueprint, missing_lines: int, extension: str) -> str:
    if extension == ".php":
        return _php_scenario_catalog(task, blueprint, missing_lines)
    if extension in {".cpp", ".h", ".hpp"}:
        return _cpp_scenario_catalog(task, blueprint, missing_lines)
    if extension == ".html":
        return _html_scenario_catalog(task, blueprint, missing_lines)
    rows = []
    for index, module in _scenario_modules(blueprint, missing_lines, lines_per_item=5):
        operation = module.operations[(index - 1) % len(module.operations)] if module.operations else f"{module.title}处理"
        field = module.data_fields[(index - 1) % len(module.data_fields)] if module.data_fields else "业务状态"
        rows.extend(
            [
                f"workflow.record.{index:04d}.code={_snake(module.key).upper()}_{index:04d}",
                f"workflow.record.{index:04d}.module={module.title}",
                f"workflow.record.{index:04d}.operation={operation}",
                f"workflow.record.{index:04d}.field={field}",
                f"workflow.record.{index:04d}.state=PENDING,PROCESSING,COMPLETED,ARCHIVED",
            ]
        )
    return "\n".join(rows)


def _php_scenario_catalog(task: GenerationTask, blueprint: ProductBlueprint, missing_lines: int) -> str:
    rows = [
        "<?php",
        "class BusinessWorkflowService {",
        "    private array $auditLines = [];",
        "    private array $statusFlow = ['PENDING', 'PROCESSING', 'COMPLETED', 'ARCHIVED'];",
        "    private string $defaultOwner = 'system';",
    ]
    for index, module in _scenario_modules(blueprint, missing_lines, lines_per_item=12):
        operation = module.operations[(index - 1) % len(module.operations)] if module.operations else f"{module.title}处理"
        field = module.data_fields[(index - 1) % len(module.data_fields)] if module.data_fields else "业务状态"
        method_name = f"handle{_pascal(module.key)}{_pascal(_operation_token(operation))}{index:04d}"
        rows.extend(
            [
                f"    public function {method_name}(?array $record, string $operatorName): array {{",
                "        $current = $this->normalizeRecord($record);",
                f"        $current['module'] = {_php_literal(module.title)};",
                f"        $current['operation'] = {_php_literal(operation)};",
                f"        $current['focusField'] = {_php_literal(field)};",
                "        $current['operator'] = $this->normalizeOperator($operatorName);",
                "        $current['beforeStatus'] = $current['status'] ?? 'PENDING';",
                "        $current['afterStatus'] = $this->nextStatus($current['beforeStatus']);",
                "        $current['updatedAt'] = date('Y-m-d H:i:s');",
                "        $this->validateRecord($current);",
                "        $this->appendAuditLine($current);",
                "        return $this->buildResponse($current);",
                "    }",
            ]
        )
    rows.extend(
        [
            "    private function normalizeRecord(?array $record): array {",
            "        $current = $record ?? [];",
            "        $current['code'] = $current['code'] ?? $this->createBusinessCode();",
            "        return $current;",
            "    }",
            "    private function normalizeOperator(string $operatorName): string {",
            "        $safeOperator = trim($operatorName);",
            "        return $safeOperator === '' ? $this->defaultOwner : $safeOperator;",
            "    }",
            "    private function validateRecord(array $record): void {",
            "        if (empty($record['code']) || empty($record['module']) || empty($record['operation'])) {",
            "            throw new RuntimeException('业务记录缺少必要字段');",
            "        }",
            "        if (mb_strlen((string)($record['description'] ?? '')) > 500) {",
            "            throw new RuntimeException('描述信息不能超过500个字符');",
            "        }",
            "    }",
            "    private function nextStatus(string $status): string {",
            "        $index = array_search($status, $this->statusFlow, true);",
            "        return $index === false ? 'PROCESSING' : $this->statusFlow[min($index + 1, count($this->statusFlow) - 1)];",
            "    }",
            "    private function appendAuditLine(array $record): void {",
            "        $this->auditLines[] = implode('|', [$record['code'], $record['module'], $record['operation'], $record['operator'], $record['afterStatus']]);",
            "    }",
            "    private function buildResponse(array $record): array {",
            "        return ['success' => true, 'data' => $record, 'auditCount' => count($this->auditLines)];",
            "    }",
            "    private function createBusinessCode(): string {",
            "        return 'BUS-' . str_pad((string)(count($this->auditLines) + 1), 6, '0', STR_PAD_LEFT);",
            "    }",
            "}",
        ]
    )
    return "\n".join(rows)


def _cpp_scenario_catalog(task: GenerationTask, blueprint: ProductBlueprint, missing_lines: int) -> str:
    rows = [
        "#include <algorithm>",
        "#include <map>",
        "#include <stdexcept>",
        "#include <string>",
        "#include <vector>",
        "class BusinessWorkflowService {",
        "public:",
        "    BusinessWorkflowService() {",
        "        statusFlow = {\"PENDING\", \"PROCESSING\", \"COMPLETED\", \"ARCHIVED\"};",
        "    }",
    ]
    for index, module in _scenario_modules(blueprint, missing_lines, lines_per_item=12):
        operation = module.operations[(index - 1) % len(module.operations)] if module.operations else f"{module.title}处理"
        field = module.data_fields[(index - 1) % len(module.data_fields)] if module.data_fields else "业务状态"
        method_name = f"handle{_pascal(module.key)}{_pascal(_operation_token(operation))}{index:04d}"
        rows.extend(
            [
                f"    std::map<std::string, std::string> {method_name}(const std::map<std::string, std::string>& record, const std::string& operatorName) {{",
                "        auto current = normalizeRecord(record);",
                f"        current[\"module\"] = {_cpp_literal(module.title)};",
                f"        current[\"operation\"] = {_cpp_literal(operation)};",
                f"        current[\"focusField\"] = {_cpp_literal(field)};",
                "        current[\"operator\"] = normalizeOperator(operatorName);",
                "        current[\"beforeStatus\"] = current.count(\"status\") ? current[\"status\"] : \"PENDING\";",
                "        current[\"afterStatus\"] = nextStatus(current[\"beforeStatus\"]);",
                "        current[\"updatedAt\"] = \"2026-06-08 10:30:00\";",
                "        validateRecord(current);",
                "        appendAuditLine(current);",
                "        return current;",
                "    }",
            ]
        )
    rows.extend(
        [
            "private:",
            "    std::vector<std::string> auditLines;",
            "    std::vector<std::string> statusFlow;",
            "    std::map<std::string, std::string> normalizeRecord(std::map<std::string, std::string> record) {",
            "        if (!record.count(\"code\")) record[\"code\"] = createBusinessCode();",
            "        return record;",
            "    }",
            "    std::string normalizeOperator(const std::string& operatorName) {",
            "        return operatorName.empty() ? \"system\" : operatorName;",
            "    }",
            "    void validateRecord(const std::map<std::string, std::string>& record) {",
            "        if (!record.count(\"code\") || !record.count(\"module\") || !record.count(\"operation\")) throw std::runtime_error(\"业务记录缺少必要字段\");",
            "    }",
            "    std::string nextStatus(const std::string& status) {",
            "        for (size_t index = 0; index < statusFlow.size(); ++index) if (statusFlow[index] == status) return statusFlow[std::min(index + 1, statusFlow.size() - 1)];",
            "        return \"PROCESSING\";",
            "    }",
            "    void appendAuditLine(const std::map<std::string, std::string>& record) {",
            "        auditLines.push_back(record.at(\"code\") + \"|\" + record.at(\"module\") + \"|\" + record.at(\"operation\") + \"|\" + record.at(\"operator\") + \"|\" + record.at(\"afterStatus\"));",
            "    }",
            "    std::string createBusinessCode() {",
            "        return \"BUS-\" + std::to_string(auditLines.size() + 1);",
            "    }",
            "};",
        ]
    )
    return "\n".join(rows)


def _html_scenario_catalog(task: GenerationTask, blueprint: ProductBlueprint, missing_lines: int) -> str:
    rows = [
        "<!doctype html>",
        "<html>",
        "<head>",
        f"  <title>{task.software_name}业务场景目录</title>",
        "</head>",
        "<body>",
        "  <main>",
    ]
    for index, module in _scenario_modules(blueprint, missing_lines, lines_per_item=6):
        rows.extend(
            [
                f"    <section data-code=\"{_snake(module.key).upper()}_{index:04d}\">",
                f"      <h2>{module.title}工作台</h2>",
                f"      <p>{module.description}</p>",
                f"      <p>{module.title}页面提供查询、维护、处理、审核、统计和追踪等业务入口。</p>",
                f"      <p>{module.title}处理结果写入操作日志并进入统计分析。</p>",
                "    </section>",
            ]
        )
    rows.extend(["  </main>", "</body>", "</html>"])
    return "\n".join(rows)


def _scenario_modules(
    blueprint: ProductBlueprint,
    missing_lines: int,
    lines_per_item: int,
    *,
    module_pool: list[FeatureModule] | None = None,
    index_offset: int = 0,
    minimum_count: int = 96,
    padding: int = 16,
) -> list[tuple[int, FeatureModule]]:
    modules = module_pool or blueprint.modules or [FeatureModule("business", "业务模块", "业务处理", ["BusinessRecord"])]
    item_size = max(1, lines_per_item)
    required = (max(0, missing_lines) + item_size - 1) // item_size
    scenario_count = max(max(1, minimum_count), required + max(0, padding))
    return [
        (index_offset + position, modules[(position - 1) % len(modules)])
        for position in range(1, scenario_count + 1)
    ]


def _operation_token(value: str) -> str:
    for suffix in ["登记", "查询", "编辑", "审核", "发布", "归档", "导入", "导出", "预警", "复核", "统计", "追踪", "新增", "删除", "详情"]:
        if suffix in value:
            return suffix
    return value or "处理"


def _json_literal(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _json_value_literal(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_block_literal(value, *, indent: int = 2) -> str:
    return json.dumps(value, ensure_ascii=False, indent=indent)


def _python_literal(value: str) -> str:
    return repr(str(value))


def _php_literal(value: str) -> str:
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def _cpp_literal(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _cpp_escape(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _c_literal(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _csharp_operation_trace_service(namespace: str, task: GenerationTask, blueprint: ProductBlueprint) -> str:
    module_titles = ", ".join(module.title for module in blueprint.modules)
    return f"""namespace {namespace}.Services;

public class OperationTraceService
{{
    private readonly List<Dictionary<string, object>> _traces = new();

    public Dictionary<string, object> BeginTrace(string module, string action, string operatorName)
    {{
        var trace = new Dictionary<string, object>
        {{
            ["SoftwareName"] = "{task.software_name}",
            ["Version"] = "{task.version}",
            ["AvailableModules"] = "{module_titles}",
            ["Module"] = Normalize(module),
            ["Action"] = Normalize(action),
            ["Operator"] = Normalize(operatorName),
            ["Status"] = "Started",
            ["CreatedAt"] = DateTime.Now,
            ["UpdatedAt"] = DateTime.Now
        }};
        _traces.Add(trace);
        return trace;
    }}

    public void AppendBusinessMessage(Dictionary<string, object> trace, string message)
    {{
        if (!trace.TryGetValue("Messages", out var value) || value is not List<string> messages)
        {{
            messages = new List<string>();
            trace["Messages"] = messages;
        }}
        messages.Add($"{{DateTime.Now:yyyy-MM-dd HH:mm:ss}} | {{Normalize(message)}}");
        trace["UpdatedAt"] = DateTime.Now;
    }}

    public void MarkSuccess(Dictionary<string, object> trace, string message)
    {{
        Mark(trace, "Success", message);
    }}

    public void MarkFailure(Dictionary<string, object> trace, string message)
    {{
        Mark(trace, "Failure", message);
    }}

    public IReadOnlyList<Dictionary<string, object>> ListByModule(string module)
    {{
        var safeModule = Normalize(module);
        return _traces
            .Where(item => item.TryGetValue("Module", out var value) && Equals(value, safeModule))
            .Select(item => new Dictionary<string, object>(item))
            .ToList();
    }}

    public IReadOnlyList<string> ExportTraceLines()
    {{
        var lines = new List<string> {{ "Software,Module,Action,Operator,Status,CreatedAt,UpdatedAt" }};
        foreach (var trace in _traces)
        {{
            lines.Add(string.Join(",",
                Escape(trace.GetValueOrDefault("SoftwareName")),
                Escape(trace.GetValueOrDefault("Module")),
                Escape(trace.GetValueOrDefault("Action")),
                Escape(trace.GetValueOrDefault("Operator")),
                Escape(trace.GetValueOrDefault("Status")),
                Escape(trace.GetValueOrDefault("CreatedAt")),
                Escape(trace.GetValueOrDefault("UpdatedAt"))));
        }}
        return lines;
    }}

    private void Mark(Dictionary<string, object> trace, string status, string message)
    {{
        trace["Status"] = status;
        trace["ResultMessage"] = Normalize(message);
        trace["UpdatedAt"] = DateTime.Now;
        AppendBusinessMessage(trace, message);
    }}

    private string Normalize(string? value)
    {{
        return string.IsNullOrWhiteSpace(value) ? "-" : value.Trim().Replace(",", "，");
    }}

    private string Escape(object? value)
    {{
        return value == null ? string.Empty : Convert.ToString(value)?.Replace(",", "，").Replace("\\n", " ") ?? string.Empty;
    }}
}}
"""


def _csharp_scenario_catalog(
    task: GenerationTask,
    blueprint: ProductBlueprint,
    missing_lines: int,
    *,
    module_pool: list[FeatureModule] | None = None,
    class_name: str = "BusinessWorkflowService",
    index_offset: int = 0,
    scenario_minimum: int = 96,
    scenario_padding: int = 16,
) -> str:
    rows: list[str] = [
        "using System;",
        "using System.Collections.Generic;",
        "",
        f"namespace {_pascal(_ascii_token(task.software_name))}.Services;",
        "",
        f"public class {class_name}",
        "{",
        "    private readonly List<string> _auditLines = new();",
        "    private readonly List<string> _statusFlow = new() { \"PENDING\", \"PROCESSING\", \"COMPLETED\", \"ARCHIVED\" };",
        "    private const string DefaultOwner = \"system\";",
    ]
    for index, module in _scenario_modules(
        blueprint,
        missing_lines,
        lines_per_item=12,
        module_pool=module_pool,
        index_offset=index_offset,
        minimum_count=scenario_minimum,
        padding=scenario_padding,
    ):
        operation = module.operations[(index - 1) % len(module.operations)] if module.operations else f"{module.title}处理"
        field = module.data_fields[(index - 1) % len(module.data_fields)] if module.data_fields else "业务状态"
        method_name = f"Handle{_pascal(module.key)}{_pascal(_operation_token(operation))}{index:0000}"
        rows.extend(
            [
                f"    public Dictionary<string, object> {method_name}(Dictionary<string, object>? record, string operatorName)",
                "    {",
                "        var current = NormalizeRecord(record);",
                f"        current[\"Module\"] = \"{module.title}\";",
                f"        current[\"Operation\"] = \"{operation}\";",
                f"        current[\"FocusField\"] = \"{field}\";",
                "        current[\"Operator\"] = NormalizeOperator(operatorName);",
                "        current[\"BeforeStatus\"] = current.GetValueOrDefault(\"Status\") ?? \"PENDING\";",
                "        current[\"AfterStatus\"] = NextStatus(Convert.ToString(current[\"BeforeStatus\"]) ?? \"PENDING\");",
                "        current[\"UpdatedAt\"] = DateTime.Now;",
                "        ValidateRecord(current);",
                "        AppendAuditLine(current);",
                "        return BuildResponse(current);",
                "    }",
            ]
        )
    rows.extend(
        [
            "    private Dictionary<string, object> NormalizeRecord(Dictionary<string, object>? record)",
            "    {",
            "        var current = record == null ? new Dictionary<string, object>() : new Dictionary<string, object>(record);",
            "        if (!current.ContainsKey(\"Code\") || string.IsNullOrWhiteSpace(Convert.ToString(current[\"Code\"]))) current[\"Code\"] = CreateBusinessCode();",
            "        return current;",
            "    }",
            "    private string NormalizeOperator(string operatorName)",
            "    {",
            "        return string.IsNullOrWhiteSpace(operatorName) ? DefaultOwner : operatorName.Trim();",
            "    }",
            "    private void ValidateRecord(Dictionary<string, object> record)",
            "    {",
            "        if (!record.ContainsKey(\"Code\") || !record.ContainsKey(\"Module\") || !record.ContainsKey(\"Operation\")) throw new InvalidOperationException(\"业务记录缺少必要字段\");",
            "        if ((Convert.ToString(record.GetValueOrDefault(\"Description\")) ?? string.Empty).Length > 500) throw new InvalidOperationException(\"描述信息不能超过500个字符\");",
            "    }",
            "    private string NextStatus(string status)",
            "    {",
            "        var index = _statusFlow.IndexOf(status);",
            "        return index < 0 ? \"PROCESSING\" : _statusFlow[Math.Min(index + 1, _statusFlow.Count - 1)];",
            "    }",
            "    private void AppendAuditLine(Dictionary<string, object> record)",
            "    {",
            "        _auditLines.Add(string.Join(\"|\", record[\"Code\"], record[\"Module\"], record[\"Operation\"], record[\"Operator\"], record[\"AfterStatus\"]));",
            "    }",
            "    private Dictionary<string, object> BuildResponse(Dictionary<string, object> record)",
            "    {",
            "        return new Dictionary<string, object> { [\"Success\"] = true, [\"Data\"] = record, [\"AuditCount\"] = _auditLines.Count };",
            "    }",
            "    private string CreateBusinessCode()",
            "    {",
            "        return $\"BUS-{_auditLines.Count + 1:000000}\";",
            "    }",
            "}",
        ]
    )
    return "\n".join(rows)


def _operation_trace_service(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    package = f"com.copyright.{_package_token(task.software_name)}"
    module_titles = ", ".join(module.title for module in blueprint.modules)
    return f"""package {package}.service;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class OperationTraceService {{
    private final List<Map<String, Object>> traces = new ArrayList<>();

    public Map<String, Object> beginTrace(String module, String action, String operator) {{
        Map<String, Object> trace = new LinkedHashMap<>();
        trace.put("softwareName", "{task.software_name}");
        trace.put("version", "{task.version}");
        trace.put("availableModules", "{module_titles}");
        trace.put("module", normalize(module));
        trace.put("action", normalize(action));
        trace.put("operator", normalize(operator));
        trace.put("status", "STARTED");
        trace.put("createdAt", LocalDateTime.now());
        trace.put("updatedAt", LocalDateTime.now());
        traces.add(trace);
        return trace;
    }}

    public void appendFieldSnapshot(Map<String, Object> trace, String fieldName, Object beforeValue, Object afterValue) {{
        if (trace == null) {{
            return;
        }}
        List<String> snapshots = snapshotList(trace);
        snapshots.add(normalize(fieldName) + ": " + stringify(beforeValue) + " -> " + stringify(afterValue));
        trace.put("updatedAt", LocalDateTime.now());
    }}

    public void appendBusinessMessage(Map<String, Object> trace, String message) {{
        if (trace == null) {{
            return;
        }}
        List<String> messages = messageList(trace);
        messages.add(LocalDateTime.now() + " | " + normalize(message));
        trace.put("updatedAt", LocalDateTime.now());
    }}

    public void markSuccess(Map<String, Object> trace, String resultMessage) {{
        mark(trace, "SUCCESS", resultMessage);
    }}

    public void markFailure(Map<String, Object> trace, String errorMessage) {{
        mark(trace, "FAILED", errorMessage);
    }}

    public List<Map<String, Object>> listByModule(String module) {{
        List<Map<String, Object>> result = new ArrayList<>();
        String safeModule = normalize(module);
        for (Map<String, Object> trace : traces) {{
            if (safeModule.equals(trace.get("module"))) {{
                result.add(new LinkedHashMap<>(trace));
            }}
        }}
        return result;
    }}

    public List<Map<String, Object>> listByOperator(String operator) {{
        List<Map<String, Object>> result = new ArrayList<>();
        String safeOperator = normalize(operator);
        for (Map<String, Object> trace : traces) {{
            if (safeOperator.equals(trace.get("operator"))) {{
                result.add(new LinkedHashMap<>(trace));
            }}
        }}
        return result;
    }}

    public List<String> exportTraceLines() {{
        List<String> lines = new ArrayList<>();
        lines.add("software,module,action,operator,status,createdAt,updatedAt");
        for (Map<String, Object> trace : traces) {{
            lines.add(stringify(trace.get("softwareName")) + ","
                    + stringify(trace.get("module")) + ","
                    + stringify(trace.get("action")) + ","
                    + stringify(trace.get("operator")) + ","
                    + stringify(trace.get("status")) + ","
                    + stringify(trace.get("createdAt")) + ","
                    + stringify(trace.get("updatedAt")));
        }}
        return lines;
    }}

    @SuppressWarnings("unchecked")
    private List<String> snapshotList(Map<String, Object> trace) {{
        Object value = trace.get("fieldSnapshots");
        if (value instanceof List) {{
            return (List<String>) value;
        }}
        List<String> snapshots = new ArrayList<>();
        trace.put("fieldSnapshots", snapshots);
        return snapshots;
    }}

    @SuppressWarnings("unchecked")
    private List<String> messageList(Map<String, Object> trace) {{
        Object value = trace.get("messages");
        if (value instanceof List) {{
            return (List<String>) value;
        }}
        List<String> messages = new ArrayList<>();
        trace.put("messages", messages);
        return messages;
    }}

    private void mark(Map<String, Object> trace, String status, String message) {{
        if (trace == null) {{
            return;
        }}
        trace.put("status", status);
        trace.put("resultMessage", normalize(message));
        trace.put("updatedAt", LocalDateTime.now());
        appendBusinessMessage(trace, message);
    }}

    private String normalize(String value) {{
        if (value == null || value.trim().isEmpty()) {{
            return "-";
        }}
        return value.trim().replace(",", "，");
    }}

    private String stringify(Object value) {{
        if (value == null) {{
            return "";
        }}
        return String.valueOf(value).replace(",", "，").replace("\\n", " ");
    }}
}}
"""


def _readme(task: GenerationTask, blueprint: ProductBlueprint) -> str:
    module_lines = "\n".join(f"- {module.title}：{module.description}" for module in blueprint.modules)
    workflow_lines = "\n".join(
        f"- {item.get('name', '业务流程')}：{' -> '.join(item.get('steps', []))}，输出：{item.get('output', '')}"
        for item in blueprint.workflows[:5]
        if isinstance(item, dict)
    )
    architecture = getattr(blueprint, "technical_architecture", {}) or {}
    return f"""# {task.software_name}

版本：{task.version}

软件大类：{task.software_category}

技术特点：{task.product_type}

技术架构：{architecture.get("name") or "-"}

源码语言：{architecture.get("source_language") or task.language}

技术栈：{"、".join(architecture.get("stack") or []) or "-"}

## 软件概述

{blueprint.summary}

## 产品方案

- 具体场景：{blueprint.scenario or "-"}
- 产品定位：{blueprint.positioning or "-"}
- 目标用户：{"、".join(blueprint.target_users or blueprint.roles)}
- 核心业务对象：{"、".join(blueprint.business_objects)}
- 统计指标：{"、".join(blueprint.report_metrics)}
- 技术特点：{"、".join(blueprint.technical_features)}
- 质量规则：{"；".join(blueprint.quality_rules)}
- 数据关系：{"；".join(blueprint.data_relations)}
- 部署拓扑：{blueprint.deployment_topology or "-"}
- 方案指纹：{blueprint.generation_fingerprint or "-"}

## 业务流程

{workflow_lines or "-"}

## 功能模块

{module_lines}

## 运行说明

本工程为{task.software_name}的完整源码工程，用于支撑软件说明书和源码鉴别材料的一致性。
"""


def _package_token(value: str) -> str:
    token = _ascii_token(value).replace("-", "")
    return token or "software"


def _java_literal(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _ascii_token(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return cleaned or f"software{digest}"


def _class_prefix(value: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9]+", " ", value)
    words = [word for word in token.split() if word]
    if not words:
        return "CopyrightSoftware"
    return "".join(word[:1].upper() + word[1:] for word in words)


def _pascal(value: str) -> str:
    words = re.split(r"[^a-zA-Z0-9]+", value)
    words = [word for word in words if word]
    return "".join(word[:1].upper() + word[1:] for word in words) or "Business"


def _snake(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return value or "business"


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


def _count_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
