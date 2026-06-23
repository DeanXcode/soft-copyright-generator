from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


SOFTWARE_CATEGORIES = ["应用软件", "嵌入式软件", "中间件", "操作系统"]


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
        }


def normalize_software_category(value: str) -> str:
    value = str(value or "").strip()
    return value if value in SOFTWARE_CATEGORIES else "应用软件"


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
        return TechnicalArchitecture(
            key="embedded_c_edge",
            name="嵌入式边缘采集与控制架构",
            languages=["C++", "C", "Python"],
            source_language="C++/C/Python",
            stack=["C++17", "C HAL", "Python 3", "MQTT", "SQLite"],
            source_strategy="embedded_mixed",
            dev_environment={
                "hardware": "x86_64 开发工作站、ARM Cortex-M/ARM Linux 调试板、传感器模拟器",
                "os": "Windows 10/11、Ubuntu 22.04 LTS",
                "tool": "CMake、GCC/Clang、Python 3、串口调试工具、设备仿真脚本",
            },
            runtime_environment={
                "hardware": "ARM 控制器、边缘网关、采集终端或工业现场设备",
                "os": "嵌入式 Linux、RTOS 或设备厂商运行环境",
                "support": "设备驱动、MQTT/串口通信库、SQLite/本地缓存、边缘同步服务",
            },
        )

    if category == "中间件" or any(term in text for term in ["中间件", "网关", "消息", "队列", "接口", "集成", "同步", "API"]):
        return TechnicalArchitecture(
            key="middleware_gateway",
            name="服务中间件与接口网关架构",
            languages=["Java", "JavaScript", "SQL"],
            source_language="Java/JavaScript/SQL",
            stack=["Spring Boot", "Express.js", "OpenAPI", "MySQL", "Redis"],
            source_strategy="java_with_node_gateway",
            dev_environment={
                "hardware": "x86_64 开发工作站或服务器",
                "os": "Windows 10/11、Ubuntu 22.04 LTS",
                "tool": "JDK 17、Maven、Node.js、OpenAPI 调试工具、数据库管理工具",
            },
            runtime_environment={
                "hardware": "应用服务器、接口网关服务器或云主机",
                "os": "Linux 服务器、Windows Server 或容器运行环境",
                "support": "JDK 17、Node.js、关系型数据库、缓存服务、反向代理服务",
            },
        )

    if category == "操作系统":
        return TechnicalArchitecture(
            key="os_service_shell",
            name="系统服务与管理控制台架构",
            languages=["C++", "C", "Python", "Shell"],
            source_language="C++/C/Python/Shell",
            stack=["C++17", "POSIX Service", "Python CLI", "Shell Script", "SQLite"],
            source_strategy="system_service_mixed",
            dev_environment={
                "hardware": "x86_64 开发工作站、虚拟化测试主机",
                "os": "Ubuntu 22.04 LTS、Windows 11 WSL",
                "tool": "CMake、GCC/Clang、Python 3、Shell、系统服务调试工具",
            },
            runtime_environment={
                "hardware": "x86_64/ARM64 主机或虚拟化节点",
                "os": "Linux 发行版或专用系统运行环境",
                "support": "系统服务管理器、Shell 运行环境、SQLite、本地日志服务",
            },
        )

    if any(term in text for term in ["APP", "小程序", "移动", "手机", "用户端", "前端", "H5"]):
        return TechnicalArchitecture(
            key="web_mobile_app",
            name="移动端与服务端分离架构",
            languages=["JavaScript", "Java", "SQL"],
            source_language="JavaScript/Java/SQL",
            stack=["React/Vite", "Spring Boot", "REST API", "MySQL", "静态资源服务"],
            source_strategy="javascript_with_java_api",
            dev_environment={
                "hardware": "x86_64 开发工作站",
                "os": "Windows 10/11、Ubuntu 22.04 LTS",
                "tool": "Node.js、Vite、JDK 17、Maven、浏览器调试工具",
            },
            runtime_environment={
                "hardware": "Web 服务器、应用服务器、移动终端或浏览器终端",
                "os": "Linux 服务器、Android/iOS 浏览器环境、Windows 客户端浏览器",
                "support": "Node.js 静态构建产物、JDK 17、HTTP 服务、关系型数据库",
            },
        )

    if any(term in text for term in ["数据", "人工智能", "算法", "分析", "预测", "识别", "模型"]):
        return TechnicalArchitecture(
            key="data_ai_service",
            name="数据分析服务与 Web 管理架构",
            languages=["Python", "JavaScript", "SQL"],
            source_language="Python/JavaScript/SQL",
            stack=["FastAPI", "Pydantic", "React/Vite", "SQLite/MySQL", "任务调度"],
            source_strategy="python_with_web_console",
            dev_environment={
                "hardware": "x86_64 开发工作站或 GPU/CPU 计算节点",
                "os": "Windows 10/11、Ubuntu 22.04 LTS",
                "tool": "Python 3、FastAPI、Node.js、Vite、数据库管理工具",
            },
            runtime_environment={
                "hardware": "应用服务器、数据处理节点或云主机",
                "os": "Linux 服务器、Windows Server 或容器运行环境",
                "support": "Python 运行环境、HTTP 服务、任务调度服务、数据库服务",
            },
        )

    return TechnicalArchitecture(
        key="enterprise_web",
        name="企业级 Web 管理系统架构",
        languages=["Java", "JavaScript", "SQL"],
        source_language="Java/JavaScript/SQL",
        stack=["Spring Boot", "REST API", "React/Vite", "MySQL", "静态资源服务"],
        source_strategy="java_with_web_console",
        dev_environment={
            "hardware": "x86_64 开发工作站",
            "os": "Windows 10/11、Ubuntu 22.04 LTS",
            "tool": "JDK 17、Maven、Node.js、Vite、数据库管理工具、浏览器调试工具",
        },
        runtime_environment={
            "hardware": "应用服务器、数据库服务器或云主机",
            "os": "Linux 服务器、Windows Server 或容器运行环境",
            "support": "JDK 17、HTTP 服务、关系型数据库、浏览器运行环境",
        },
    )
