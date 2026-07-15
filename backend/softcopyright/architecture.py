from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SOFTWARE_CATEGORIES = ["应用软件", "嵌入式软件", "中间件", "操作系统"]
SUPPORTED_SOURCE_STRATEGIES = [
    "java_with_web_console",
    "csharp_web_api",
    "javascript_with_java_api",
    "python_with_web_console",
    "java_with_node_gateway",
    "embedded_mixed",
    "system_service_mixed",
]


@dataclass
class TechnicalArchitecture:
    key: str
    name: str
    languages: list[str]
    source_language: str
    stack: list[str]
    source_strategy: str
    dev_environment: dict[str, str] = field(default_factory=dict)
    runtime_environment: dict[str, str] = field(default_factory=dict)
    source: str = "local-rule"
    rationale: str = ""
    project_layout: list[str] = field(default_factory=list)
    run_commands: list[str] = field(default_factory=list)
    quality_checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "languages": self.languages,
            "source_language": self.source_language,
            "stack": self.stack,
            "source_strategy": self.source_strategy,
            "dev_environment": self.dev_environment,
            "runtime_environment": self.runtime_environment,
            "source": self.source,
            "rationale": self.rationale,
            "project_layout": self.project_layout,
            "run_commands": self.run_commands,
            "quality_checks": self.quality_checks,
        }


ARCHITECTURE_CATALOG: dict[str, dict[str, Any]] = {
    "enterprise_web": {
        "name": "企业级 Web 管理系统架构",
        "languages": ["Java", "JavaScript", "SQL"],
        "source_language": "Java/JavaScript/SQL",
        "stack": ["Spring Boot", "REST API", "React/Vite", "MySQL", "静态资源服务"],
        "source_strategy": "java_with_web_console",
        "dev_environment": {
            "hardware": "x86_64 开发工作站",
            "os": "Windows 10/11、Ubuntu 22.04 LTS",
            "tool": "JDK 17、Maven、Node.js、Vite、数据库管理工具、浏览器调试工具",
        },
        "runtime_environment": {
            "hardware": "应用服务器、数据库服务器或云主机",
            "os": "Linux 服务器、Windows Server 或容器运行环境",
            "support": "JDK 17、HTTP 服务、关系型数据库、浏览器运行环境",
        },
        "project_layout": ["Spring Boot 后端服务", "React/Vite 管理控制台", "SQL 初始化脚本", "UI 原型静态入口"],
        "run_commands": ["mvn spring-boot:run", "npm install && npm run build"],
    },
    "dotnet_web_api": {
        "name": ".NET Web API 与管理控制台架构",
        "languages": ["C#", "JavaScript", "SQL"],
        "source_language": "C#/JavaScript/SQL",
        "stack": ["ASP.NET Core", "REST API", "React/Vite", "SQLite/MySQL", "静态资源服务"],
        "source_strategy": "csharp_web_api",
        "dev_environment": {
            "hardware": "x86_64 开发工作站",
            "os": "Windows 10/11、Ubuntu 22.04 LTS",
            "tool": ".NET SDK、Visual Studio/VS Code、Node.js、数据库管理工具",
        },
        "runtime_environment": {
            "hardware": "应用服务器、数据库服务器或云主机",
            "os": "Windows Server、Linux 服务器或容器运行环境",
            "support": ".NET 运行环境、HTTP 服务、关系型数据库、浏览器运行环境",
        },
        "project_layout": ["ASP.NET Core 后端服务", "wwwroot UI 原型入口", "业务 Service/Repository/Model 分层", "SQL/配置文件"],
        "run_commands": ["dotnet run --urls http://127.0.0.1:5000"],
    },
    "web_mobile_app": {
        "name": "移动端与服务端分离架构",
        "languages": ["JavaScript", "Java", "SQL"],
        "source_language": "JavaScript/Java/SQL",
        "stack": ["React/Vite", "Spring Boot", "REST API", "MySQL", "静态资源服务"],
        "source_strategy": "javascript_with_java_api",
        "dev_environment": {
            "hardware": "x86_64 开发工作站",
            "os": "Windows 10/11、Ubuntu 22.04 LTS",
            "tool": "Node.js、Vite、JDK 17、Maven、浏览器调试工具",
        },
        "runtime_environment": {
            "hardware": "Web 服务器、应用服务器、移动终端或浏览器终端",
            "os": "Linux 服务器、Android/iOS 浏览器环境、Windows 客户端浏览器",
            "support": "Node.js 静态构建产物、JDK 17、HTTP 服务、关系型数据库",
        },
        "project_layout": ["React/Vite 用户端", "Spring Boot API 服务", "移动端 UI 原型", "接口与数据脚本"],
        "run_commands": ["npm install && npm start", "mvn spring-boot:run"],
    },
    "data_ai_service": {
        "name": "数据分析服务与 Web 管理架构",
        "languages": ["Python", "JavaScript", "SQL"],
        "source_language": "Python/JavaScript/SQL",
        "stack": ["FastAPI", "Pydantic", "React/Vite", "SQLite/MySQL", "任务调度"],
        "source_strategy": "python_with_web_console",
        "dev_environment": {
            "hardware": "x86_64 开发工作站或 GPU/CPU 计算节点",
            "os": "Windows 10/11、Ubuntu 22.04 LTS",
            "tool": "Python 3、FastAPI、Node.js、Vite、数据库管理工具",
        },
        "runtime_environment": {
            "hardware": "应用服务器、数据处理节点或云主机",
            "os": "Linux 服务器、Windows Server 或容器运行环境",
            "support": "Python 运行环境、HTTP 服务、任务调度服务、数据库服务",
        },
        "project_layout": ["FastAPI 服务", "React/Vite 数据控制台", "任务调度模块", "数据模型与指标脚本"],
        "run_commands": ["uvicorn app.main:app --host 127.0.0.1 --port 8080", "npm install && npm start"],
    },
    "middleware_gateway": {
        "name": "服务中间件与接口网关架构",
        "languages": ["Java", "JavaScript", "SQL"],
        "source_language": "Java/JavaScript/SQL",
        "stack": ["Spring Boot", "Express.js", "OpenAPI", "MySQL", "Redis"],
        "source_strategy": "java_with_node_gateway",
        "dev_environment": {
            "hardware": "x86_64 开发工作站或服务器",
            "os": "Windows 10/11、Ubuntu 22.04 LTS",
            "tool": "JDK 17、Maven、Node.js、OpenAPI 调试工具、数据库管理工具",
        },
        "runtime_environment": {
            "hardware": "应用服务器、接口网关服务器或云主机",
            "os": "Linux 服务器、Windows Server 或容器运行环境",
            "support": "JDK 17、Node.js、关系型数据库、缓存服务、反向代理服务",
        },
        "project_layout": ["Spring Boot 核心服务", "Node.js 网关服务", "OpenAPI 接口描述", "数据与缓存配置"],
        "run_commands": ["mvn spring-boot:run", "npm install && npm start"],
    },
    "embedded_c_edge": {
        "name": "嵌入式边缘采集与控制架构",
        "languages": ["C++", "C", "Python"],
        "source_language": "C++/C/Python",
        "stack": ["C++17", "C HAL", "Python 3", "MQTT", "SQLite"],
        "source_strategy": "embedded_mixed",
        "dev_environment": {
            "hardware": "x86_64 开发工作站、ARM Cortex-M/ARM Linux 调试板、传感器模拟器",
            "os": "Windows 10/11、Ubuntu 22.04 LTS",
            "tool": "CMake、GCC/Clang、Python 3、串口调试工具、设备仿真脚本",
        },
        "runtime_environment": {
            "hardware": "ARM 控制器、边缘网关、采集终端或工业现场设备",
            "os": "嵌入式 Linux、RTOS 或设备厂商运行环境",
            "support": "设备驱动、MQTT/串口通信库、SQLite/本地缓存、边缘同步服务",
        },
        "project_layout": ["C++ 边缘服务", "C HAL 设备适配层", "Python 调试脚本", "CMake 构建文件"],
        "run_commands": ["cmake -S . -B build", "cmake --build build", "python tools/device_simulator.py"],
    },
    "system_service_shell": {
        "name": "系统服务与管理控制台架构",
        "languages": ["C++", "C", "Python", "Shell"],
        "source_language": "C++/C/Python/Shell",
        "stack": ["C++17", "POSIX Service", "Python CLI", "Shell Script", "SQLite"],
        "source_strategy": "system_service_mixed",
        "dev_environment": {
            "hardware": "x86_64 开发工作站、虚拟化测试主机",
            "os": "Ubuntu 22.04 LTS、Windows 11 WSL",
            "tool": "CMake、GCC/Clang、Python 3、Shell、系统服务调试工具",
        },
        "runtime_environment": {
            "hardware": "x86_64/ARM64 主机或虚拟化节点",
            "os": "Linux 发行版或专用系统运行环境",
            "support": "系统服务管理器、Shell 运行环境、SQLite、本地日志服务",
        },
        "project_layout": ["C++ 系统服务", "Python 管理 CLI", "Shell 运维脚本", "本地配置与日志目录"],
        "run_commands": ["cmake -S . -B build", "cmake --build build", "python cli/admin.py status"],
    },
}


def normalize_software_category(value: str) -> str:
    value = str(value or "").strip()
    return value if value in SOFTWARE_CATEGORIES else "应用软件"


def architecture_catalog_for_prompt() -> list[dict[str, Any]]:
    return [
        {
            "key": key,
            "name": item["name"],
            "languages": item["languages"],
            "source_language": item["source_language"],
            "stack": item["stack"],
            "source_strategy": item["source_strategy"],
            "best_for": _best_for_text(key),
        }
        for key, item in ARCHITECTURE_CATALOG.items()
    ]


def create_technical_architecture(
    key: str,
    *,
    source: str = "local-rule",
    rationale: str = "",
    project_layout: list[str] | None = None,
    run_commands: list[str] | None = None,
    quality_checks: list[str] | None = None,
) -> TechnicalArchitecture:
    normalized_key = str(key or "").strip()
    item = ARCHITECTURE_CATALOG.get(normalized_key) or ARCHITECTURE_CATALOG["enterprise_web"]
    return TechnicalArchitecture(
        key=normalized_key if normalized_key in ARCHITECTURE_CATALOG else "enterprise_web",
        name=item["name"],
        languages=list(item["languages"]),
        source_language=item["source_language"],
        stack=list(item["stack"]),
        source_strategy=item["source_strategy"],
        dev_environment=dict(item["dev_environment"]),
        runtime_environment=dict(item["runtime_environment"]),
        source=source,
        rationale=rationale,
        project_layout=list(project_layout or item.get("project_layout") or []),
        run_commands=list(run_commands or item.get("run_commands") or []),
        quality_checks=list(quality_checks or _default_quality_checks(item["source_strategy"])),
    )


def select_technical_architecture(task: Any, blueprint: Any | None = None) -> TechnicalArchitecture:
    category = normalize_software_category(getattr(task, "software_category", "应用软件"))
    text = " ".join(
        str(item or "")
        for item in [
            getattr(task, "software_name", ""),
            getattr(task, "product_type", ""),
            getattr(task, "feature_hint", ""),
            getattr(blueprint, "industry", ""),
            getattr(blueprint, "scenario", ""),
            getattr(blueprint, "positioning", ""),
        ]
    )

    if category == "嵌入式软件":
        return create_technical_architecture("embedded_c_edge")

    if category == "中间件" or any(term in text for term in ["中间件", "网关", "消息", "队列", "接口", "集成", "同步", "API"]):
        return create_technical_architecture("middleware_gateway")

    if category == "操作系统":
        return create_technical_architecture("system_service_shell")

    if any(term in text for term in ["APP", "小程序", "移动", "手机", "用户端", "前端", "H5"]):
        return create_technical_architecture("web_mobile_app")

    if any(term in text for term in ["数据", "人工智能", "算法", "分析", "预测", "识别", "模型"]):
        return create_technical_architecture("data_ai_service")

    return create_technical_architecture("enterprise_web")


def _best_for_text(key: str) -> str:
    table = {
        "enterprise_web": "后台管理、业务流程、行业管理平台",
        "dotnet_web_api": "Windows 生态、企业内网、C# 业务服务、需要 .NET 项目证据",
        "web_mobile_app": "APP、小程序、H5、移动用户端和服务端分离",
        "data_ai_service": "数据分析、AI、算法、预测、识别、任务调度",
        "middleware_gateway": "接口网关、中间件、集成同步、消息和开放 API",
        "embedded_c_edge": "嵌入式、物联网边缘采集、设备控制",
        "system_service_shell": "操作系统、系统服务、底层管理工具",
    }
    return table.get(key, "")


def _default_quality_checks(source_strategy: str) -> list[str]:
    common = ["源码行数满足软著鉴别材料目标", "说明书、源码、截图共享同一产品蓝图", "最终 ZIP 保持 5 个交付文件"]
    strategy_checks = {
        "java_with_web_console": ["Spring Boot 后端结构完整", "Web 控制台静态入口可浏览"],
        "csharp_web_api": ["ASP.NET Core 分层结构完整", "wwwroot 原型入口可浏览"],
        "javascript_with_java_api": ["前端工程和 Java API 服务边界清晰", "移动端页面与接口对象一致"],
        "python_with_web_console": ["FastAPI 服务结构完整", "数据处理模块与前端看板一致"],
        "java_with_node_gateway": ["Java 核心服务和 Node 网关分层清晰", "接口契约与业务对象一致"],
        "embedded_mixed": ["C/C++ 设备层和 Python 调试脚本职责清晰", "采集/控制流程可追溯"],
        "system_service_mixed": ["系统服务、CLI 和脚本职责清晰", "配置、日志和状态检查闭环"],
    }
    return strategy_checks.get(source_strategy, []) + common
