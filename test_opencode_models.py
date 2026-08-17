#!/usr/bin/env python3
"""
Test script for DeepSeek V4 Pro via OpenCode Zen Go.

OpenCode Go gives you access to curated open coding models through an
OpenAI-compatible chat completions endpoint. This script sends a few
test prompts to DeepSeek V4 Pro and prints the results.

Endpoint:     https://opencode.ai/zen/go/v1/chat/completions
Model ID:     deepseek-v4-pro
Pricing:      $0.435/M input | $0.87/M output | $0.003625/M cached read
Usage/month:  ~17,150 requests (included in Go subscription)

Prerequisites:
    pip install openai python-dotenv

Setup:
    1. Sign in to https://opencode.ai/zen and subscribe to OpenCode Go.
    2. Copy your API key.
    3. Paste it into the .env file in this directory:
           OPENCODE_GO_API_KEY=sk-...
    4. Run this script:
           python test_deepseek_v4_pro.py
"""

import json
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

# --- Try importing openai ---
try:
    from openai import OpenAI
except ImportError:
    print("Missing openai. Install it with: pip install openai")
    sys.exit(1)

# --- Client ---
client = OpenAI(
    api_key=API_KEY,
    base_url="https://opencode.ai/zen/go/v1",
)

MODEL = "deepseek-v4-pro"

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


def run_prompt(system_msg: str, user_msg: str) -> dict:
    """Send a single chat completion and return the parsed result."""
    response = client.chat.completions.create(
        model=MODEL,
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
        "usage": {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
        } if usage else None,
    }


def main():
    print("=" * 60)
    print(f"DeepSeek V4 Pro — OpenCode Zen Go Test")
    print(f"Model:  {MODEL}")
    print(f"API:    https://opencode.ai/zen/go/v1")
    print("=" * 60)

    total_prompt = 0
    total_completion = 0

    for i, prompt in enumerate(TEST_PROMPTS, 1):
        print(f"\n--- Test {i}/{len(TEST_PROMPTS)} ---")
        print(f"User: {prompt['user']}")

        try:
            result = run_prompt(prompt["system"], prompt["user"])
        except Exception as e:
            print(f"ERROR: {e}")
            continue

        print(f"Response: {result['content']}")
        if result["usage"]:
            u = result["usage"]
            total_prompt += u["prompt_tokens"]
            total_completion += u["completion_tokens"]
            print(f"Tokens:   prompt={u['prompt_tokens']}, "
                  f"completion={u['completion_tokens']}, "
                  f"total={u['total_tokens']}  "
                  f"[finish: {result['finish_reason']}]")

    # --- Cost estimate ---
    input_cost = (total_prompt / 1_000_000) * 0.435
    output_cost = (total_completion / 1_000_000) * 0.87
    total_cost = input_cost + output_cost

    print("\n" + "=" * 60)
    print(f"Total tokens — prompt: {total_prompt}, completion: {total_completion}")
    print(f"Estimated cost: ${total_cost:.6f} "
          f"(input: ${input_cost:.6f}, output: ${output_cost:.6f})")
    print("Done.")
    print("=" * 60)


if __name__ == "__main__":
    main()
