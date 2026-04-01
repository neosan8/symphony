import subprocess
from pathlib import Path


def build_codex_command(worktree_path: Path, context_packet_path: Path) -> list[str]:
    return [
        "codex",
        "exec",
        "--cwd",
        str(worktree_path),
        f"Read {context_packet_path} and complete the issue with verification artifacts.",
    ]


def run_codex_command(
    command: list[str],
    worktree_path: Path,
    stdout_path: Path,
    stderr_path: Path,
) -> int:
    with stdout_path.open("w") as stdout_file, stderr_path.open("w") as stderr_file:
        process = subprocess.run(
            command,
            cwd=worktree_path,
            stdout=stdout_file,
            stderr=stderr_file,
        )
    return process.returncode
