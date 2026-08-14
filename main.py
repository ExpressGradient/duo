import argparse
import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from openai_codex import ApprovalMode, Codex, CodexConfig, Sandbox

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "feedback": {"type": "string"},
    },
    "required": ["passed", "feedback"],
    "additionalProperties": False,
}


def package_version() -> str:
    try:
        return version("duo")
    except PackageNotFoundError:
        return "0.1.0"

VERIFIER_PROMPT = """You are a private verifier. Study the task and repository,
then form a concrete view of the correct final state: required behavior,
constraints, likely failure modes, counterexamples, and how to verify it. Write
your current view concisely for later reviews; revise it when new evidence
warrants. Do not modify project files or implement the solution. You may use
disposable scratch code under /tmp for investigation. Do not mention or assume
another agent.

User task:
{task}
"""

REVIEW_PROMPT = """Reassess the task's intent, the repository, and the current
solution. Update your view of the correct final state when evidence warrants.
Your goal is to find every concrete fault you can. Missing any defect is a
failed review. Do not stop after one finding or treat a fix for one finding as
evidence that other requirements work. On every review, recheck the whole task
against the actual code using relevant tests, probes, boundary cases,
regressions, and counterexamples. Look especially for missing behavior, wrong
behavior, and requirements that tests do not cover. Do not modify files in the
project or implement a solution. You may create and run disposable probes or
scratch code under /tmp to investigate and test it.

Set passed true only with positive evidence that you could not find a remaining
fault and the solution is complete; use empty feedback. Otherwise, set passed
false and give only actionable feedback: what is missing, wrong, or failing;
the evidence or counterexample; and what the final state requires. Do not
mention another agent or the review process."""


def complete(thread, prompt, **kwargs) -> str:
    response = thread.run(prompt, **kwargs).final_response
    if response is None:
        raise RuntimeError("Codex turn completed without a final response")
    return response


def run(args) -> bool:
    with Codex(config=CodexConfig(cwd=args.workdir)) as codex:
        verifier = codex.thread_start(
            model=args.verifier_model,
            approval_mode=ApprovalMode.auto_review,
            sandbox=Sandbox.full_access,
        )
        print("\n--- Verifier · understand task ---")
        print(
            complete(
                verifier,
                VERIFIER_PROMPT.format(task=args.prompt),
                effort=args.verifier_effort,
            )
        )

        developer = codex.thread_start(
            model=args.developer_model,
            approval_mode=ApprovalMode.auto_review,
            sandbox=Sandbox.full_access,
        )
        developer_prompt = args.prompt

        for attempt in range(1, args.max_iterations + 1):
            print(f"\n--- Developer · {attempt}/{args.max_iterations} ---")
            print(complete(developer, developer_prompt, effort=args.developer_effort))

            print(f"\n--- Verifier · review {attempt}/{args.max_iterations} ---")
            verdict_output = complete(
                verifier,
                REVIEW_PROMPT,
                effort=args.verifier_effort,
                output_schema=VERDICT_SCHEMA,
            )
            print(verdict_output)
            verdict = json.loads(verdict_output)
            if verdict["passed"]:
                print("Passed")
                return True

            feedback = verdict["feedback"].strip()
            if not feedback:
                raise RuntimeError("Verifier rejected the solution without feedback")
            print(feedback)
            developer_prompt = feedback

        print("Failed: iteration limit reached")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Have a developer implement a task and a private verifier check it.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""workflow:
  1. The developer receives the task and edits the project.
  2. The verifier reads the result, tests it, and returns a JSON verdict.
  3. Rejection feedback becomes the developer's next task.

The verifier never edits project files, but may use /tmp for probes.
Exit 0: verifier passed. Exit 1: iteration limit reached.

examples:
  duo "add pagination" -C /path/to/project
  duo -f task.md -C /path/to/project --max-iterations 6
""",
    )
    prompt = parser.add_mutually_exclusive_group(required=True)
    prompt.add_argument("prompt", nargs="?", help="task sent to the developer first")
    prompt.add_argument(
        "-f",
        "--prompt-file",
        type=Path,
        help="read the task from a file; useful for long tasks",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {package_version()}")
    parser.add_argument(
        "-n",
        "--max-iterations",
        default=3,
        type=int,
        help="maximum developer → verifier cycles (default: 3)",
    )
    parser.add_argument(
        "--verifier-model", default="gpt-5.6-terra", help="read-only verifier model"
    )
    parser.add_argument(
        "--developer-model", default="gpt-5.6-terra", help="developer model"
    )
    parser.add_argument(
        "--verifier-effort", default="high", help="verifier reasoning effort"
    )
    parser.add_argument(
        "--developer-effort", default="high", help="developer reasoning effort"
    )
    parser.add_argument(
        "-C",
        "--workdir",
        default=".",
        help="project directory to edit and review (default: current directory)",
    )
    args = parser.parse_args()

    if args.max_iterations < 1:
        parser.error("--max-iterations must be at least 1")
    if args.prompt_file:
        args.prompt = args.prompt_file.read_text()

    return 0 if run(args) else 1


if __name__ == "__main__":
    raise SystemExit(main())
