"""Deploy Gate agent: reads diff, scores risk, decides deploy/hold."""

import argparse
import asyncio
import subprocess
import sys

from agents.lib import gh, kill_switch, prompts
from agents.lib.anthropic import run_agent


async def assess(sha: str) -> str:
    """Returns 'deploy' | 'deploy_and_watch' | 'hold'."""
    repo = gh.repo()

    diff_stat = subprocess.run(
        ["git", "diff", "--stat", f"{sha}~1..{sha}"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()

    diff_content = subprocess.run(
        ["git", "diff", f"{sha}~1..{sha}"],
        capture_output=True, text=True, check=False,
    ).stdout[:4096]

    deploy_runs = list(repo.get_workflow("deploy-prod.yml").get_runs()[:5])
    recent = "\n".join(
        f"- {r.created_at}: {r.conclusion or r.status}"
        for r in deploy_runs
    )

    user_prompt = (
        f"DIFF_STAT:\n{diff_stat}\n\n"
        f"DIFF_CONTENT:\n{diff_content}\n\n"
        f"RECENT_DEPLOYS:\n{recent}"
    )

    system = prompts.load("deploy_gate")
    result = await run_agent(prompt=user_prompt, system=system, max_turns=3, allowed_tools=[])
    text = _extract_text(result.messages)
    return _parse_decision(text)


def _extract_text(messages: list[object]) -> str:
    parts: list[str] = []
    for m in messages:
        if isinstance(m, dict) and m.get("type") == "text" and "text" in m:
            parts.append(str(m["text"]))
        elif hasattr(m, "text"):
            parts.append(str(m.text))
    return "\n".join(parts).strip()


def _parse_decision(text: str) -> str:
    first = text.splitlines()[0] if text else ""
    if "DECISION: DEPLOY_AND_WATCH" in first:
        return "deploy_and_watch"
    if "DECISION: DEPLOY" in first:
        return "deploy"
    if "DECISION: HOLD" in first:
        return "hold"
    return "deploy"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agents.deploy_gate")
    parser.add_argument("--sha", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    kill_switch.exit_if_paused()
    decision = asyncio.run(assess(args.sha))
    print(f"deploy-gate: {decision}")
    if decision == "hold":
        print("HOLD — deployment blocked by deploy gate. Review the diff manually.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
