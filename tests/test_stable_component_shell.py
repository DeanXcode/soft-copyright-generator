from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from backend.softcopyright.ai_frontend_codegen import generate_ai_frontend_pages
from backend.softcopyright.blueprint import FeatureModule, ProductBlueprint
from backend.softcopyright.models import GenerationTask
from backend.softcopyright.screenshots import UiScreenshot
from backend.softcopyright.ui_blueprint import UiBlueprint, UiScreenBlueprint


class _FailingProvider:
    def chat(self, *args, **kwargs):  # pragma: no cover - should never be called
        raise AssertionError("stable shell must not call page-level LLM")


class StableComponentShellTests(unittest.TestCase):
    def test_admin_pages_use_stable_shell_without_page_llm(self):
        with patch.dict("os.environ", {"SOFT_AI_FRONTEND_MODE": "stable-component-shell"}), TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            task = GenerationTask(
                software_name="矿山机械设备运行状态监测与智能维护管理系统",
                version="V1.0",
                product_type="人工智能软件",
                language="Python",
            )
            module = FeatureModule(
                key="device_profile",
                title="设备档案管理",
                description="维护矿山机械设备档案、运行状态和维保记录。",
                entities=["DeviceProfile"],
                operations=["登记", "校验", "分析", "确认"],
                data_fields=["设备编号", "设备名称", "安装位置", "运行状态"],
            )
            blueprint = ProductBlueprint(
                software_name=task.software_name,
                version=task.version,
                language=task.language,
                product_type=task.product_type,
                industry="矿山设备智能运维",
                purpose="支撑设备运行监测与维护管理。",
                summary="围绕矿山机械设备运行状态、告警处置和维保闭环进行管理。",
                modules=[module],
                roles=["设备管理员", "维护人员"],
                pages=["登录页", "系统首页", "设备档案管理"],
                dev_environment={},
                runtime_environment={},
                report_metrics=["在线设备数", "异常告警数", "维护完成率", "预测准确率"],
            )
            ui_blueprint = UiBlueprint(
                renderer="admin",
                visual_style="工业监控后台",
                source="llm",
                screens=[
                    UiScreenBlueprint("login", "登录界面", "用户登录", "admin_login"),
                    UiScreenBlueprint("dashboard", "系统首页", "总览", "admin_dashboard"),
                    UiScreenBlueprint("device_profile", "设备档案管理", "设备档案", "admin_module", module_key="device_profile"),
                ],
            )
            screenshots = [
                UiScreenshot("login", "登录界面", "登录", str(root / "login.html"), page_kind="login"),
                UiScreenshot("dashboard", "系统首页", "首页", str(root / "dashboard.html"), page_kind="dashboard"),
                UiScreenshot(
                    "device_profile",
                    "设备档案管理",
                    "设备档案",
                    str(root / "device_profile.html"),
                    page_kind="module",
                    module_key="device_profile",
                ),
            ]

            report = generate_ai_frontend_pages(
                task=task,
                blueprint=blueprint,
                ui_blueprint=ui_blueprint,
                screenshots=screenshots,
                provider=_FailingProvider(),
                require_llm=True,
                visual_reference_report={
                    "ready": True,
                    "mode": "style_reference",
                    "reference_count": 1,
                    "page_count": 3,
                    "style_reference_ready": True,
                    "style_reference": {"ready": True, "visual_tokens": ["工业", "深色侧栏"]},
                },
            )

            self.assertTrue(report["ready"])
            self.assertEqual(report["source"], "gpt-visual-reference-stable-component-shell")
            self.assertEqual(report["page_count"], 3)
            self.assertIn("reference-driven-stable-component-shell", report["architecture"]["strategy"])
            self.assertIn("stable-app", (root / "dashboard.html").read_text(encoding="utf-8"))
            self.assertIn("runtime-record-panel", (root / "device_profile.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
