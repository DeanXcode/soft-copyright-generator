from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from softcopyright.generator import generate_materials
from softcopyright.llm.provider import build_provider, config_from_env
from softcopyright.models import GenerationTask, PRODUCT_TYPES, SUPPORTED_LANGUAGES


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="软著材料一键生成原型")
    parser.add_argument("--name", required=True, help="软件全称")
    parser.add_argument("--version", default="V1.0", help="版本号")
    parser.add_argument("--language", default="Java", choices=SUPPORTED_LANGUAGES, help="编程语言")
    parser.add_argument("--product-type", default="智慧城市软件", choices=PRODUCT_TYPES, help="产品类型/技术特点")
    parser.add_argument("--feature-hint", default="", help="100字以内业务补充说明")
    parser.add_argument("--model-provider", default="local-template", help="模型供应商")
    parser.add_argument("--model-name", default="template-v1", help="模型名称")
    parser.add_argument("--api-base-url", default="", help="OpenAI-compatible API Base URL")
    parser.add_argument("--api-key", default="", help="API Key；不传时读取环境变量")
    parser.add_argument("--randomness", default="standard", choices=["保守", "standard", "高差异"], help="随机度")
    parser.add_argument("--seed", default="", help="随机种子，不填则自动生成")
    parser.add_argument("--output-root", default="output", help="输出目录")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    task = GenerationTask(
        software_name=args.name,
        version=args.version,
        language=args.language,
        product_type=args.product_type,
        feature_hint=args.feature_hint,
        model_provider=args.model_provider,
        model_name=args.model_name,
        randomness=args.randomness,
        output_root=Path(args.output_root),
    )
    if args.seed:
        task.seed = args.seed

    llm_config = config_from_env(
        provider=args.model_provider,
        model=args.model_name,
        base_url=args.api_base_url,
        api_key=args.api_key,
    )
    task.llm_base_url = llm_config.base_url
    task.llm_api_key_configured = bool(llm_config.api_key)

    def emit(event: dict) -> None:
        print("EVENT_JSON:" + json.dumps(event, ensure_ascii=True), flush=True)

    provider = build_provider(llm_config)
    report = generate_materials(task, emit=emit, llm_provider=provider)
    print(f"生成完成：{report['zip_path']}")
    print(
        "RESULT_JSON:"
        + json.dumps(
            {
                "zip_path": report["zip_path"],
                "output_dir": report["task"].get("output_dir"),
                "warnings": report.get("warnings", []),
                "checks": report.get("checks", {}),
                "files": report.get("files", []),
                "validation": report.get("validation", {}),
                "blueprint_source": report.get("blueprint_source", "local-template"),
                "manual_source": report.get("manual_source", "local-template"),
                "seed": report["task"].get("seed", ""),
                "randomness": report["task"].get("randomness", ""),
                "feature_hint": report["task"].get("feature_hint", ""),
                "feature_hint_meta": report.get("feature_hint", {}),
            },
            ensure_ascii=True,
        ),
        flush=True,
    )
    if report.get("warnings"):
        print("警告：")
        for warning in report["warnings"]:
            print(f"- {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
