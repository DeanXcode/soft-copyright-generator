from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .blueprint import ProductBlueprint, FeatureModule
from .models import GenerationTask


def generate_source_project(task: GenerationTask, blueprint: ProductBlueprint, output_dir: Path) -> dict:
    source_dir = output_dir / "generated_source"
    source_dir.mkdir(parents=True, exist_ok=True)

    if task.language == "Java":
        files = _generate_java_project(task, blueprint, source_dir)
    elif task.language == "Python":
        files = _generate_python_project(task, blueprint, source_dir)
    elif task.language == "JavaScript":
        files = _generate_javascript_project(task, blueprint, source_dir)
    else:
        files = _generate_generic_project(task, blueprint, source_dir)

    total_lines = sum(_count_lines(path) for path in files)
    return {
        "source_dir": str(source_dir),
        "files": [str(path) for path in files],
        "total_lines": total_lines,
    }


def read_source_lines(source_dir: Path) -> list[str]:
    allowed = {
        ".java",
        ".xml",
        ".py",
        ".js",
        ".ts",
        ".json",
        ".php",
        ".cs",
        ".cpp",
        ".h",
        ".hpp",
        ".html",
        ".css",
        ".md",
        ".sql",
        ".yml",
        ".yaml",
        ".properties",
    }
    lines: list[str] = []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in allowed:
            continue
        relative = path.relative_to(source_dir).as_posix()
        lines.append(f"// ===== {relative} =====")
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="gbk", errors="ignore")
        for line in content.splitlines():
            lines.append(line.rstrip())
        lines.append("")
    return lines


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
    <groupId>com.copyright</groupId>
    <artifactId>{_ascii_token(task.software_name)}</artifactId>
    <version>1.0.0</version>
    <name>{task.software_name}</name>
    <properties>
        <java.version>17</java.version>
    </properties>
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

app = FastAPI(title="{task.software_name}", version="{task.version}")


@app.get("/health")
def health_check():
    return {{"status": "ok", "software": "{task.software_name}", "version": "{task.version}"}}
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
const app = express();
app.use(express.json());

app.get("/health", (req, res) => {{
  res.json({{ status: "ok", software: "{task.software_name}", version: "{task.version}" }});
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
    return files


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
            f"// {task.software_name} - {title}",
            f"// {module.description}",
            f"class {_pascal(module.key)}Service {{",
            "public:",
            "    void createRecord();",
            "    void updateRecord();",
            "    void deleteRecord();",
            "    void queryRecord();",
            "};",
        ]
    )


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
    return f"""# {task.software_name}

版本：{task.version}

类型：{task.product_type}

编程语言：{task.language}

## 软件概述

{blueprint.summary}

## 功能模块

{module_lines}

## 运行说明

本工程为软著材料生成系统自动生成的完整源码工程，用于支撑软件说明书和源码鉴别材料的一致性。
"""


def _package_token(value: str) -> str:
    token = _ascii_token(value).replace("-", "")
    return token or "software"


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
