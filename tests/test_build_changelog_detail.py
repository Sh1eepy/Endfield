import os
import tempfile
import unittest
from pathlib import Path

from scripts.build_changelog_detail import load_notes, render, split_subject


def commit(short, date, subject):
    return {"short": short, "date": date, "subject": subject}


def round_trip(commits, text):
    """把渲染结果写入文件再解析回来，模拟"下一次重新生成"。"""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "CHANGELOG_DETAIL.md"
        path.write_text(text, encoding="utf-8")
        return load_notes(path)


def add_note(text, short, note):
    """在指定提交行下方插入一条人工说明，模拟维护者的编辑。"""
    lines = []
    for line in text.splitlines():
        lines.append(line)
        if line.startswith(f"- `{short}`"):
            lines.append(f"  - {note}")
    return "\n".join(lines) + "\n"


class SubjectLabelTests(unittest.TestCase):
    def test_maps_conventional_prefix_to_chinese_label(self):
        self.assertEqual(split_subject("feat: add query backdrop"), ("新增", "add query backdrop"))
        self.assertEqual(split_subject("fix(api): bound retries"), ("修复", "bound retries"))
        self.assertEqual(split_subject("docs!: rewrite readme"), ("文档", "rewrite readme"))

    def test_keeps_subject_without_conventional_prefix(self):
        self.assertEqual(split_subject("initial import"), ("", "initial import"))

    def test_keeps_unknown_prefix_readable(self):
        self.assertEqual(split_subject("wip: try something"), ("wip", "try something"))


class RenderTests(unittest.TestCase):
    def test_groups_commits_by_date_newest_first(self):
        text = render([
            commit("aaa1111", "2026-09-14", "feat: newer"),
            commit("bbb2222", "2026-09-13", "fix: older"),
        ], {})
        self.assertIn("共 2 条提交，覆盖 2026-09-13 至 2026-09-14", text)
        self.assertLess(text.index("## 2026-09-14"), text.index("## 2026-09-13"))
        self.assertLess(text.index("aaa1111"), text.index("bbb2222"))

    def test_renders_notes_below_their_commit(self):
        text = render([commit("aaa1111", "2026-09-14", "feat: newer")],
                      {"aaa1111": ["说明：补齐了来源登记"]})
        self.assertIn("  - 说明：补齐了来源登记", text)
        self.assertLess(text.index("aaa1111"), text.index("说明：补齐了来源登记"))


class NoteRoundTripTests(unittest.TestCase):
    COMMITS = [commit("aaa1111", "2026-09-14", "feat: newer"),
               commit("bbb2222", "2026-09-13", "fix: older")]

    def test_regenerating_keeps_manual_notes(self):
        marked = add_note(add_note(render(self.COMMITS, {}), "aaa1111", "说明：人工补充"),
                          "bbb2222", "说明：另一条补充")
        notes = round_trip(self.COMMITS, marked)
        second = render(self.COMMITS, notes)
        self.assertEqual(notes["aaa1111"], ["说明：人工补充"])
        self.assertIn("  - 说明：人工补充", second)
        self.assertIn("  - 说明：另一条补充", second)

    def test_regenerating_twice_is_stable(self):
        text = render(self.COMMITS, {"aaa1111": ["说明：人工补充"]})
        self.assertEqual(render(self.COMMITS, round_trip(self.COMMITS, text)), text)

    def test_missing_file_yields_no_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_notes(Path(tmp) / "absent.md"), {})

    def test_body_lines_are_not_mistaken_for_notes(self):
        text = render(self.COMMITS, {})
        self.assertEqual(round_trip(self.COMMITS, text), {})


if __name__ == "__main__":
    unittest.main()
