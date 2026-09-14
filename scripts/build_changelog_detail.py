# -*- coding: utf-8 -*-
"""从 git 历史生成详细更新日志骨架，并保留人工补充的说明。

设计目标：
  - 提交行由脚本从 `git log` 生成，不靠人工誊写，避免漏记；
  - 人工只需在提交行下缩进两格写 `  - 说明：…`，重新生成时按短哈希归属保留；
  - 输出稳定：同一段 git 历史重复运行结果一致，可直接提交。
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "docs" / "CHANGELOG_DETAIL.md"

TYPE_LABELS = {
    "feat": "新增",
    "fix": "修复",
    "docs": "文档",
    "chore": "杂项",
    "perf": "性能",
    "refactor": "重构",
    "test": "测试",
    "build": "构建",
    "ci": "集成",
}

COMMIT_RE = re.compile(r"^- `([0-9a-f]{7,})`")
NOTE_RE = re.compile(r"^ {2}- (.+)$")
SUBJECT_RE = re.compile(r"^(?P<type>[a-z]+)(?:\([^)]*\))?!?:\s*(?P<text>.+)$")

HEADER = """# 详细更新日志

> 这里按提交逐条记录项目发生过的每一次改动，用来查"某个小改动是哪次做的"。
> **面向"这一版有什么变化"的摘要见 [重要变更](CHANGELOG.md)**，面向当前能力见 [文档总入口](README.md)。
>
> 骨架由 `python scripts/build_changelog_detail.py` 从 `git log` 生成，**不要手工调整提交行**；
> 需要补充原因、影响或验证结果时，在对应提交下方缩进两格写 `  - 说明：…`，重新生成会按短哈希保留。
> 本文件只包含**已提交**的历史，工作区未提交的改动不会出现在这里。
"""


def run_git_log(rev: str) -> list[dict[str, str]]:
    result = subprocess.run(
        ["git", "log", "--format=%h%x1f%ad%x1f%s", "--date=short", rev],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        raise SystemExit(f"git log 失败：{result.stderr.strip()}")
    commits = []
    for line in result.stdout.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        short, date, subject = parts
        commits.append({"short": short, "date": date, "subject": subject})
    return commits


def split_subject(subject: str) -> tuple[str, str]:
    """把 `feat: xxx` 拆成（中文标签, 正文）；没有约定前缀时标签为空。"""
    match = SUBJECT_RE.match(subject)
    if not match:
        return "", subject
    label = TYPE_LABELS.get(match.group("type"), match.group("type"))
    return label, match.group("text")


def load_notes(path: Path) -> dict[str, list[str]]:
    """读取上次生成时人工补充的说明，按短哈希归属。"""
    notes: dict[str, list[str]] = {}
    if not path.exists():
        return notes
    current = None
    for line in path.read_text(encoding="utf-8").splitlines():
        commit = COMMIT_RE.match(line)
        if commit:
            current = commit.group(1)
            continue
        note = NOTE_RE.match(line)
        if note and current:
            notes.setdefault(current, []).append(note.group(1).rstrip())
    return notes


def render(commits: list[dict[str, str]], notes: dict[str, list[str]]) -> str:
    lines = [HEADER.rstrip(), ""]
    if commits:
        dates = sorted({c["date"] for c in commits})
        lines += [
            f"共 {len(commits)} 条提交，覆盖 {dates[0]} 至 {dates[-1]}。",
            "",
        ]
    current_date = None
    for commit in commits:
        if commit["date"] != current_date:
            if current_date is not None:
                lines.append("")
            current_date = commit["date"]
            lines += [f"## {current_date}", ""]
        label, text = split_subject(commit["subject"])
        prefix = f"**{label}** " if label else ""
        lines.append(f"- `{commit['short']}` {prefix}{text}")
        for note in notes.get(commit["short"], []):
            lines.append(f"  - {note}")
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="从 git 历史生成 docs/CHANGELOG_DETAIL.md")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="输出路径")
    parser.add_argument("--rev", default="HEAD", help="git 修订范围，默认 HEAD")
    args = parser.parse_args()

    out = Path(args.out)
    commits = run_git_log(args.rev)
    notes = load_notes(out)
    text = render(commits, notes)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")

    kept = sum(len(v) for v in notes.values())
    print(f"已生成 {out.relative_to(ROOT)}：{len(commits)} 条提交，保留人工说明 {kept} 条")


if __name__ == "__main__":
    if sys.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
    main()
