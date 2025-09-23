#!/usr/bin/env python3
"""Diagnose Azure OpenAI connectivity and configuration issues."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict

try:
    import openai  # type: ignore
    from openai import AzureOpenAI  # type: ignore
except ImportError:  # pragma: no cover - diagnostic
    openai = None  # type: ignore
    AzureOpenAI = None  # type: ignore


def _status(name: str, value: str | None, redact: bool = False) -> str:
    if not value:
        return f"{name}: ❌ missing"
    if redact and len(value) > 6:
        truncated = value[:3] + "..." + value[-3:]
        return f"{name}: ✅ set ({truncated})"
    return f"{name}: ✅ {value}"


def _print_header(title: str) -> None:
    print("\n" + title)
    print("-" * len(title))


def diagnose() -> int:
    _print_header("Environment Variables")
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME")
    model_alias = os.environ.get("AZURE_OPENAI_MODEL")
    api_version = os.environ.get("OPENAI_API_VERSION")

    print(_status("AZURE_OPENAI_API_KEY", api_key, redact=True))
    print(_status("AZURE_OPENAI_ENDPOINT", endpoint))
    print(_status("AZURE_OPENAI_DEPLOYMENT_NAME", deployment or "(using default)"))
    print(_status("AZURE_OPENAI_MODEL", model_alias or "(using default)"))
    print(_status("OPENAI_API_VERSION", api_version or "(using default)"))

    _print_header("openai SDK")
    if openai is None or AzureOpenAI is None:
        print("❌ 未安装 openai 库。请运行 `uv pip install \"openai>=1.14\"`.")
        return 1

    print(f"✅ openai 版本: {getattr(openai, '__version__', 'unknown')}")
    print("✅ 检测到 AzureOpenAI 客户端")

    if not api_key or not endpoint:
        print("❌ 缺少必需的环境变量，跳过 API 调用测试。")
        return 1

    api_version = api_version or "2025-01-01-preview"
    deployment = deployment or "gpt-4o-new"

    _print_header("API Connectivity")
    try:
        client = AzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )
        print("✅ 成功创建 Azure OpenAI 客户端")
    except Exception as exc:  # pragma: no cover - diagnostic script
        print("❌ 创建客户端失败:")
        print(f"   {exc}")
        return 1

    payload: Dict[str, Any] = {
        "model": deployment,
        "messages": [
            {"role": "system", "content": "You are a connectivity probe."},
            {"role": "user", "content": "Reply with the word 'pong'."},
        ],
        "max_tokens": 5,
        "temperature": 0,
    }

    try:
        response = client.chat.completions.create(**payload)
        content = response.choices[0].message.content if response.choices else None
        print("✅ API 调用成功")
        print(f"   响应: {json.dumps(content, ensure_ascii=False)}")
        return 0
    except Exception as exc:  # pragma: no cover - diagnostic script
        print("❌ API 调用失败:")
        print(f"   {exc}")
        if hasattr(exc, "response") and getattr(exc.response, "status_code", None):
            print(f"   状态码: {exc.response.status_code}")
        return 1


if __name__ == "__main__":
    sys.exit(diagnose())
