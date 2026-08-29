"""答案评测与线上坏例共用的 Gold schema、来源匹配和确定性评分。"""
import json
import re
from dataclasses import dataclass


VALID_ROUTES = {"enum", "structured", "graph", "hybrid_relation", "rag"}


def _list(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            value = []
    return [str(x).strip() for x in (value or []) if str(x).strip()]


def normalized_source(name):
    return str(name or "").split("｜语音：")[0].strip().lower()


def source_name_matches(name, acceptable_sources):
    normalized = normalized_source(name)
    return any(normalized == normalized_source(x) for x in acceptable_sources)


@dataclass(frozen=True)
class EvaluationCase:
    query: str
    required_terms: tuple[str, ...] = ()
    acceptable_sources: tuple[str, ...] = ()
    should_refuse: bool = False
    expected_route: str | None = None

    @classmethod
    def from_mapping(cls, row):
        route = row.get("expected_route") or None
        if route and route not in VALID_ROUTES:
            raise ValueError(f"invalid_expected_route:{route}")
        return cls(
            query=str(row.get("query") or "").strip(),
            required_terms=tuple(_list(row.get("required_terms", row.get("required_terms_json")))),
            acceptable_sources=tuple(_list(row.get("acceptable_sources", row.get("acceptable_sources_json")))),
            should_refuse=bool(row.get("should_refuse")),
            expected_route=route,
        )


def result_source_names(result):
    sources = [x.get("name") for x in (result.get("sources") or [])]
    sources.extend((x.get("meta") or {}).get("name") or x.get("name")
                   for x in (result.get("hits") or []))
    return [str(x) for x in sources if x]


def deterministic_score(case, result):
    if not isinstance(case, EvaluationCase):
        case = EvaluationCase.from_mapping(case)
    answer = str(result.get("answer") or "")
    refused = bool(result.get("rejected")) or "未找到" in answer or "不足" in answer
    names = result_source_names(result)
    return {
        "refusal_correct": refused == case.should_refuse,
        "required_terms_coverage": (
            round(sum(term in answer for term in case.required_terms) / len(case.required_terms), 4)
            if case.required_terms else 1.0),
        "citation_present": case.should_refuse or bool(re.search(r"\[来源\d+\]", answer)),
        "source_overlap": (case.should_refuse or not case.acceptable_sources or
                           any(source_name_matches(name, case.acceptable_sources) for name in names)),
    }
