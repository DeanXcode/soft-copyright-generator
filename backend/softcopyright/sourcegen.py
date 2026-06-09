from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .blueprint import ProductBlueprint, FeatureModule
from .models import GenerationTask


def generate_source_project(task: GenerationTask, blueprint: ProductBlueprint, output_dir: Path) -> dict:
    source_dir = output_dir / "generated_source"
    source_dir.mkdir(parents=True, exist_ok=True)

    if task.language == "Java":
        files = _generate_java_project(task, blueprint, source_dir)
    elif task.language == "C#":
        files = _generate_csharp_project(task, blueprint, source_dir)
    elif task.language == "Python":
        files = _generate_python_project(task, blueprint, source_dir)
    elif task.language == "JavaScript":
        files = _generate_javascript_project(task, blueprint, source_dir)
    else:
        files = _generate_generic_project(task, blueprint, source_dir)

    blueprint_path = _write(source_dir / "product-blueprint.json", json.dumps(blueprint.to_dict(), ensure_ascii=False, indent=2))
    files.append(blueprint_path)
    total_lines = sum(_count_lines(path) for path in files)
    return {
        "source_dir": str(source_dir),
        "files": [str(path) for path in files],
        "blueprint_path": str(blueprint_path),
        "module_keys": [module.key for module in blueprint.modules],
        "module_titles": [module.title for module in blueprint.modules],
        "total_lines": total_lines,
    }


def read_source_line_entries(source_dir: Path) -> list[dict]:
    allowed = {
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
    entries: list[dict] = []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in allowed:
            continue
        relative = path.relative_to(source_dir).as_posix()
        if _is_duplicate_served_prototype(relative) or _is_internal_material_file(relative):
            continue
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
        if path.is_file() and not _is_duplicate_served_prototype(path.relative_to(source_dir).as_posix())
    ]
    return {
        "files": files,
        "total_lines": len(lines),
    }


def _is_duplicate_served_prototype(relative: str) -> bool:
    normalized = relative.replace("\\", "/")
    return (
        normalized.startswith("src/main/resources/static/ui-prototype/")
        or normalized.startswith("wwwroot/ui-prototype/")
    )


def _is_internal_material_file(relative: str) -> bool:
    normalized = relative.replace("\\", "/")
    name = Path(normalized).name.lower()
    return (
        name in {"readme.md", "ui_prototype_entry.md", "product-blueprint.json", "prototype-manifest.json"}
        or normalized.startswith("ui-prototype/")
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


def _generate_java_project(task: GenerationTask, blueprint: ProductBlueprint, source_dir: Path) -> list[Path]:
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

@SpringBootApplication
public class {app_class} {{
    public static void main(String[] args) {{
        SpringApplication.run({app_class}.class, args);
    }}
}}
""",
        )
    )

    files.append(
        _write(
            resources / "application.yml",
            f"""server:
  port: 8080
spring:
  application:
    name: {_ascii_token(task.software_name)}-service
  datasource:
    url: jdbc:mysql://localhost:3306/{_ascii_token(task.software_name)}?useUnicode=true&characterEncoding=utf8
    username: root
    password: root
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

    files.append(_write(source_dir / "README.md", _readme(task, blueprint)))
    files.append(_write(resources / "schema.sql", _java_schema_sql(blueprint)))
    files = _ensure_line_target(files, java_root, task, blueprint, target_lines=3200)
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


def _generate_python_project(task: GenerationTask, blueprint: ProductBlueprint, source_dir: Path) -> list[Path]:
    app_dir = source_dir / "app"
    for folder in [app_dir / "routers", app_dir / "services", app_dir / "models", app_dir / "schemas", app_dir / "core"]:
        folder.mkdir(parents=True, exist_ok=True)
    files = [
        _write(source_dir / "README.md", _readme(task, blueprint)),
        _write(source_dir / "requirements.txt", "fastapi\nuvicorn\npydantic\n"),
        _write(app_dir / "__init__.py", ""),
        _write(
            app_dir / "main.py",
            f'''from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

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
                    app_dir / "services" / f"{token}_service.py",
                    f'''from datetime import datetime
from app.models.{token}_model import {_pascal(token)}Record


class {_pascal(token)}Service:
    """{title}业务服务。"""

    def __init__(self):
        self.records: list[{_pascal(token)}Record] = []

    def list_records(self, keyword: str | None = None, status: str | None = None):
        result = []
        for record in self.records:
            keyword_matched = not keyword or keyword in record.name or keyword in record.code
            status_matched = not status or status == record.status
            if keyword_matched and status_matched:
                result.append(record)
        return result

    def create_record(self, code: str, name: str, owner_role: str, description: str):
        now = datetime.now()
        record = {_pascal(token)}Record(
            id=len(self.records) + 1,
            code=code,
            name=name,
            status="ENABLED",
            owner_role=owner_role,
            description=description,
            created_at=now,
            updated_at=now,
        )
        self.records.append(record)
        return record

    def update_status(self, record_id: int, status: str):
        for record in self.records:
            if record.id == record_id:
                record.status = status
                record.updated_at = datetime.now()
                return record
        raise ValueError("记录不存在")
''',
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
    files = _ensure_generic_line_target(files, app_dir / "services", task, blueprint, target_lines=3200, extension=".py")
    files = _align_source_material_pages(files, source_dir, app_dir / "services", ".py")
    return files


def _generate_javascript_project(task: GenerationTask, blueprint: ProductBlueprint, source_dir: Path) -> list[Path]:
    src = source_dir / "src"
    for folder in [src / "routes", src / "services", src / "models", src / "middleware"]:
        folder.mkdir(parents=True, exist_ok=True)
    files = [
        _write(source_dir / "README.md", _readme(task, blueprint)),
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
app.use(express.json());
app.use("/ui-prototype", express.static(path.join(__dirname, "..", "ui-prototype")));

app.get("/health", (req, res) => {{
  res.json({{ status: "ok", software: "{task.software_name}", version: "{task.version}" }});
}});

app.get("/", (req, res) => {{
  res.redirect("/ui-prototype/index.html");
}});

app.listen(8080, () => {{
  console.log("{task.software_name} service started on 8080");
}});
''',
        ),
    ]
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


def _generate_csharp_project(task: GenerationTask, blueprint: ProductBlueprint, source_dir: Path) -> list[Path]:
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
        _write(source_dir / "README.md", _readme(task, blueprint)),
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

var builder = WebApplication.CreateBuilder(args);
builder.Services.AddControllers();
builder.Services.AddSingleton(new SoftwareProfile(
    "{task.software_name}",
    "{task.version}",
    "{task.product_type}",
    "{blueprint.industry}"
));
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


def _align_source_material_pages(files: list[Path], source_dir: Path, target_dir: Path, extension: str) -> list[Path]:
    remainder = len(read_source_lines(source_dir)) % 50
    if remainder == 0:
        return files
    lines_needed = 50 - remainder
    if extension in {".js", ".ts"}:
        path = target_dir / "workflowTransitionSupport.js"
    elif extension == ".py":
        path = target_dir / "workflow_transition_support.py"
    else:
        path = target_dir / "workflow-state-support.properties"
    files.append(_write(path, _source_alignment_lines(lines_needed, extension)))
    return files


def _source_alignment_lines(lines_needed: int, extension: str) -> str:
    if extension in {".js", ".ts"}:
        base = [
            "const workflowTransitionSupport = { visible: new Set([\"PENDING\", \"PROCESSING\", \"COMPLETED\"]), closed: new Set([\"COMPLETED\", \"ARCHIVED\"]) };",
            "workflowTransitionSupport.normalizeRecord = (record) => ({ ...record, status: record && record.status ? String(record.status).trim() : \"PENDING\" });",
            "workflowTransitionSupport.canModify = (record) => !workflowTransitionSupport.closed.has(workflowTransitionSupport.normalizeRecord(record).status);",
            "workflowTransitionSupport.resolveNextStatus = (record) => workflowTransitionSupport.normalizeRecord(record).status === \"PENDING\" ? \"PROCESSING\" : \"COMPLETED\";",
            "workflowTransitionSupport.applyTransition = (record, operatorName) => ({ ...workflowTransitionSupport.normalizeRecord(record), operatorName: operatorName || \"system\", status: workflowTransitionSupport.resolveNextStatus(record), updatedAt: new Date() });",
            "workflowTransitionSupport.buildAuditLine = (record) => [record.code || \"-\", record.module || \"-\", record.operation || \"-\", record.operatorName || \"system\", record.status || \"PENDING\"].join(\"|\");",
            "workflowTransitionSupport.toQuery = (record) => ({ code: record.code || \"\", status: workflowTransitionSupport.normalizeRecord(record).status, updatedAt: record.updatedAt || new Date() });",
            "module.exports = workflowTransitionSupport;",
        ]
    elif extension == ".py":
        base = [
            "WORKFLOW_VISIBLE_STATES = {'PENDING', 'PROCESSING', 'COMPLETED'}",
            "WORKFLOW_CLOSED_STATES = {'COMPLETED', 'ARCHIVED'}",
            "def normalize_workflow_record(record):",
            "    current = dict(record or {})",
            "    current['status'] = str(current.get('status') or 'PENDING').strip() or 'PENDING'",
            "    return current",
            "def apply_workflow_transition(record, operator_name):",
            "    current = normalize_workflow_record(record)",
            "    current['operator_name'] = operator_name or 'system'",
            "    current['status'] = 'PROCESSING' if current['status'] == 'PENDING' else 'COMPLETED'",
            "    return current",
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
    if extension == ".cs":
        files.append(_write(target_dir / "BusinessWorkflowService.cs", _csharp_scenario_catalog(task, blueprint, target_lines - total_lines)))
    elif extension == ".js":
        files.append(_write(target_dir / "businessWorkflowService.js", _javascript_scenario_catalog(task, blueprint, target_lines - total_lines)))
    elif extension == ".py":
        files.append(_write(target_dir / "business_workflow_service.py", _python_scenario_catalog(task, blueprint, target_lines - total_lines)))
    else:
        files.append(_write(target_dir / f"business_workflow{extension}", _generic_scenario_catalog(task, blueprint, target_lines - total_lines, extension)))
    return files


def _javascript_scenario_catalog(task: GenerationTask, blueprint: ProductBlueprint, missing_lines: int) -> str:
    rows: list[str] = [
        "class BusinessWorkflowEngine {",
        "  constructor() {",
        "    this.auditLines = [];",
        "    this.statusFlow = [\"PENDING\", \"PROCESSING\", \"COMPLETED\", \"ARCHIVED\"];",
        "    this.defaultOwner = \"system\";",
        "  }",
    ]
    for index, module in _scenario_modules(blueprint, missing_lines, lines_per_item=12):
        operation = module.operations[(index - 1) % len(module.operations)] if module.operations else f"{module.title}处理"
        field = module.data_fields[(index - 1) % len(module.data_fields)] if module.data_fields else "业务状态"
        method_name = f"handle{_pascal(module.key)}{_pascal(_operation_token(operation))}{index:04d}"
        rows.extend(
            [
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
        )
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
            "module.exports = new BusinessWorkflowEngine();",
        ]
    )
    return "\n".join(rows)


def _python_scenario_catalog(task: GenerationTask, blueprint: ProductBlueprint, missing_lines: int) -> str:
    rows: list[str] = [
        "from datetime import datetime",
        "class BusinessWorkflowService:",
        "    def __init__(self):",
        "        self.audit_lines = []",
        "        self.status_flow = ['PENDING', 'PROCESSING', 'COMPLETED', 'ARCHIVED']",
        "        self.default_owner = 'system'",
    ]
    for index, module in _scenario_modules(blueprint, missing_lines, lines_per_item=12):
        operation = module.operations[(index - 1) % len(module.operations)] if module.operations else f"{module.title}处理"
        field = module.data_fields[(index - 1) % len(module.data_fields)] if module.data_fields else "业务状态"
        method_name = f"handle_{_snake(module.key)}_{_snake(_operation_token(operation))}_{index:04d}"
        rows.extend(
            [
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
        )
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
            "workflow_service = BusinessWorkflowService()",
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


def _scenario_modules(blueprint: ProductBlueprint, missing_lines: int, lines_per_item: int) -> list[tuple[int, FeatureModule]]:
    modules = blueprint.modules or [FeatureModule("business", "业务模块", "业务处理", ["BusinessRecord"])]
    scenario_count = max(96, missing_lines // max(1, lines_per_item) + 16)
    return [(index, modules[(index - 1) % len(modules)]) for index in range(1, scenario_count + 1)]


def _operation_token(value: str) -> str:
    for suffix in ["登记", "查询", "编辑", "审核", "发布", "归档", "导入", "导出", "预警", "复核", "统计", "追踪", "新增", "删除", "详情"]:
        if suffix in value:
            return suffix
    return value or "处理"


def _json_literal(value: str) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _python_literal(value: str) -> str:
    return repr(str(value))


def _php_literal(value: str) -> str:
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def _cpp_literal(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


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


def _csharp_scenario_catalog(task: GenerationTask, blueprint: ProductBlueprint, missing_lines: int) -> str:
    rows: list[str] = [
        "using System;",
        "using System.Collections.Generic;",
        "",
        f"namespace {_pascal(_ascii_token(task.software_name))}.Services;",
        "",
        "public class BusinessWorkflowService",
        "{",
        "    private readonly List<string> _auditLines = new();",
        "    private readonly List<string> _statusFlow = new() { \"PENDING\", \"PROCESSING\", \"COMPLETED\", \"ARCHIVED\" };",
        "    private const string DefaultOwner = \"system\";",
    ]
    for index, module in _scenario_modules(blueprint, missing_lines, lines_per_item=12):
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
    return f"""# {task.software_name}

版本：{task.version}

类型：{task.product_type}

编程语言：{task.language}

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
