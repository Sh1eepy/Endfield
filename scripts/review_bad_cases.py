"""本机管理员审核反馈隔离区；未审核样本不会进入 Replay 或质量门禁。"""
import argparse
import json
import os
import sqlite3
import sys

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from scripts.rag_trace import trace_store  # noqa: E402
from scripts.eval_case import VALID_ROUTES  # noqa: E402


def split_values(text):
    return [x.strip() for x in (text or "").split(",") if x.strip()]


def main():
    ap = argparse.ArgumentParser(description="审核 RAG 用户反馈隔离区")
    sub = ap.add_subparsers(dest="command", required=True)
    listing = sub.add_parser("list")
    listing.add_argument("--status", default="pending_review")
    listing.add_argument("--limit", type=int, default=50)
    show = sub.add_parser("show"); show.add_argument("feedback_id")
    approve = sub.add_parser("approve")
    approve.add_argument("feedback_id")
    approve.add_argument("--facts", default="", help="必要事实，英文逗号分隔")
    approve.add_argument("--sources", default="", help="可接受来源名称，英文逗号分隔")
    approve.add_argument("--route", choices=sorted(VALID_ROUTES), required=True,
                         help="生产问答应使用的 route_used")
    approve.add_argument("--should-refuse", action="store_true")
    approve.add_argument("--failure-type", default="")
    approve.add_argument("--notes", default="")
    reject = sub.add_parser("reject"); reject.add_argument("feedback_id"); reject.add_argument("--notes", default="")
    args = ap.parse_args()
    with trace_store.connect() as conn:
        if args.command == "list":
            rows = conn.execute("""SELECT feedback_id,trace_id,created_at,vote,query,status
                FROM feedback WHERE status=? ORDER BY created_at DESC LIMIT ?""",
                                (args.status, args.limit)).fetchall()
            print(json.dumps([dict(x) for x in rows], ensure_ascii=False, indent=2))
        elif args.command == "show":
            row = conn.execute("SELECT * FROM feedback WHERE feedback_id=?", (args.feedback_id,)).fetchone()
            print(json.dumps(dict(row) if row else None, ensure_ascii=False, indent=2))
        elif args.command == "approve":
            facts, sources = split_values(args.facts), split_values(args.sources)
            if not args.should_refuse and not facts and not sources:
                raise SystemExit("非拒答样本必须提供 --facts 或 --sources，避免无 Gold 坏例污染回归集")
            cur = conn.execute("""UPDATE feedback SET status='approved_regression', failure_type=?,
                required_terms_json=?, acceptable_sources_json=?, expected_route=?, should_refuse=?,
                notes=? WHERE feedback_id=? AND status='pending_review'""", (
                args.failure_type or None, json.dumps(facts, ensure_ascii=False),
                json.dumps(sources, ensure_ascii=False), args.route,
                int(args.should_refuse), args.notes, args.feedback_id))
            if cur.rowcount != 1:
                raise SystemExit("未找到待审核反馈，或该反馈已处理")
            print("approved_regression")
        else:
            cur = conn.execute("""UPDATE feedback SET status='rejected_invalid', notes=?
                WHERE feedback_id=? AND status='pending_review'""", (args.notes, args.feedback_id))
            if cur.rowcount != 1:
                raise SystemExit("未找到待审核反馈，或该反馈已处理")
            print("rejected_invalid")


if __name__ == "__main__":
    main()
