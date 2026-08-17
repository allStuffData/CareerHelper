#!/usr/bin/env python3
"""
Test every model currently available through OpenCode Go.

The model list is fetched from OpenCode Go's own `/models` endpoint at runtime,
so this script does not test models from the general OpenCode/Zen catalog and
does not need a hard-coded list that can become stale.

OpenCode Go exposes models through three compatible API protocols:
    - OpenAI Chat Completions: /chat/completions
    - OpenAI Responses:        /responses
    - Anthropic Messages:      /messages

Prerequisites:
    pip install openai anthropic python-dotenv

Setup:
    1. Sign in to https://opencode.ai/zen and subscribe to OpenCode Go.
    2. Copy your API key.
    3. Put it in the project .env file:
           OPENCODE_GO_API_KEY=sk-...
    4. Run this script:
           python test_deepseek_v4_pro.py
"""

import os
import sys
from pathlib import Path

# --- Load .env ---
try:
    from dotenv import load_dotenv
except ImportError:
    print("Missing python-dotenv. Install it with: pip install python-dotenv")
    sys.exit(1)

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(env_path)

API_KEY = os.getenv("OPENCODE_GO_API_KEY")
if not API_KEY or API_KEY == "your-api-key-here":
    print("ERROR: OPENCODE_GO_API_KEY is not set.")
    print("Put your OpenCode Go API key in the .env file, then re-run.")
    sys.exit(1)

BASE_URL = os.getenv("OPENCODE_GO_BASE_URL", "https://opencode.ai/zen/go/v1")

# --- API clients ---
try:
    from openai import OpenAI
except ImportError:
    print("Missing openai. Install it with: pip install openai")
    sys.exit(1)

try:
    from anthropic import Anthropic
except ImportError:
    print("Missing anthropic. Install it with: pip install anthropic")
    sys.exit(1)

openai_client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
anthropic_client = Anthropic(api_key=API_KEY, base_url=BASE_URL)

# OpenCode documents the protocol used by each Go model. Unknown future models
# default to chat completions, which is the most common OpenAI-compatible API.
RESPONSES_MODELS = {
    "gpt-5.6-luna",
    "grok-4.5",
}
MESSAGE_MODEL_PREFIXES = (
    "minimax-",
    "qwen",
)

# --- Test prompts ---
TEST_PROMPTS = [
    {
        "system": "You are a helpful coding assistant. Answer concisely.",
        "user": "Write a Python function that checks if a string is a palindrome. Return only the code, no explanation.",
    },
    {
        "system": "You are a concise assistant.",
        "user": "In one sentence, explain what a linked list is.",
    },
    {
        "system": "You are a senior software engineer. Be terse.",
        "user": "What is the time complexity of quicksort in the worst case? One line.",
    },
]


def get_models() -> list[str]:
    """Return the current model IDs from the OpenCode Go catalog only."""
    response = openai_client.models.list()
    model_ids = sorted({model.id for model in response.data if model.id})
    if not model_ids:
        raise RuntimeError("OpenCode Go returned no available models.")
    return model_ids


def protocol_for_model(model: str) -> str:
    """Return the API protocol OpenCode Go uses for a model."""
    if model in RESPONSES_MODELS:
        return "responses"
    if model.startswith(MESSAGE_MODEL_PREFIXES):
        return "messages"
    return "chat"


def usage_dict(input_tokens: int, output_tokens: int) -> dict:
    """Normalize usage fields across the three API response formats."""
    return {
        "prompt_tokens": input_tokens,
        "completion_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }


def run_chat_prompt(model: str, system_msg: str, user_msg: str) -> dict:
    response = openai_client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.3,
        max_tokens=512,
    )

    choice = response.choices[0]
    usage = response.usage
    return {
        "content": choice.message.content,
        "finish_reason": choice.finish_reason,
        "model": response.model,
        "usage": usage_dict(usage.prompt_tokens, usage.completion_tokens)
        if usage
        else None,
    }


def run_responses_prompt(model: str, system_msg: str, user_msg: str) -> dict:
    response = openai_client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        max_output_tokens=512,
    )

    usage = response.usage
    return {
        "content": response.output_text,
        "finish_reason": "completed",
        "model": response.model,
        "usage": usage_dict(usage.input_tokens, usage.output_tokens)
        if usage
        else None,
    }


def run_messages_prompt(model: str, system_msg: str, user_msg: str) -> dict:
    response = anthropic_client.messages.create(
        model=model,
        system=system_msg,
        messages=[{"role": "user", "content": user_msg}],
        temperature=0.3,
        max_tokens=512,
    )

    text_parts = [
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text"
    ]
    usage = response.usage
    return {
        "content": "".join(text_parts),
        "finish_reason": response.stop_reason,
        "model": response.model,
        "usage": usage_dict(usage.input_tokens, usage.output_tokens)
        if usage
        else None,
    }


def run_prompt(model: str, system_msg: str, user_msg: str) -> dict:
    """Send one prompt through the protocol assigned to this Go model."""
    protocol = protocol_for_model(model)
    if protocol == "responses":
        return run_responses_prompt(model, system_msg, user_msg)
    if protocol == "messages":
        return run_messages_prompt(model, system_msg, user_msg)
    return run_chat_prompt(model, system_msg, user_msg)


def main() -> None:
    try:
        models = get_models()
    except Exception as exc:
        print(f"ERROR: Could not fetch the OpenCode Go model list: {exc}")
        sys.exit(1)

    print("=" * 72)
    print("OpenCode Go — all available models test")
    print(f"API:    {BASE_URL}")
    print(f"Models: {len(models)} (discovered from {BASE_URL}/models)")
    print("=" * 72)
    print("Model IDs:")
    for model in models:
        print(f"  - {model} [{protocol_for_model(model)}]")

    total_prompt = 0
    total_completion = 0
    successful = 0
    failed = 0

    for model_index, model in enumerate(models, 1):
        protocol = protocol_for_model(model)
        print("\n" + "=" * 72)
        print(f"Model {model_index}/{len(models)}: {model} [{protocol}]")
        print("=" * 72)

        model_successful = 0
        for prompt_index, prompt in enumerate(TEST_PROMPTS, 1):
            print(f"\n--- Test {prompt_index}/{len(TEST_PROMPTS)} ---")
            print(f"User: {prompt['user']}")

            try:
                result = run_prompt(model, prompt["system"], prompt["user"])
            except Exception as exc:
                failed += 1
                print(f"ERROR: {exc}")
                continue

            successful += 1
            model_successful += 1
            print(f"Response: {result['content']}")
            if result["usage"]:
                usage = result["usage"]
                total_prompt += usage["prompt_tokens"]
                total_completion += usage["completion_tokens"]
                print(
                    f"Tokens:   prompt={usage['prompt_tokens']}, "
                    f"completion={usage['completion_tokens']}, "
                    f"total={usage['total_tokens']} "
                    f"[finish: {result['finish_reason']}]"
                )

        print(
            f"\nModel summary: {model_successful}/{len(TEST_PROMPTS)} "
            "tests succeeded."
        )

    print("\n" + "=" * 72)
    print(f"Models tested: {len(models)}")
    print(f"Successful requests: {successful}")
    print(f"Failed requests: {failed}")
    print(
        f"Total tokens — prompt: {total_prompt}, "
        f"completion: {total_completion}, "
        f"total: {total_prompt + total_completion}"
    )
    print("Cost estimate omitted because OpenCode Go pricing differs by model.")
    print("Done.")
    print("=" * 72)


if __name__ == "__main__":
    main()
