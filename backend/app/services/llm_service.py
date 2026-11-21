"""One small client for many AI providers, so users can pick what they trust and what they can afford.

  rules        built-in keyword classifier: free, offline, no AI, nothing leaves the server
  anthropic    Claude with the user's own API key
  openai-compatible: Ollama (local, free), GLM/Zhipu, Qwen/DashScope, DeepSeek, Moonshot/Kimi, OpenRouter (incl. free models), OpenAI, or any custom endpoint

Presets are editable defaults, not promises: model names, prices and free tiers change, so every field can be overridden in the UI."""
import json, re
from dataclasses import dataclass
import httpx

PROVIDERS: dict[str, dict] = {
    "rules": dict(label="Built-in rules (free, offline, no AI)", kind="rules", needs_key=False, base_url=None, models=[], tier="free",
                  note="Keyword matching in English, Dutch and German. Nothing leaves this server. Less accurate than an AI model."),
    "ollama": dict(label="Ollama — run a model on your own computer", kind="openai", needs_key=False, base_url="http://localhost:11434/v1", tier="free",
                   models=["qwen2.5:7b", "qwen2.5:14b", "deepseek-r1:8b", "llama3.1:8b", "mistral:7b"],
                   note="Free and private. Install Ollama, run `ollama pull qwen2.5:7b`. Works only when the server can reach your machine."),
    "zhipu": dict(label="GLM (Zhipu AI, China)", kind="openai", needs_key=True, base_url="https://open.bigmodel.cn/api/paas/v4", tier="free tier",
                  models=["glm-4-flash", "glm-4-air", "glm-4-plus"], note="glm-4-flash has had a free tier; check Zhipu's current terms."),
    "qwen": dict(label="Qwen (Alibaba Cloud DashScope, China)", kind="openai", needs_key=True, base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1", tier="free quota",
                 models=["qwen-turbo", "qwen-plus", "qwen-max", "qwen2.5-72b-instruct"], note="New accounts usually get a free token quota; check Alibaba's current terms."),
    "deepseek": dict(label="DeepSeek (China)", kind="openai", needs_key=True, base_url="https://api.deepseek.com/v1", tier="very cheap",
                     models=["deepseek-chat"], note="Pay-as-you-go, very low prices."),
    "moonshot": dict(label="Kimi (Moonshot AI, China)", kind="openai", needs_key=True, base_url="https://api.moonshot.ai/v1", tier="paid",
                     models=["moonshot-v1-8k", "moonshot-v1-32k", "kimi-k2-0905-preview"], note="Pay-as-you-go."),
    "openrouter": dict(label="OpenRouter (one key, many models, some free)", kind="openai", needs_key=True, base_url="https://openrouter.ai/api/v1", tier="free models available",
                       models=["deepseek/deepseek-chat-v3-0324:free", "qwen/qwen-2.5-72b-instruct:free", "meta-llama/llama-3.3-70b-instruct:free", "anthropic/claude-haiku-4.5"],
                       note="Models ending in :free cost nothing but are rate-limited, and the list changes often."),
    "anthropic": dict(label="Claude (Anthropic) — your own API key", kind="anthropic", needs_key=True, base_url="https://api.anthropic.com", tier="paid",
                      models=["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-2"],
                      note="Haiku is fastest and cheapest and is enough for classifying e-mails. Sonnet writes better replies."),
    "openai": dict(label="OpenAI — your own API key", kind="openai", needs_key=True, base_url="https://api.openai.com/v1", tier="paid", models=["gpt-4o-mini", "gpt-4o"], note="Pay-as-you-go."),
    "custom": dict(label="Custom (any OpenAI-compatible endpoint)", kind="openai", needs_key=False, base_url="", tier="varies", models=[],
                   note="vLLM, LM Studio, LiteLLM, a company gateway… Enter the base URL ending in /v1, a model name and (if needed) a key."),
}


class LlmError(Exception): pass


@dataclass
class Cfg:
    provider: str = "rules"
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None

    @property
    def kind(self) -> str: return PROVIDERS.get(self.provider, PROVIDERS["rules"])["kind"]
    @property
    def external(self) -> bool: return self.kind != "rules" and self.provider != "ollama" and not (self.base_url or "").startswith(("http://localhost", "http://127.0.0.1"))
    @property
    def label(self) -> str: return f"{self.provider}:{self.model}" if self.kind != "rules" else "rules"


def _clean(text: str, key: str | None) -> str:
    t = re.sub(r"\s+", " ", text or "")[:240]
    return t.replace(key, "***") if key else t


def complete(cfg: Cfg, system: str, user: str, max_tokens: int = 700, timeout: float = 60) -> str:
    """Send one prompt, return the model's text. Raises LlmError with a short, key-free message."""
    if cfg.kind == "rules": raise LlmError("the rules classifier does not call a model")
    p = PROVIDERS[cfg.provider]; base = (cfg.base_url or p["base_url"] or "").rstrip("/"); model = cfg.model or (p["models"][0] if p["models"] else "")
    if not base or not model: raise LlmError("base URL and model are required")
    if p["needs_key"] and not cfg.api_key: raise LlmError("an API key is required for this provider")
    try:
        with httpx.Client(timeout=timeout) as c:
            if cfg.kind == "anthropic":
                r = c.post(f"{base}/v1/messages", headers={"x-api-key": cfg.api_key or "", "anthropic-version": "2023-06-01"},
                           json={"model": model, "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": user}]})
                if r.status_code >= 400: raise LlmError(f"{r.status_code}: {_clean(r.text, cfg.api_key)}")
                out = "".join(b.get("text", "") for b in r.json().get("content", []))
            else:
                h = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
                r = c.post(f"{base}/chat/completions", headers=h, json={"model": model, "temperature": 0, "max_tokens": max_tokens,
                           "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]})
                if r.status_code >= 400: raise LlmError(f"{r.status_code}: {_clean(r.text, cfg.api_key)}")
                out = r.json()["choices"][0]["message"]["content"] or ""
    except LlmError: raise
    except httpx.HTTPError as e: raise LlmError(_clean(str(e), cfg.api_key))
    except (KeyError, IndexError, ValueError): raise LlmError("unexpected response from the provider")
    return re.sub(r"<think>.*?</think>", "", out, flags=re.S).strip()           # reasoning models (DeepSeek-R1, Qwen3) prepend their thoughts


def parse_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m: raise LlmError("the model did not return JSON")
    try: d = json.loads(m.group(0))
    except ValueError: raise LlmError("the model returned invalid JSON")
    if not isinstance(d, dict): raise LlmError("the model returned invalid JSON")
    return d


def test(cfg: Cfg) -> dict:
    """Cheap round trip used by the 'Test' button."""
    if cfg.kind == "rules": return {"ok": True, "detail": "built-in rules need no connection"}
    out = complete(cfg, "Reply with exactly: ok", "ping", max_tokens=10, timeout=30)
    return {"ok": True, "detail": f"{cfg.label} answered: {out[:40]}"}
