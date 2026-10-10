from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from .reward_audit import evaluate_reward_audit_cases


DEFAULT_REWARD_AUDIT_FIXTURE = Path("examples/evals/reward_audit_cases.json")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run small eval fixtures for reward-surface audit heuristics.")
    parser.add_argument(
        "--fixture",
        default=str(DEFAULT_REWARD_AUDIT_FIXTURE),
        help="Path to a reward audit fixture JSON list.",
    )
    parser.add_argument("--json", action="store_true", help="Print full JSON results.")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        results = evaluate_reward_audit_cases(args.fixture)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for result in results:
            status = "PASS" if result["passed"] else "FAIL"
            print(f"{status} {result['name']}: expected={result['expected_risk']} actual={result['actual_risk']}")
    return 0 if all(result["passed"] for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
