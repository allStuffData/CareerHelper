#!/usr/bin/env python3
"""Discover and smoke-test every model exposed by OpenCode Go.

The script fetches the live model catalog, sends one lightweight request to
each model, and writes `model-summary.md` beside this file. A passing DeepSeek
model is asked to write the report; deterministic Markdown is used as a
fallback if no preferred summarizer works or its report is incomplete.

Prerequisite:
    pip install python-dotenv

Run:
    python test_all_opencode_models.py
"""

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from dotenv import load_dotenv
except ImportError:
    print("Missing python-dotenv. Install it with: pip install python-dotenv")
    sys.exit(1)


SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(SCRIPT_DIR.parent / ".env")

API_KEY = os.getenv("OPENCODE_GO_API_KEY")
BASE_URL = os.getenv("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1").rstrip("/")
SUMMARY_PATH = SCRIPT_DIR / "model-summary.md"
USER_AGENT = "careerhelper-opencode-model-refresh/1.0"
TIMEOUT_SECONDS = 90

if not API_KEY or API_KEY == "your-api-key-here":
    print("ERROR: OPENCODE_GO_API_KEY is not set in the project .env file.")
    sys.exit(1)


# The model catalog returns IDs but no endpoint metadata. Keep the exceptional
# protocols here; newly discovered, unknown IDs default to Chat Completions.
RESPONSES_MODELS = {
    "gpt-5.6-luna",
    "grok-4.5",
    "grok-4.6",
    "muse-spark-1.2-contributor",
    "muse-spark-1.3-contributor",
}
CHAT_MODEL_OVERRIDES = {
    "qwen3.5-plus",
}
MESSAGES_MODEL_PREFIXES = (
    "minimax-",
    "qwen",
    "union-",
)

SUMMARY_MODEL_PREFERENCE = (
    "deepseek-v4-pro",
    "deepseek-v4.1-flash",
    "deepseek-v4-flash",
    "deepseek-flash",
)

SYSTEM_PROMPT = "You are a concise coding assistant."
TEST_PROMPT = "Reply with exactly the word AVAILABLE and nothing else."


def protocol_for_model(model: str) -> str:
    if model in RESPONSES_MODELS:
        return "responses"
    if model in CHAT_MODEL_OVERRIDES:
        return "chat"
    if model.startswith(MESSAGES_MODEL_PREFIXES):
        return "messages"
    return "chat"


def headers_for(protocol: str, session_id: str) -> dict[str, str]:
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "user-agent": USER_AGENT,
        "x-opencode-session": session_id,
    }
    if protocol == "messages":
        headers.update(
            {
                "x-api-key": API_KEY,
                "anthropic-version": "2023-06-01",
            }
        )
    else:
        headers["Authorization"] = f"Bearer {API_KEY}"
    return headers


def request_json(
    endpoint: str,
    *,
    method: str = "POST",
    headers: dict[str, str],
    payload: dict | None = None,
) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(endpoint, data=data, method=method, headers=headers)
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8")
            return {"ok": True, "status": response.status, "body": json.loads(raw)}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = raw[:500].replace("\n", " ")
        return {"ok": False, "status": exc.code, "body": body}
    except (URLError, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        return {"ok": False, "status": "network", "body": str(reason)}


def fetch_models() -> list[str]:
    result = request_json(
        f"{BASE_URL}/models",
        method="GET",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "accept": "application/json",
            "user-agent": USER_AGENT,
        },
    )
    if not result["ok"]:
        raise RuntimeError(f"HTTP {result['status']}: {result['body']}")
    models = sorted(
        {
            item.get("id")
            for item in result["body"].get("data", [])
            if item.get("id")
        }
    )
    if not models:
        raise RuntimeError("OpenCode Go returned an empty model catalog.")
    return models


def settings_for_model(model: str, protocol: str) -> dict:
    if protocol == "responses":
        return {"max_output_tokens": 64}
    if protocol == "messages":
        return {"temperature": 0.3, "max_tokens": 64}
    if model.startswith("kimi-"):
        return {"temperature": 1.0, "top_p": 0.95, "max_tokens": 64}
    return {"temperature": 0.3, "max_tokens": 64}


def payload_for(model: str, protocol: str, user_prompt: str) -> dict:
    settings = settings_for_model(model, protocol)
    if protocol == "responses":
        return {
            "model": model,
            "input": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            **settings,
        }
    if protocol == "messages":
        return {
            "model": model,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": user_prompt}],
            **settings,
        }
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        **settings,
    }


def extract_text(body: dict, protocol: str) -> str:
    if protocol == "messages":
        return "".join(
            block.get("text", "")
            for block in body.get("content", [])
            if block.get("type") == "text"
        )
    if protocol == "responses":
        parts = []
        for item in body.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"}:
                    parts.append(content.get("text", ""))
        return "".join(parts)
    choices = body.get("choices", [])
    if not choices:
        return ""
    return choices[0].get("message", {}).get("content", "") or ""


def extract_usage(body: dict, protocol: str) -> dict[str, int]:
    usage = body.get("usage") or {}
    if protocol == "messages":
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
    elif protocol == "responses":
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
    else:
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
    return {
        "input": input_tokens,
        "output": output_tokens,
        "total": input_tokens + output_tokens,
    }


def error_message(result: dict) -> str:
    body = result["body"]
    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict):
            return str(error.get("message") or error.get("type") or error)
        return str(error)
    return str(body)


def test_model(model: str) -> dict:
    protocol = protocol_for_model(model)
    endpoint = f"{BASE_URL}/{'chat/completions' if protocol == 'chat' else protocol}"
    result = request_json(
        endpoint,
        headers=headers_for(protocol, str(uuid.uuid4())),
        payload=payload_for(model, protocol, TEST_PROMPT),
    )
    record = {
        "model": model,
        "protocol": protocol,
        "working": result["ok"],
        "status": result["status"],
        "response": "",
        "error": "",
        "usage": {"input": 0, "output": 0, "total": 0},
    }
    if result["ok"]:
        record["response"] = extract_text(result["body"], protocol).strip()
        record["usage"] = extract_usage(result["body"], protocol)
    else:
        record["error"] = error_message(result)
    return record


def deterministic_summary(
    results: list[dict],
    generated_at: str,
    writer: str,
    assessment: str = "",
) -> str:
    working = [item for item in results if item["working"]]
    failed = [item for item in results if not item["working"]]
    total_tokens = sum(item["usage"]["total"] for item in results)
    lines = [
        "# OpenCode Go Model Summary",
        "",
        f"Generated: {generated_at}",
        f"Catalog: `{BASE_URL}/models`",
        f"Summary writer: {writer}",
        "",
        "## Results",
        "",
        f"- Models discovered: {len(results)}",
        f"- Working: {len(working)}",
        f"- Non-working: {len(failed)}",
        f"- Verification tokens: {total_tokens}",
        "- Test method: one lightweight request per discovered model",
        "",
    ]
    if assessment:
        lines.extend(["## AI assessment", "", assessment.strip(), ""])
    lines.extend(["## Working models", ""])
    lines.extend(
        f"- `{item['model']}` — {item['protocol']} — HTTP {item['status']}"
        for item in working
    )
    lines.extend(["", "## Non-working models", ""])
    if failed:
        lines.extend(
            f"- `{item['model']}` — {item['protocol']} — HTTP {item['status']}: "
            f"{item['error']}"
            for item in failed
        )
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "The `/models` endpoint is a live catalog and may include stale or temporarily unavailable IDs. A model is classified as working only when its verification request returns HTTP 200.",
            "",
            "Messages models use the direct Anthropic-compatible `/messages` endpoint with `x-api-key`, `anthropic-version`, and `x-opencode-session` headers. Kimi models use Chat Completions with `temperature=1.0` and `top_p=0.95`.",
            "",
        ]
    )
    return "\n".join(lines)


def strip_markdown_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```markdown") and cleaned.endswith("```"):
        return cleaned[len("```markdown") : -3].strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        return cleaned[3:-3].strip()
    return cleaned


def generate_summary_with_model(results: list[dict], generated_at: str) -> tuple[str, str]:
    passing_models = {item["model"] for item in results if item["working"]}
    summary_model = next(
        (model for model in SUMMARY_MODEL_PREFERENCE if model in passing_models),
        None,
    )
    if not summary_model:
        return deterministic_summary(results, generated_at, "deterministic fallback"), "fallback"

    compact_results = [
        {
            "model": item["model"],
            "protocol": item["protocol"],
            "working": item["working"],
            "http_status": item["status"],
            "error": item["error"],
            "tokens": item["usage"]["total"],
        }
        for item in results
    ]
    working_count = sum(item["working"] for item in results)
    failed_count = len(results) - working_count
    prompt = (
        "Write a factual 2-4 sentence assessment of these OpenCode Go smoke-test "
        "results. Mention the exact discovered, working, and non-working counts. "
        "Explain that catalog presence does not guarantee successful inference. "
        "Do not list individual models, add a heading, use a code fence, or invent "
        "causes beyond the supplied errors.\n\n"
        f"Generation time: {generated_at}\n"
        f"Catalog URL: {BASE_URL}/models\n"
        f"Summary writer: {summary_model}\n"
        f"Models discovered: {len(results)}\n"
        f"Working: {working_count}\n"
        f"Non-working: {failed_count}\n"
        f"Results JSON: {json.dumps(compact_results, ensure_ascii=False)}"
    )
    protocol = protocol_for_model(summary_model)
    endpoint = f"{BASE_URL}/{'chat/completions' if protocol == 'chat' else protocol}"
    summary_payload = payload_for(summary_model, protocol, prompt)
    if protocol == "responses":
        summary_payload["max_output_tokens"] = 512
    else:
        summary_payload["max_tokens"] = 512

    response = request_json(
        endpoint,
        headers=headers_for(protocol, str(uuid.uuid4())),
        payload=summary_payload,
    )
    if not response["ok"]:
        writer = f"deterministic fallback; {summary_model} summary call failed"
        return deterministic_summary(results, generated_at, writer), "fallback"

    assessment = strip_markdown_fence(extract_text(response["body"], protocol))
    if not assessment:
        writer = f"deterministic fallback; {summary_model} returned an empty assessment"
        return deterministic_summary(results, generated_at, writer), "fallback"
    return (
        deterministic_summary(results, generated_at, summary_model, assessment),
        summary_model,
    )


def main() -> None:
    try:
        models = fetch_models()
    except Exception as exc:
        print(f"ERROR: Could not fetch the OpenCode Go model list: {exc}")
        sys.exit(1)

    print("=" * 72)
    print("OpenCode Go model refresh")
    print(f"Catalog: {BASE_URL}/models")
    print(f"Discovered: {len(models)} models")
    print("One verification request will be sent to each model.")
    print("=" * 72)

    results = []
    for index, model in enumerate(models, 1):
        result = test_model(model)
        results.append(result)
        if result["working"]:
            detail = result["response"].replace("\n", " ")[:80] or "HTTP 200"
            print(
                f"[{index:02d}/{len(models):02d}] PASS {model} "
                f"[{result['protocol']}] — {detail}"
            )
        else:
            print(
                f"[{index:02d}/{len(models):02d}] FAIL {model} "
                f"[{result['protocol']}] — HTTP {result['status']}: {result['error']}"
            )

    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")
    markdown, writer = generate_summary_with_model(results, generated_at)
    SUMMARY_PATH.write_text(markdown, encoding="utf-8")

    working = sum(item["working"] for item in results)
    failed = len(results) - working
    tokens = sum(item["usage"]["total"] for item in results)
    print("=" * 72)
    print(f"Working: {working}/{len(results)}")
    print(f"Non-working: {failed}/{len(results)}")
    print(f"Verification tokens: {tokens}")
    print(f"Summary writer: {writer}")
    print(f"Report: {SUMMARY_PATH}")
    print("=" * 72)


if __name__ == "__main__":
    main()
