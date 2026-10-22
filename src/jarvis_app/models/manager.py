"""Model manager: reads providers.yaml, resolves spoken aliases, validates a model with a live ping before
switching, persists the active model in SQLite, and reports status for the dashboard (never secret values)."""
import re
import time
from contextlib import nullcontext

import yaml

from ..security.secrets import get_secret, redact, secret_status
from .adapters import AnthropicProvider, MockProvider, OllamaProvider, OpenAICompatProvider
from .base import ProviderError


def _norm(s):
    """'Claude Sonnet 5.5' → 'claude sonnet 5 5' (case, punctuation and extra spaces ignored)."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(s).lower()).split())


class ModelManager:
    def __init__(self, providers_file, db, events=None):
        self.events = events
        self.db = db
        with open(providers_file) as f:
            cfg = yaml.safe_load(f) or {}
        self.providers_cfg = cfg.get("providers") or {}
        self.models = cfg.get("models") or {}
        self.aliases = {_norm(k): v for k, v in (cfg.get("aliases") or {}).items()}
        for k, m in self.models.items():
            if m.get("provider") not in self.providers_cfg:
                raise ValueError(f"model {k}: unknown provider {m.get('provider')}")
            self.aliases.setdefault(_norm(k), k)
            self.aliases.setdefault(_norm(m.get("label", k)), k)
        default = cfg.get("active")
        saved = db.get_setting("active_model")
        self.active = saved if saved in self.models else default
        if self.active not in self.models:
            raise ValueError(f"active model {self.active!r} not in models")
        self._adapters = {}

    def _emit(self, kind, **data):
        if self.events is not None:
            self.events.emit(kind, **data)

    def _key_fn(self, pcfg):
        return lambda: get_secret(pcfg.get("secret"), pcfg.get("env"), pcfg.get("secret_file"))

    def adapter(self, provider_name):
        if provider_name not in self._adapters:
            p = self.providers_cfg[provider_name]
            t = p.get("type")
            if t == "anthropic":
                a = AnthropicProvider(p["base_url"], self._key_fn(p))
            elif t == "openai_compat":
                a = OpenAICompatProvider(p["base_url"], self._key_fn(p))
            elif t == "ollama":
                a = OllamaProvider(p["base_url"])
            elif t == "mock":
                a = MockProvider()
            else:
                raise ValueError(f"provider {provider_name}: unknown type {t}")
            self._adapters[provider_name] = a
        return self._adapters[provider_name]

    def resolve(self, name):
        """Spoken or typed name → model key, or None."""
        n = _norm(name)
        if n in self.aliases:
            return self.aliases[n]
        n2 = re.sub(r"^(claude|the)\s+", "", n)
        return self.aliases.get(n2)

    def current(self):
        m = self.models[self.active]
        return self.active, m

    def capabilities(self, key=None):
        return set(self.models[key or self.active].get("capabilities") or [])

    def validate(self, key):
        """Live ping. Returns (ok, detail). Records the result for the dashboard."""
        m = self.models[key]
        t0 = time.time()
        try:
            with self.events.span("model.validation", provider=m["provider"], model=m["model"], label="Model validation") if self.events is not None else nullcontext():
                self._emit("model.requested", provider=m["provider"], model=m["model"], requested_model=m["model"], reason="validation")
                adapter = self.adapter(m["provider"])
                served = adapter.ping(m["model"])
                reported = served if getattr(adapter, "last_ping_model_reported", False) else "unknown"
                self._emit("model.served", provider=m["provider"], model=reported, served_model=reported,
                           reason="provider_reported_model" if reported != "unknown" else "provider_omitted_model",
                           status="completed")
            ok, detail = True, f"answered as {served} in {time.time() - t0:.1f}s"
        except ProviderError as e:
            ok, detail = False, redact(e)
        except Exception as e:  # noqa: BLE001 - unexpected adapter bug: report, don't crash
            ok, detail = False, redact(f"{type(e).__name__}: {e}")
        checks = self.db.get_setting("model_checks", {})
        checks[key] = {"ok": ok, "detail": detail[:300], "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        self.db.set_setting("model_checks", checks)
        return ok, detail

    def switch(self, name):
        key = self.resolve(name) if name not in self.models else name
        if not key:
            self._emit("model.switch", status="invalid", reason="unknown_model", model=self.active)
            return {"ok": False, "message": f"I don't have a model called '{name}' configured. "
                    f"Available: {', '.join(self.models[k].get('label', k) for k in self.models if k != 'mock')}."}
        ok, detail = self.validate(key)
        if not ok:
            self._emit("model.switch.retained", status="error", reason="validation_failed_kept_selected", model=self.active, requested_model=key)
            return {"ok": False, "model": key, "message": f"{self.models[key].get('label', key)} is configured but "
                    f"not reachable right now ({detail}). I kept {self.models[self.active].get('label', self.active)}."}
        self.active = key
        self._emit("model.switch", status="completed", model=key, provider=self.models[key]["provider"])
        self.db.set_setting("active_model", key)
        return {"ok": True, "model": key, "message": f"Switched to {self.models[key].get('label', key)} "
                f"({self.models[key]['provider']}: {self.models[key]['model']}); {detail}."}

    def status(self):
        checks = self.db.get_setting("model_checks", {})
        out = []
        for k, m in self.models.items():
            p = self.providers_cfg[m["provider"]]
            cred = "not needed" if p.get("type") in ("ollama", "mock") else \
                secret_status(p.get("secret"), p.get("env"), p.get("secret_file"))
            out.append({"key": k, "label": m.get("label", k), "provider": m["provider"], "model": m["model"],
                        "capabilities": m.get("capabilities") or [], "credential": cred, "active": k == self.active,
                        "last_check": checks.get(k)})
        return out
