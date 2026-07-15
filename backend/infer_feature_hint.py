from __future__ import annotations

import argparse
import json
import sys

from softcopyright.feature_inference import harmonize_feature_hint
from softcopyright.llm.provider import build_provider, config_from_env


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Infer business feature hint from software name")
    parser.add_argument("--name", required=True, help="software name")
    parser.add_argument("--product-type", default="", help="product type")
    parser.add_argument("--feature-hint", default="", help="existing feature hint")
    parser.add_argument("--model-provider", default="custom", help="model provider; GPT/OpenAI-compatible is required")
    parser.add_argument("--model-name", default="gpt-5.5", help="model name")
    parser.add_argument("--api-base-url", default="", help="OpenAI-compatible API Base URL")
    parser.add_argument("--api-key", default="", help="API Key")
    parser.add_argument("--timeout-seconds", type=int, default=60, help="LLM request timeout for name inference")
    parser.add_argument("--retry-count", type=int, default=0, help="LLM retry count for name inference")
    parser.add_argument("--require-llm", action="store_true", help="fail instead of local fallback when LLM inference fails")
    parser.add_argument("--min-blueprint-modules", type=int, default=8, help="minimum accepted blueprint module count")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.model_provider.lower() in {"", "local", "local-template", "template"}:
            return _fail("当前版本已关闭默认模板蓝图生成，请配置 GPT/OpenAI-compatible。", code=2)
        llm_config = config_from_env(
            provider=args.model_provider,
            model=args.model_name,
            base_url=args.api_base_url,
            api_key=args.api_key,
        )
        llm_config.timeout = max(5, args.timeout_seconds)
        llm_config.retry_count = max(0, args.retry_count)
        llm_config.stream = False
        provider = build_provider(llm_config)
        feature_hint, meta = harmonize_feature_hint(
            args.name,
            args.product_type,
            args.feature_hint,
            provider=provider,
            require_llm=True,
            min_blueprint_modules=max(0, args.min_blueprint_modules),
        )
        if not feature_hint:
            return _fail(
                str(meta.get("failure_message") or "")
                or "GPT 未生成合格蓝图，请重试；要求至少 8 个不重复的业务模块。",
                meta=meta,
                code=3,
            )
        print(
            "RESULT_JSON:"
            + json.dumps(
                {
                    "feature_hint": feature_hint,
                    "meta": meta,
                },
                ensure_ascii=True,
            ),
            flush=True,
        )
        return 0
    except Exception as exc:
        return _fail(f"GPT 蓝图生成异常：{exc}", code=1)


def _fail(message: str, *, meta: dict | None = None, code: int = 1) -> int:
    print(message, file=sys.stderr, flush=True)
    print(
        "RESULT_JSON:"
        + json.dumps(
            {
                "feature_hint": "",
                "meta": meta or {"feature_hint_source": "llm-error", "requires_gpt": True},
                "message": message,
            },
            ensure_ascii=True,
        ),
        flush=True,
    )
    return code


if __name__ == "__main__":
    sys.exit(main())
