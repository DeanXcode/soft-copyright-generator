from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import unittest
from unittest.mock import patch

from backend.softcopyright.blueprint import FeatureModule, ProductBlueprint
from backend.softcopyright.models import GenerationTask
from backend.softcopyright.screenshot_page_runtime import project_server_command, resolve_node_runtime
from backend.softcopyright.screenshot_capture import _navigate_for_screenshot
from backend.softcopyright.screenshots import _project_prototype_target, _project_runtime_served_dirs
from backend.softcopyright.sourcegen import generate_source_project


class ScreenshotPageRuntimeTests(unittest.TestCase):
    def test_project_server_process_does_not_use_unread_output_pipes(self):
        source_info = {
            "source_dir": "C:/generated/project",
            "ui_project_entry": {
                "route_mode": "node-static",
                "entry_url": "http://127.0.0.1:8080/ui-prototype/index.html",
            },
        }
        process = object()
        with patch(
            "backend.softcopyright.screenshot_page_runtime.select_port", return_value=18080
        ), patch(
            "backend.softcopyright.screenshot_page_runtime.project_server_command",
            return_value={
                "args": ["node", "server.js"],
                "env": {},
                "display": "node server.js",
                "route_mode": "node-static",
            },
        ), patch(
            "backend.softcopyright.screenshot_page_runtime.subprocess.Popen", return_value=process
        ) as popen, patch(
            "backend.softcopyright.screenshot_page_runtime.wait_for_http"
        ):
            from backend.softcopyright.screenshot_page_runtime import start_project_server

            server = start_project_server(source_info)

        self.assertIs(server["process"], process)
        self.assertEqual(popen.call_args.kwargs["stdout"], __import__("subprocess").DEVNULL)
        self.assertEqual(popen.call_args.kwargs["stderr"], __import__("subprocess").DEVNULL)

    def test_project_page_navigation_uses_dom_ready_instead_of_network_idle(self):
        class PageStub:
            def __init__(self):
                self.calls = []

            def goto(self, url, **kwargs):
                self.calls.append((url, kwargs))

        page = PageStub()
        _navigate_for_screenshot(page, "http://127.0.0.1:8080/page.html", project_server=True)

        self.assertEqual(
            page.calls,
            [("http://127.0.0.1:8080/page.html", {"wait_until": "domcontentloaded"})],
        )

    def test_file_page_navigation_waits_for_document_load(self):
        class PageStub:
            def __init__(self):
                self.calls = []

            def goto(self, url, **kwargs):
                self.calls.append((url, kwargs))

        page = PageStub()
        _navigate_for_screenshot(page, "file:///tmp/page.html", project_server=False)

        self.assertEqual(page.calls, [("file:///tmp/page.html", {"wait_until": "load"})])

    def create_node_fallback(self, source_dir: Path):
        node_dir = source_dir / "web-console"
        (node_dir / "src").mkdir(parents=True)
        (node_dir / "src" / "server.js").write_text("console.log('ready')", encoding="utf-8")
        (node_dir / "package.json").write_text('{"scripts":{"start":"node src/server.js"}}', encoding="utf-8")

    def test_packaged_project_server_uses_electron_as_node(self):
        electron_node = r"C:\Program Files\Soft Copyright Generator\Soft Copyright Generator.exe"
        with TemporaryDirectory() as temporary_directory:
            source_dir = Path(temporary_directory)
            (source_dir / "src").mkdir()
            (source_dir / "src" / "server.js").write_text("console.log('ready')", encoding="utf-8")
            (source_dir / "package.json").write_text('{"scripts":{"start":"node src/server.js"}}', encoding="utf-8")
            with patch.dict("os.environ", {"SOFT_ELECTRON_NODE": electron_node}, clear=False), patch(
                "backend.softcopyright.screenshot_page_runtime.shutil.which", return_value=None
            ):
                command = project_server_command(source_dir, "node-static", 8080)

        self.assertEqual(command["args"][0], electron_node)
        self.assertEqual(command["env"]["ELECTRON_RUN_AS_NODE"], "1")
        self.assertEqual(command["env"]["PORT"], "8080")

    def test_system_node_does_not_inherit_electron_run_mode(self):
        system_node = r"C:\Program Files\nodejs\node.exe"
        with patch.dict("os.environ", {"ELECTRON_RUN_AS_NODE": "1"}, clear=False), patch(
            "backend.softcopyright.screenshot_page_runtime.shutil.which", return_value=system_node
        ):
            with patch.dict("os.environ", {"SOFT_ELECTRON_NODE": ""}, clear=False):
                node, env = resolve_node_runtime()

        self.assertEqual(node, system_node)
        self.assertNotIn("ELECTRON_RUN_AS_NODE", env)

    def test_csharp_without_dotnet_uses_packaged_node_fallback(self):
        electron_node = r"C:\Program Files\Soft Copyright Generator\Soft Copyright Generator.exe"
        with TemporaryDirectory() as temporary_directory:
            source_dir = Path(temporary_directory)
            (source_dir / "Acceptance.csproj").write_text("<Project />", encoding="utf-8")
            self.create_node_fallback(source_dir)
            with patch.dict("os.environ", {"SOFT_ELECTRON_NODE": electron_node}, clear=False), patch(
                "backend.softcopyright.screenshot_page_runtime.shutil.which", return_value=None
            ):
                command = project_server_command(source_dir, "aspnet-static", 5000)

        self.assertEqual(command["args"][0], electron_node)
        self.assertEqual(command["route_mode"], "node-static")
        self.assertIn("未安装 .NET", command["display"])

    def test_java_without_maven_uses_packaged_node_fallback(self):
        electron_node = r"C:\Program Files\Soft Copyright Generator\Soft Copyright Generator.exe"
        with TemporaryDirectory() as temporary_directory:
            source_dir = Path(temporary_directory)
            (source_dir / "pom.xml").write_text("<project />", encoding="utf-8")
            self.create_node_fallback(source_dir)
            with patch.dict("os.environ", {"SOFT_ELECTRON_NODE": electron_node}, clear=False), patch(
                "backend.softcopyright.screenshot_page_runtime.shutil.which", return_value=None
            ):
                command = project_server_command(source_dir, "spring-static", 8080)

        self.assertEqual(command["args"][0], electron_node)
        self.assertEqual(command["route_mode"], "node-static")
        self.assertIn("未安装 Maven", command["display"])

    def test_fastapi_uses_current_bundled_python(self):
        with TemporaryDirectory() as temporary_directory:
            source_dir = Path(temporary_directory)
            (source_dir / "app").mkdir()
            (source_dir / "app" / "main.py").write_text("app = None", encoding="utf-8")
            with patch("backend.softcopyright.screenshot_page_runtime.shutil.which", return_value=None), patch(
                "backend.softcopyright.screenshot_page_runtime.python_runtime_has_fastapi", return_value=True
            ):
                command = project_server_command(source_dir, "fastapi-static", 8080)

        self.assertEqual(command["args"][0], sys.executable)
        self.assertEqual(command["route_mode"], "fastapi-static")

    def test_fastapi_without_runtime_dependencies_uses_packaged_node_fallback(self):
        electron_node = r"C:\Program Files\Soft Copyright Generator\Soft Copyright Generator.exe"
        with TemporaryDirectory() as temporary_directory:
            source_dir = Path(temporary_directory)
            (source_dir / "app").mkdir()
            (source_dir / "app" / "main.py").write_text("app = None", encoding="utf-8")
            self.create_node_fallback(source_dir)
            with patch.dict("os.environ", {"SOFT_ELECTRON_NODE": electron_node}, clear=False), patch(
                "backend.softcopyright.screenshot_page_runtime.shutil.which", return_value=None
            ), patch(
                "backend.softcopyright.screenshot_page_runtime.python_runtime_has_fastapi", return_value=False
            ):
                command = project_server_command(source_dir, "fastapi-static", 8080)

        self.assertEqual(command["args"][0], electron_node)
        self.assertEqual(command["route_mode"], "node-static")
        self.assertIn("缺少 FastAPI/Uvicorn", command["display"])

    def test_native_targets_are_primary_and_fallback_prototype_is_published(self):
        with TemporaryDirectory() as temporary_directory:
            source_dir = Path(temporary_directory)
            (source_dir / "Acceptance.csproj").write_text("<Project />", encoding="utf-8")
            self.create_node_fallback(source_dir)
            target = _project_prototype_target(source_dir)
            served_dirs = _project_runtime_served_dirs(source_dir, Path(target["served_dir"]))

        self.assertEqual(target["route_mode"], "aspnet-static")
        self.assertEqual(len(served_dirs), 2)
        self.assertTrue(str(served_dirs[1]).replace("\\", "/").endswith("web-console/ui-prototype"))

    def test_generated_architectures_include_zero_dependency_runtime_console(self):
        module = FeatureModule(
            "qualification_query",
            "资质信息查询",
            "查询企业资质状态与有效期",
            ["QualificationRecord"],
            operations=["查询资质"],
            data_fields=["资质编号", "企业名称", "有效状态"],
        )
        cases = (
            ("C#", "csharp_web_api", "aspnet-static"),
            ("Java", "", "spring-static"),
            ("C++", "embedded_mixed", "node-static"),
            ("C++", "system_service_mixed", "node-static"),
        )
        for language, strategy, expected_entry_mode in cases:
            with self.subTest(language=language), TemporaryDirectory() as temporary_directory:
                blueprint = ProductBlueprint(
                    software_name="Runtime Acceptance",
                    version="V1.0",
                    language=language,
                    product_type="管理软件",
                    industry="企业服务",
                    purpose="验证客户运行时",
                    summary="验证客户机无需安装开发环境",
                    modules=[module],
                    roles=["管理员"],
                    pages=["资质信息查询"],
                    dev_environment={},
                    runtime_environment={},
                    technical_architecture={"source_strategy": strategy, "source_language": f"{language}/JavaScript"} if strategy else {},
                )
                task = GenerationTask(software_name="Runtime Acceptance", language=language)
                result = generate_source_project(task, blueprint, Path(temporary_directory))
                source_dir = Path(result["source_dir"])
                package_data = json.loads((source_dir / "web-console" / "package.json").read_text(encoding="utf-8"))

                self.assertTrue((source_dir / "web-console" / "src" / "server.js").exists())
                self.assertFalse(package_data.get("dependencies"))
                self.assertEqual(_project_prototype_target(source_dir)["route_mode"], expected_entry_mode)


if __name__ == "__main__":
    unittest.main()
