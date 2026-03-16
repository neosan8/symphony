from __future__ import annotations

import argparse
import sys

from symphony_runtime.config import SymphonyConfig
from symphony_runtime.daemon import SymphonyRuntime
from symphony_runtime.human_gate import VALID_HUMAN_GATE_DECISIONS
from symphony_runtime.human_gate_store import (
    load_human_gate_record_from_ref,
    scan_pending_human_gate_runs,
    scan_ready_for_pr_runs,
)


def build_runtime() -> SymphonyRuntime:
    return SymphonyRuntime(config=SymphonyConfig.default())

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="symphony_v2")
    subparsers = parser.add_subparsers(dest="command")

    human_gate_parser = subparsers.add_parser("human-gate")
    human_gate_subparsers = human_gate_parser.add_subparsers(dest="human_gate_command", required=True)

    human_gate_subparsers.add_parser("list")

    show_parser = human_gate_subparsers.add_parser("show")
    show_parser.add_argument("--run", required=True)

    show_package_parser = human_gate_subparsers.add_parser("show-package")
    show_package_parser.add_argument("--run", required=True)

    apply_parser = human_gate_subparsers.add_parser("apply")
    apply_parser.add_argument("--run", required=True)
    apply_parser.add_argument("--decision", choices=sorted(VALID_HUMAN_GATE_DECISIONS), required=True)
    apply_parser.add_argument("--note", required=True)

    ready_for_pr_parser = subparsers.add_parser("ready-for-pr")
    ready_for_pr_subparsers = ready_for_pr_parser.add_subparsers(dest="ready_for_pr_command", required=True)
    ready_for_pr_subparsers.add_parser("list")
    ready_for_pr_create_parser = ready_for_pr_subparsers.add_parser("create")
    ready_for_pr_create_parser.add_argument("--run", required=True)

    pr_opened_parser = subparsers.add_parser("pr-opened")
    pr_opened_subparsers = pr_opened_parser.add_subparsers(dest="pr_opened_command", required=True)
    pr_opened_refresh_parser = pr_opened_subparsers.add_parser("refresh-reviews")
    pr_opened_refresh_parser.add_argument("--run", required=True)
    pr_opened_show_parser = pr_opened_subparsers.add_parser("show-reviews")
    pr_opened_show_parser.add_argument("--run", required=True)
    pr_opened_show_diff_parser = pr_opened_subparsers.add_parser("show-review-diff")
    pr_opened_show_diff_parser.add_argument("--run", required=True)
    pr_opened_ack_parser = pr_opened_subparsers.add_parser("acknowledge-reviews")
    pr_opened_ack_parser.add_argument("--run", required=True)
    pr_opened_ack_parser.add_argument(
        "--state",
        choices=("addressed", "needs-follow-up", "reviewed"),
        required=True,
    )
    pr_opened_ack_parser.add_argument("--note", default="")
    pr_opened_prepare_merge_parser = pr_opened_subparsers.add_parser("prepare-merge")
    pr_opened_prepare_merge_parser.add_argument("--run", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    runtime = build_runtime()
    runtime.ensure_workspace_roots()
    args = build_parser().parse_args(argv)

    if args.command is None:
        print(f"Symphony runtime ready: {runtime.config.runs_root}")
        return 0

    if args.command == "human-gate" and args.human_gate_command == "list":
        scan_result = scan_pending_human_gate_runs(runtime.config)
        print("RUN\tISSUE\tBRANCH\tCOMMIT")
        for context in scan_result.pending_runs:
            run_name = context.run_root.name if context.run_root is not None else "unknown"
            print(f"{run_name}\t{context.issue_key}\t{context.branch}\t{context.commit_sha}")
        for issue in scan_result.issues:
            print(
                f"WARNING: Skipped invalid Human Gate run {issue.run_root.name}: {issue.message}",
                file=sys.stderr,
            )
        return 0

    if args.command == "human-gate" and args.human_gate_command == "show":
        record = load_human_gate_record_from_ref(runtime.config, args.run)
        run_name = record.run_root.name if record.run_root is not None else args.run
        print(f"RUN: {run_name}")
        print(f"ISSUE: {record.issue_key}")
        print(f"BRANCH: {record.branch}")
        print(f"COMMIT: {record.commit_sha}")
        print(f"DECISION: {record.decision}")
        print(f"NOTE: {record.note}")
        print(f"NEXT_ACTION: {record.next_action}")
        return 0

    if args.command == "human-gate" and args.human_gate_command == "show-package":
        package = runtime.get_human_gate_package_from_run(args.run)
        print(f"RUN: {package['run_ref']}")
        print(f"ISSUE: {package['issue_key']}")
        print(f"BRANCH: {package['branch']}")
        print(f"RECOMMENDATION: {package['recommendation']}")
        print(f"VERIFICATION: {package['verification_path']}")
        print(f"REVIEW: {package['review_path']}")
        print(f"BLOCKING_REVIEWS: {package['blocking_review_count']}")
        print(f"UNRESOLVED_FINDINGS: {package['unresolved_findings_count']}")
        print(f"ACKNOWLEDGEMENT: {package['acknowledgement_state']}")
        print(f"PACKAGE: {package['package_markdown_path']}")
        return 0

    if args.command == "human-gate" and args.human_gate_command == "apply":
        runtime.apply_human_gate_decision_from_run(args.run, args.decision, args.note)
        return 0

    if args.command == "ready-for-pr" and args.ready_for_pr_command == "list":
        scan_result = scan_ready_for_pr_runs(runtime.config)
        print("RUN\tISSUE\tBRANCH\tCOMMIT")
        for record in scan_result.ready_runs:
            run_name = record.run_root.name if record.run_root is not None else "unknown"
            print(f"{run_name}\t{record.issue_key}\t{record.branch}\t{record.commit_sha}")
        for issue in scan_result.issues:
            print(
                f"WARNING: Skipped invalid ready-for-pr run {issue.run_root.name}: {issue.message}",
                file=sys.stderr,
            )
        return 0

    if args.command == "ready-for-pr" and args.ready_for_pr_command == "create":
        print(runtime.create_pr_from_run(args.run))
        return 0

    if args.command == "pr-opened" and args.pr_opened_command == "refresh-reviews":
        runtime.refresh_pr_reviews_from_run(args.run)
        print(f"Refreshed PR reviews for {args.run}")
        return 0

    if args.command == "pr-opened" and args.pr_opened_command == "show-reviews":
        review_status = runtime.get_pr_review_status_from_run(args.run)
        print(f"RUN: {review_status['run_ref']}")
        print(f"BLOCKING_REVIEWS: {review_status['blocking_review_count']}")
        print(f"UNRESOLVED_FINDINGS: {review_status['unresolved_findings_count']}")
        print(f"TRIAGE: {review_status['review_triage_path']}")
        print(f"FINDINGS: {review_status['review_findings_path']}")
        return 0

    if args.command == "pr-opened" and args.pr_opened_command == "show-review-diff":
        review_status = runtime.get_pr_review_status_from_run(args.run)
        print(f"RUN: {review_status['run_ref']}")
        print(f"BLOCKING_REVIEWS: {review_status['blocking_review_count']}")
        print(f"UNRESOLVED_FINDINGS: {review_status['unresolved_findings_count']}")
        print(f"NEW_FINDINGS: {review_status['newly_introduced_findings_count']}")
        print(f"RESOLVED_FINDINGS: {review_status['resolved_findings_count']}")
        print(f"DIFF: {review_status['review_diff_path']}")
        return 0

    if args.command == "pr-opened" and args.pr_opened_command == "acknowledge-reviews":
        runtime.acknowledge_pr_reviews_from_run(args.run, args.state, args.note)
        print(f"Acknowledged PR reviews for {args.run} as {args.state}")
        return 0

    if args.command == "pr-opened" and args.pr_opened_command == "prepare-merge":
        merge_preparation = runtime.prepare_merge_from_run(args.run)
        print(f"RUN: {merge_preparation['run_ref']}")
        print(f"MERGE_PREPARATION: {merge_preparation['merge_preparation_path']}")
        return 0

    raise ValueError(f"Unsupported command: {args}")
