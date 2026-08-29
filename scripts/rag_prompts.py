"""所有生产/评测 Prompt 的单一来源，并按实际内容自动生成版本指纹。"""
import hashlib
from pathlib import Path


SEMANTIC_PLAN_SYSTEM = "你是检索规划器，只输出 JSON；计划中的词不是事实证据。"
SEMANTIC_PLAN_TEMPLATE = (
    "分析下面的游戏知识库问题并生成检索计划，只输出 JSON。你不能回答问题，也不能"
    "把猜测的答案写进关键词。要同时考虑动词和对象，例如‘喜欢吃什么’的主题是饮食偏好，"
    "不是人物关系；‘喜欢谁/怎么看某人’才是关系解读。检索词可以使用问题原词和通用同义词，"
    "并必须保留决定主题的核心动词（如吃、穿、用、去），不要只留下抽象分类名。\n"
    "问题：{query}\n"
    "question_type 只能是 recipe/device/enum/factual/relation/preference/"
    "comparison/numeric/open；routes 只能从 entity_direct/rag/keyword/mention/"
    "graph/relationship_evidence/recipe/enum 中选择。\n"
    '{"question_type":"preference","topic":"饮食偏好","entities":["人物名"],'
    '"keywords":["吃","食物","饮食","喜欢"],"search_queries":["人物名 吃 饮食偏好"],'
    '"routes":["entity_direct","rag","keyword"],"needs_graph":false}'
)

ANSWER_SYSTEM = (
    "你是《明日方舟：终末地》百科助手。根据提供的资料回答用户问题，要求：\n"
    "1. 只基于提供的资料，不要编造资料外的内容\n"
    "2. 回答末尾用 [来源1] 标注依据哪条资料\n"
    "3. 若资料不足以回答，明确说'资料中未找到相关内容'\n"
    "4. 对喜欢、性格、态度、动机等解释性问题，必须分成‘原文明确事实’、"
    "‘基于证据的合理解读’和‘资料不足’，不得把解读伪装成设定事实\n"
    "5. 复合问题必须逐项回答；某一小问资料不足时，只说明该小问不足，不能拒绝其他有证据的小问\n"
    "6. 简洁，中文回答"
)

INTENT_SINGLE_SYSTEM = "你是意图分类器，只输出 JSON。"
INTENT_SINGLE_TEMPLATE = (
    "判断下面这条查询的意图类别，只输出 JSON。\n"
    "类别候选：配方（问怎么合成/制造/获取物品）、设备（问什么设备能做什么）、"
    "知识（问是什么/介绍/背景）、比较（问两个东西哪个好/区别）、数值（问具体数值/属性/倍率）。\n"
    "查询：{query}\n输出格式：{\"intent\": \"配方\", \"confidence\": 0.9}"
)
INTENT_BATCH_SYSTEM = "你是意图分类器，必须按输入index逐条返回，只输出JSON。"
INTENT_BATCH_TEMPLATE = (
    '对每条查询判断意图。只输出形如 {"results":[{"index":0,"intent":"知识","confidence":0.9}]} 的JSON。\n'
    "类别只能是：配方、设备、知识、比较、数值。\n查询列表：\n{queries}"
)

ROOT = Path(__file__).resolve().parent.parent
JUDGE_PROMPT_PATH = ROOT / "scripts" / "prompts" / "judge" / "v1.txt"


def semantic_plan_prompt(query):
    return SEMANTIC_PLAN_TEMPLATE.replace("{query}", query)


def intent_single_prompt(query):
    return INTENT_SINGLE_TEMPLATE.replace("{query}", query)


def intent_batch_prompt(queries):
    return INTENT_BATCH_TEMPLATE.replace("{queries}", queries)


def load_judge_prompt():
    text = JUDGE_PROMPT_PATH.read_text(encoding="utf-8")
    system, suffix = text.split("\nUSER_SUFFIX:\n", 1)
    return system.removeprefix("SYSTEM:\n").strip(), suffix.strip()


def _version(*parts):
    content = "\n---\n".join(parts)
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def prompt_versions():
    judge_system, judge_suffix = load_judge_prompt()
    return {
        "intent": _version(INTENT_SINGLE_SYSTEM, INTENT_SINGLE_TEMPLATE,
                           INTENT_BATCH_SYSTEM, INTENT_BATCH_TEMPLATE),
        "semantic_plan": _version(SEMANTIC_PLAN_SYSTEM, SEMANTIC_PLAN_TEMPLATE),
        "answer": _version(ANSWER_SYSTEM),
        "judge": _version(judge_system, judge_suffix),
    }


PROMPT_VERSIONS = prompt_versions()
