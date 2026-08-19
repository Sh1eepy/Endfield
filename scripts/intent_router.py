# -*- coding: utf-8 -*-
"""
intent_router.py — 意图识别分层漏斗（RAG_UPGRADE_PLAN.md 阶段 2）

层级（从便宜到贵，低置信度才往下走）:
    L1 规则层:  关键词/正则，毫秒级零成本
    L3 LLM 兜底: 低置信度时调用在线 LLM（chat_json），慢但准
    （L2 轻量分类器可选，未启用——规则+LLM 组合已够用，见 RAG_UPGRADE_PLAN）

意图类别:
    配方 / 设备 / 知识 / 比较 / 数值

用法:
    from intent_router import classify_query
    intent, conf, method = classify_query("重息壤怎么合成")   # ('配方', 1.0, 'rule')

CLI:
    python scripts/intent_router.py "重息壤怎么合成"
"""
import json
import os
import re
import sys

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from llm_client import llm  # noqa: E402

# ===================== L1 规则层 =====================
# 每条规则: (意图, 正则模式)。按顺序匹配，先命中优先（比较类规则放最前，
# 因为"哪个好"这类特征最强烈；配方类关键词较宽泛放中段）。

RULES = [
    # 比较类（特征最强）
    ("比较", re.compile(r"哪个好|哪个强|哪个厉害|哪个更|有何区别|什么区别|区别是|对比一下|选哪个|和.{1,12}比")),
    # 数值类（特征明确）
    ("数值", re.compile(r"多少级|数值|属性|倍率|攻击力|防御力|生命值|血量|伤害|秒伤|装填|cd|冷却|概率|率是|多少点|多少秒|多少伤害|满级")),
    # 设备类（问设备/机器能做什么，特征强于配方）
    ("设备", re.compile(r"什么设备|什么机器|什么装置|什么设施|哪台|哪套|哪座|哪个设备|什么加工站|什么制造站")),
    ("设备", re.compile(r"能(干|做|加工|生产|制造|造|合成|产出|提炼|冶炼|加工|制作)什么|有什么用|什么用|可以(干|做|造|生产)什么|功能是")),
    # 配方类（宽泛关键词）
    ("配方", re.compile(r"怎么(合成|造|做|获得|获取|弄|搞|生产|采集|刷|冶炼|制作|制造|加工|种|培育|提炼|蒸馏|组装|制作)|合成|配方|制造|材料|原料|需要什么|需要哪些|怎么做|如何(获得|获取|合成|制造|做)|产出|产量|生产")),
    # 知识类（是什么/介绍）
    ("知识", re.compile(r"是什么|是啥|介绍|简介|背景|档案|故事|谁|哪一位|资料|设定|剧情|外观|立绘|来自|出处|讲一下|说说|了解一下|科普")),
]

# 置信度：规则命中给 1.0（匹配即视为确定）；空查询给 0
CONF_RULE = 1.0
CONF_LLM = 0.9          # LLM 兜底命中置信度
LLM_FALLBACK_THRESHOLD = 0.2   # 规则层未命中才走 LLM


def _rule_classify(query):
    """L1 规则层。返回 (intent, confidence) 或 (None, 0.0)。"""
    q = (query or "").strip()
    if not q:
        return None, 0.0
    for intent, pat in RULES:
        if pat.search(q):
            return intent, CONF_RULE
    return None, 0.0


def _llm_classify(query):
    """L3 LLM 兜底：返回 (intent, confidence) 或 (None, 0.0)。"""
    if not llm.available():
        return None, 0.0
    try:
        d = llm.chat_json(
            f"判断下面这条查询的意图类别，只输出 JSON。\n类别候选：配方（问怎么合成/制造/获取物品）、设备（问什么设备能做什么）、知识（问是什么/介绍/背景）、比较（问两个东西哪个好/区别）、数值（问具体数值/属性/倍率）。\n查询：{query}\n输出格式：{{\"intent\": \"配方\", \"confidence\": 0.9}}",
            system="你是意图分类器，只输出 JSON。", temperature=0.1, max_tokens=100)
        intent = str(d.get("intent") or "").strip()
        conf = float(d.get("confidence") or CONF_LLM)
        if intent in {"配方", "设备", "知识", "比较", "数值"}:
            return intent, conf
    except Exception:
        pass
    return None, 0.0


def classify_query(query):
    """分层漏斗入口。返回 (intent, confidence, method)。"""
    q = (query or "").strip()
    if not q:
        return None, 0.0, "empty"
    intent, conf = _rule_classify(q)
    if intent:
        return intent, conf, "rule"
    # 规则未命中 → LLM 兜底
    intent, conf = _llm_classify(q)
    if intent:
        return intent, conf, "llm"
    return None, 0.0, "none"


def classify_batch(queries):
    """批量分类（LLM 兜底合并为一次调用，省额度）。返回 {query: (intent, conf, method)}。"""
    out = {}
    llm_qs = []
    for q in queries:
        intent, conf = _rule_classify(q)
        if intent:
            out[q] = (intent, conf, "rule")
        else:
            out[q] = (None, 0.0, "pending")
            llm_qs.append(q)
    if llm_qs and llm.available():
        try:
            d = llm.chat_json(
                "对每条查询判断意图。只输出形如 "
                '{"results":[{"index":0,"intent":"知识","confidence":0.9}]} 的JSON。\n'
                "类别只能是：配方、设备、知识、比较、数值。\n查询列表：\n" +
                "\n".join(f"{i}. {q}" for i, q in enumerate(llm_qs)),
                system="你是意图分类器，必须按输入index逐条返回，只输出JSON。", temperature=0.1, max_tokens=1200)
            for item in d.get("results", []):
                idx = item.get("index")
                intent = str(item.get("intent") or "").strip()
                if isinstance(idx, int) and 0 <= idx < len(llm_qs) and intent in {"配方", "设备", "知识", "比较", "数值"}:
                    out[llm_qs[idx]] = (intent, float(item.get("confidence") or CONF_LLM), "llm")
        except Exception as exc:
            for q in llm_qs:
                out[q] = (None, 0.0, "llm_failed:" + type(exc).__name__)
    return out


if __name__ == "__main__":
    tests = ["重息壤怎么合成", "什么设备能生产电池", "重息壤是什么", "中容谷地电池和重息壤哪个好", "天有洪炉攻击力多少", "帮我看下这个"]
    for t in tests:
        i, c, m = classify_query(t)
        print(f"{t!r} → {i} (conf={c}, {m})")
