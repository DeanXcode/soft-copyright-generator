from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str((ROOT / "backend").resolve()))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from docx import Document  # noqa: E402

from softcopyright.blueprint import FeatureModule, ProductBlueprint  # noqa: E402
from softcopyright.docgen import analyze_manual_density, generate_manual_docx  # noqa: E402
from softcopyright.models import GenerationTask  # noqa: E402
from softcopyright.screenshots import UiScreenshot  # noqa: E402


def main() -> int:
    output_dir = ROOT / "output-manual-density-review"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)
    image_path = _make_docx_image(output_dir / "figure-source.docx", output_dir / "figure-source.png")
    task = GenerationTask(
        software_name="说明书密度验收系统",
        version="V1.0",
        language="Java",
        product_type="金融软件",
        output_root=output_dir,
    )
    modules = _modules()
    blueprint = ProductBlueprint(
        software_name=task.software_name,
        version=task.version,
        language=task.language,
        product_type=task.product_type,
        industry="金融服务",
        purpose="用于验证说明书截图后的操作说明密度。",
        summary="系统用于验证截图后操作说明、字段说明和处理结果说明是否充分。",
        modules=modules,
        roles=["系统管理员", "复核人员"],
        pages=["登录页", "首页"] + [module.title for module in modules] + ["统计报表页"],
        dev_environment={"hardware": "CPU 8G", "os": "Windows 10", "tool": "JDK 17 / Maven"},
        runtime_environment={"hardware": "CPU 4G", "os": "Windows Server", "support": "JDK 17 / MySQL"},
        scenario="小微贷款风险巡检场景",
        positioning="面向风险复核人员的业务系统。",
        business_objects=["风险事件", "业务档案", "复核记录"],
        report_metrics=["风险事件数", "复核完成率", "异常处置数"],
        technical_features=["权限控制", "操作审计", "报表导出"],
        quality_rules=["高风险必须复核"],
        data_relations=["风险事件与复核记录关联"],
        deployment_topology="浏览器访问业务服务。",
        quality_score=100,
    )
    screenshots = {
        key: UiScreenshot(key, title, caption, "", str(image_path), 1280, 820)
        for key, title, caption in [
            ("login", "登录界面", "登录"),
            ("dashboard", "系统首页", "首页"),
            ("risk", "风险预警处置主界面", "主界面"),
            ("archive", "业务档案管理主界面", "主界面"),
            ("statistics", "统计报表界面", "统计"),
        ]
    }
    manual_docx = generate_manual_docx(task, blueprint, output_dir, ui_screenshots=screenshots, design_brief={"nav_model": "rail"})
    density = analyze_manual_density(manual_docx)
    shutil.rmtree(output_dir, ignore_errors=True)
    result = {
        "passed": bool(density.get("manual_operation_density_ready")),
        "temporary_output_removed": True,
        "density": density,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


def _modules() -> list[FeatureModule]:
    return [
        FeatureModule(
            "risk",
            "风险预警处置",
            "维护风险事件、预警等级、处置意见和复核记录。",
            ["RiskEvent", "ReviewRecord"],
            operations=["登记", "复核", "导出", "归档"],
            data_fields=["事件编号", "风险等级", "责任人", "处置状态", "更新时间"],
            rules=["高风险事件必须复核", "处置意见不能为空"],
        ),
        FeatureModule(
            "archive",
            "业务档案管理",
            "维护对象档案、附件材料、状态轨迹和关联记录。",
            ["BusinessProfile"],
            operations=["查询", "编辑", "导出", "追踪"],
            data_fields=["档案编号", "对象名称", "状态", "经办人", "更新时间"],
            rules=["档案变更必须写入审计日志"],
        ),
    ]


def _make_docx_image(docx_path: Path, image_path: Path) -> Path:
    document = Document()
    document.add_heading("截图占位源图", level=1)
    document.add_paragraph("该图片仅用于本地说明书密度验收。")
    document.save(docx_path)
    return image_path if image_path.exists() else _copy_known_png(image_path)


def _copy_known_png(image_path: Path) -> Path:
    for candidate in ROOT.glob("output*/**/*.png"):
        if candidate.is_file():
            shutil.copyfile(candidate, image_path)
            return image_path
    # A tiny valid 1x1 PNG, used only when no generated screenshot exists locally.
    image_path.write_bytes(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
            "0000000c49444154789c6360f8ffff3f0005fe02fea73581e70000000049454e44ae426082"
        )
    )
    return image_path


if __name__ == "__main__":
    raise SystemExit(main())
