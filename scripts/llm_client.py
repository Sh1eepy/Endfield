# -*- coding: utf-8 -*-
"""
llm_client.py — 在线 LLM 统一客户端（OpenAI 兼容协议）

用途：
  - 意图识别 L3 兜底（chat_json 强制 JSON 输出）
  - RAG 答案生成（chat + 引用溯源）
  - 测试集自动生成 / 评测裁判

密钥安全（重要）:
  - API key 只从环境变量 / .env 读取（api_server._load_env 已把 .env 读进环境变量）
  - 本文件代码内零明文 key；错误信息不打印 key；不写日志
  - 未配置 key 时 available() 返回 False，调用方优雅降级，绝不抛异常

配置（环境变量）:
  LLM_API_KEY   必填，云端服务商密钥
  LLM_BASE_URL  可选，默认 https://api.deepseek.com/v1（OpenAI 兼容端点，DeepSeek/通义/Kimi 通用）
  LLM_MODEL     可选，默认 deepseek-chat

用法:
    from llm_client import llm
    if llm.available():
        text = llm.chat("重息壤是什么？")            # 普通问答 → str
        data = llm.chat_json("判断意图，只输出JSON",  # 强制 JSON → dict
                             system="你是意图分类器")
    else:
        # 未配 key：走降级路径（如只返回检索片段）
        ...
"""
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from contextvars import ContextVar

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")

import httpx
try:
    from scripts.rag_config import DEFAULT_LLM_MODEL
except ModuleNotFoundError:  # `python scripts/llm_client.py`
    from rag_config import DEFAULT_LLM_MODEL

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = DEFAULT_LLM_MODEL
_LLM_OBSERVER = ContextVar("llm_observer", default=None)


@contextmanager
def observe_llm(callback):
    """临时接收脱敏调用元数据；不改变 chat/chat_json 的返回类型。"""
    token = _LLM_OBSERVER.set(callback)
    try:
        yield
    finally:
        _LLM_OBSERVER.reset(token)


def _emit_event(event):
    callback = _LLM_OBSERVER.get()
    if callback:
        try:
            callback(event)
        except Exception:
            pass  # 可观测性故障不能改变问答结果


def _load_dotenv():
    """加载项目根 .env（不覆盖已存在的环境变量），llm_client 独立使用时也能读到配置。"""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

# 常见服务商 base_url 备选（当用户只填了 key 没填 base_url 时用 model 名猜）
BASE_URL_HINTS = {
    "deepseek": "https://api.deepseek.com/v1",
    "moonshot": "https://api.moonshot.cn/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "kimi": "https://api.moonshot.cn/v1",
    "glm": "https://open.bigmodel.cn/api/paas/v4",
    "zhipu": "https://open.bigmodel.cn/api/paas/v4",
    "openai": "https://api.openai.com/v1",
    "gpt": "https://api.openai.com/v1",
}


class LLMClient:
    """OpenAI 兼容协议的轻量客户端（httpx 同步实现，零额外依赖）。"""

    def __init__(self):
        self.api_key = (os.environ.get("LLM_API_KEY") or "").strip()
        self.model = (os.environ.get("LLM_MODEL") or "").strip() or DEFAULT_MODEL
        self.base_url = (os.environ.get("LLM_BASE_URL") or "").strip() or self._guess_base_url()
        self.timeout = float(os.environ.get("LLM_TIMEOUT") or "60")
        self.max_retries = 2  # 网络错误/5xx 重试次数（不含首次）

    # ---------- 配置 ----------
    def _guess_base_url(self):
        """没配 base_url 时按模型名猜服务商（deepseek-chat → deepseek）。"""
        m = self.model.lower()
        for hint, url in BASE_URL_HINTS.items():
            if hint in m:
                return url
        return DEFAULT_BASE_URL

    def available(self):
        """是否可调用：key 已配置即视为可用（不做网络探测，避免启动卡顿）。"""
        return bool(self.api_key)

    def config_summary(self):
        """脱敏配置摘要（不含 key），供日志/调试。"""
        return {"model": self.model, "base_url": self.base_url, "key_configured": bool(self.api_key)}

    # ---------- 核心调用 ----------
    def _chat_completions(self, messages, temperature=0.3, max_tokens=1024,
                          response_format=None, timeout=None):
        """调用 /chat/completions，返回解析后的 JSON 响应体。"""
        if not self.available():
            raise RuntimeError("LLM_API_KEY 未配置：请在 .env 中填写（参考 .env.example），或走降级路径")
        url = self.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if response_format:
            payload["response_format"] = response_format
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        last_err = None
        for attempt in range(self.max_retries + 1):
            started = time.perf_counter()
            try:
                with httpx.Client(timeout=timeout or self.timeout) as client:
                    resp = client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    usage = data.get("usage") if isinstance(data, dict) else None
                    choices = data.get("choices") if isinstance(data, dict) else None
                    finish_reason = choices[0].get("finish_reason") if choices else None
                    _emit_event({
                        "status": "ok", "model": data.get("model", self.model),
                        "attempt": attempt + 1,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                        "finish_reason": finish_reason,
                        "prompt_tokens": (usage or {}).get("prompt_tokens"),
                        "completion_tokens": (usage or {}).get("completion_tokens"),
                        "total_tokens": (usage or {}).get("total_tokens"),
                    })
                    return data
                # 4xx 不重试（key 错误/参数错误重试无意义）；5xx/网络错误重试
                if 400 <= resp.status_code < 500:
                    _emit_event({"status": "error", "model": self.model, "attempt": attempt + 1,
                                 "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                                 "error_type": f"HTTP_{resp.status_code}"})
                    raise RuntimeError(f"LLM 接口返回 {resp.status_code}: {self._safe_body(resp)}")
                _emit_event({"status": "retry" if attempt < self.max_retries else "error",
                             "model": self.model, "attempt": attempt + 1,
                             "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                             "error_type": f"HTTP_{resp.status_code}"})
                last_err = RuntimeError(f"LLM 接口返回 {resp.status_code}: {self._safe_body(resp)}")
            except httpx.HTTPError as e:
                _emit_event({"status": "retry" if attempt < self.max_retries else "error",
                             "model": self.model, "attempt": attempt + 1,
                             "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                             "error_type": e.__class__.__name__})
                last_err = RuntimeError(f"LLM 网络错误: {e.__class__.__name__} ({e})")
            if attempt < self.max_retries:
                time.sleep(1.5 * (attempt + 1))  # 1.5s / 3s 退避
        raise last_err or RuntimeError("LLM 调用失败（未知错误）")

    @staticmethod
    def _safe_body(resp):
        """响应体脱敏：错误信息里绝不带 key（body 一般不含 key，这里再兜底）。"""
        try:
            body = resp.text[:300]
        except Exception:
            return ""
        return body.replace(os.environ.get("LLM_API_KEY", "________"), "***")

    # ---------- 对外接口 ----------
    def chat(self, prompt, system=None, temperature=0.3, max_tokens=1024, timeout=None):
        """普通对话 → 返回回答文本 str；命中长度上限时自动续写一次。"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        parts = []
        budget = max_tokens
        for round_index in range(2):
            data = self._chat_completions(messages, temperature=temperature,
                                          max_tokens=budget, timeout=timeout)
            choice = data["choices"][0]
            content = choice["message"].get("content") or ""
            if content:
                parts.append(content)
            if choice.get("finish_reason") != "length":
                return "".join(parts).strip()
            if round_index == 1:
                raise RuntimeError("LLM 回答连续两次达到长度上限")
            if content:
                messages.extend([
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": "请从刚才截断处继续，只输出尚未输出的正文，不要复述。"},
                ])
            else:
                # 推理模型可能先耗尽思考预算而正文仍为空；原请求用更大预算重试。
                budget = min(max(2 * budget, budget + 512), 4096)
        raise RuntimeError("LLM 回答生成异常")

    def chat_json(self, prompt, system=None, temperature=0.1, max_tokens=1024, timeout=None):
        """强制 JSON 输出 → 返回 dict（意图识别/测试集生成/结构化抽取用）。

        双保险：请求带 response_format=json_object；若服务商不支持，
        则从文本中提取第一个 {...} 块兜底解析。
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            data = self._chat_completions(
                messages, temperature=temperature, max_tokens=max_tokens,
                response_format={"type": "json_object"}, timeout=timeout)
            content = (data["choices"][0]["message"]["content"] or "").strip()
        except RuntimeError as e:
            # response_format 不被支持（个别服务商）→ 去掉后重试一次
            if "response_format" not in str(e) and "400" not in str(e):
                raise
            data = self._chat_completions(messages, temperature=temperature,
                                          max_tokens=max_tokens, timeout=timeout)
            content = (data["choices"][0]["message"]["content"] or "").strip()
        return self._extract_json(content)

    def chat_stream(self, prompt, system=None, temperature=0.3, max_tokens=1024, timeout=None,
                    abort=None, _messages=None, _continuations_left=1):
        """流式对话（SSE 增量）→ 逐段产出回答文本的生成器。

        与 chat() 使用同一套 prompt/参数/密钥纪律，只是把 stream=True 的增量解析后
        一段段 yield 出来，供 /api/ask/stream 边生成边转发。

        重试语义：
          - 首字到达前的网络错误 / 5xx 按既有 1.5s/3s 退避重试；
          - 已经开始吐字后的失败不再重试（已输出的内容无法撤销），由调用方收尾；
          - 4xx 是业务错误，直接抛出。
        `abort` 是可选 threading.Event：置位后在下一个 chunk 边界中止（配合客户端断开）。
        """
        if not self.available():
            raise RuntimeError("LLM_API_KEY 未配置：请在 .env 中填写（参考 .env.example），或走降级路径")
        messages = list(_messages) if _messages is not None else []
        if _messages is None:
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
        url = self.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        last_err = None
        for attempt in range(self.max_retries + 1):
            if abort is not None and abort.is_set():
                raise RuntimeError("LLM 流式生成已中止")
            started = time.perf_counter()
            emitted = False
            emitted_parts = []
            finish_reason = None
            status_code = None
            try:
                with httpx.Client(timeout=timeout or self.timeout) as client:
                    with client.stream("POST", url, json=payload, headers=headers) as resp:
                        status_code = resp.status_code
                        if resp.status_code != 200:
                            raise RuntimeError(f"LLM 接口返回 {resp.status_code}: {self._safe_body(resp)}")
                        for line in resp.iter_lines():
                            if abort is not None and abort.is_set():
                                raise RuntimeError("LLM 流式生成已中止")
                            if not line or not line.startswith("data:"):
                                continue
                            data = line[len("data:"):].strip()
                            if not data or data == "[DONE]":
                                continue
                            try:
                                chunk = json.loads(data)
                            except json.JSONDecodeError:
                                continue
                            choices = chunk.get("choices") or []
                            if not choices:
                                continue
                            choice = choices[0]
                            if choice.get("finish_reason") is not None:
                                finish_reason = choice.get("finish_reason")
                            delta = (choice.get("delta") or {}).get("content") or ""
                            if delta:
                                emitted = True
                                emitted_parts.append(delta)
                                yield delta
                if finish_reason == "length":
                    if _continuations_left <= 0:
                        raise RuntimeError("LLM 流式回答连续两次达到长度上限")
                    _emit_event({"status": "continue", "model": self.model,
                                 "attempt": attempt + 1,
                                 "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                                 "error_type": "finish_reason_length"})
                    if emitted_parts:
                        next_messages = messages + [
                            {"role": "assistant", "content": "".join(emitted_parts)},
                            {"role": "user", "content": "请从刚才截断处继续，只输出尚未输出的正文，不要复述。"},
                        ]
                        next_budget = max_tokens
                    else:
                        # 正文尚未开始，通常是推理预算耗尽；扩大预算后重跑原请求。
                        next_messages = messages
                        next_budget = min(max(2 * max_tokens, max_tokens + 512), 4096)
                    yield from self.chat_stream(
                        "", temperature=temperature, max_tokens=next_budget, timeout=timeout,
                        abort=abort, _messages=next_messages,
                        _continuations_left=_continuations_left - 1)
                    return
                _emit_event({"status": "ok", "model": self.model, "attempt": attempt + 1,
                             "elapsed_ms": round((time.perf_counter() - started) * 1000, 2)})
                return
            except httpx.HTTPError as exc:
                last_err = RuntimeError(f"LLM 网络错误: {exc.__class__.__name__} ({exc})")
                _emit_event({"status": "retry" if (attempt < self.max_retries and not emitted) else "error",
                             "model": self.model, "attempt": attempt + 1,
                             "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                             "error_type": exc.__class__.__name__})
                if emitted:
                    raise last_err
            except RuntimeError as exc:
                # 主动取消不是可恢复的网络故障，尤其不能在首字前重新发起付费请求。
                if abort is not None and abort.is_set():
                    raise
                # 非 200 的业务错误：4xx 直接抛；5xx 在未吐字时按退避重试。
                if emitted:
                    raise
                if status_code is not None and 400 <= status_code < 500:
                    _emit_event({"status": "error", "model": self.model, "attempt": attempt + 1,
                                 "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                                 "error_type": f"HTTP_{status_code}"})
                    raise exc
                if status_code is not None and attempt >= self.max_retries:
                    _emit_event({"status": "error", "model": self.model, "attempt": attempt + 1,
                                 "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                                 "error_type": f"HTTP_{status_code}"})
                    raise exc
                last_err = exc
            if attempt < self.max_retries:
                time.sleep(1.5 * (attempt + 1))  # 1.5s / 3s 退避
        raise last_err or RuntimeError("LLM 调用失败（未知错误）")

    @staticmethod
    def _extract_json(text):
        """从文本提取 JSON 对象：先整体解析，失败则找第一个 {...} 块。"""
        text = (text or "").strip()
        # 去掉可能的 markdown 代码围栏
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
        raise ValueError(f"LLM 输出不是有效 JSON: {text[:200]}")


# 模块级单例（api_server / rag 管线共享）
llm = LLMClient()


if __name__ == "__main__":
    print("LLM 客户端配置:", llm.config_summary())
    if llm.available():
        try:
            ans = llm.chat("用一句话介绍《明日方舟：终末地》")
            print("测试回答:", ans)
        except Exception as e:
            print("调用失败:", e)
    else:
        print("未配置 LLM_API_KEY → 降级路径生效（不崩）。请在 .env 填写后重试。")
