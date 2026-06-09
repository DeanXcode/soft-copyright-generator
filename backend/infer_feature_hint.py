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
    parser.add_argument("--model-provider", default="local-template", help="model provider")
    parser.add_argument("--model-name", default="template-v1", help="model name")
    parser.add_argument("--api-base-url", default="", help="OpenAI-compatible API Base URL")
    parser.add_argument("--api-key", default="", help="API Key")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    llm_config = config_from_env(
        provider=args.model_provider,
        model=args.model_name,
        base_url=args.api_base_url,
        api_key=args.api_key,
    )
    provider = build_provider(llm_config)
    feature_hint, meta = harmonize_feature_hint(
        args.name,
        args.product_type,
        args.feature_hint,
        provider=provider,
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


if __name__ == "__main__":
    sys.exit(main())
