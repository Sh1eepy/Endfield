"""检查项目 Markdown 中的本地相对链接，不访问网络。"""
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
SKIP_DIRS = {".git", "node_modules", "endfield_kb", "Claude-Code-Frontend-Design-Toolkit-main",
             "taste-skill-main", "logs", "tmp", ".tmp", "output", "web"}

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")


def markdown_files():
    for path in ROOT.rglob("*.md"):
        if not any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            yield path


def local_target(raw: str) -> str | None:
    value = raw.strip()
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1]
    if value.startswith(("http://", "https://", "mailto:", "#", "/")):
        return None
    value = value.split("#", 1)[0]
    return value or None


def main() -> None:
    broken = []
    checked = 0
    for doc in markdown_files():
        text = doc.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            target = local_target(match.group(1))
            if not target:
                continue
            checked += 1
            resolved = (doc.parent / target).resolve()
            if not resolved.is_relative_to(ROOT) or not resolved.exists():
                line = text.count("\n", 0, match.start()) + 1
                broken.append(f"{doc.relative_to(ROOT)}:{line} -> {target}")
    if broken:
        print("文档链接检查失败：")
        print("\n".join(broken))
        raise SystemExit(1)
    print(f"文档链接检查通过：{checked} 个本地链接")


if __name__ == "__main__":
    main()
