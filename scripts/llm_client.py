# -*- coding: utf-8 -*-
"""
llm_client.py — 在线 LLM 统一客户端（OpenAI 兼容协议）

用途（RAG_UPGRADE_PLAN.md 阶段 0）:
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

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")

import httpx

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"


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
            try:
                with httpx.Client(timeout=timeout or self.timeout) as client:
                    resp = client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    return resp.json()
                # 4xx 不重试（key 错误/参数错误重试无意义）；5xx/网络错误重试
                if 400 <= resp.status_code < 500:
                    raise RuntimeError(f"LLM 接口返回 {resp.status_code}: {self._safe_body(resp)}")
                last_err = RuntimeError(f"LLM 接口返回 {resp.status_code}: {self._safe_body(resp)}")
            except httpx.HTTPError as e:
                last_err = RuntimeError(f"LLM 网络错误: {e.__class__.__name__} ({e})")
            if attempt < self.max_retries:
                import time
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
        """普通对话 → 返回回答文本 str。"""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        data = self._chat_completions(messages, temperature=temperature,
                                      max_tokens=max_tokens, timeout=timeout)
        return (data["choices"][0]["message"]["content"] or "").strip()

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
