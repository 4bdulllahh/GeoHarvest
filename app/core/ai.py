"""Smart mode: an AI reads each lead and scores it against the user's ideal customer.

The user brings their own AI: a free cloud key (Gemini, Groq, OpenRouter...), a
paid one (Claude, OpenAI...) or a model running on their own PC (Ollama, LM
Studio). Three ways of talking cover all of them:

* ``gemini``     Google's generateContent API, plain HTTPS
* ``openai``     the OpenAI-style /chat/completions API, which almost every other
                 provider and both local apps also speak
* ``anthropic``  Claude through the official ``anthropic`` SDK

Leads go in batches of a few at a time: one request scores several businesses,
which matters on free tiers that allow only a handful of requests a minute.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

import httpx

from app.core import credentials, db

BATCH_SIZE = 8
GOOD_FIT, MAYBE = 80, 50
# What the AI can add besides the score, when the user switches it on:
# setting -> (lead field, what to ask for; the word before ":" is the reply's key)
EXTRAS = {
    "ai_opener": ("ai_opener", "opener: a friendly first line for a cold email or call to "
                               "this business, at most 25 words, specific to it"),
    "ai_needs": ("ai_needs", "needs: what this business seems to be missing that the seller "
                             "could help with (e.g. no website, few reviews), at most 15 words"),
    "ai_channel": ("ai_channel", "channel: the best way to reach it, one of Email, Phone, "
                                 "WhatsApp, Instagram, Facebook, LinkedIn, Contact form, Visit"),
}
LANGUAGE_NAMES = {"ar": "Arabic", "de": "German", "es": "Spanish", "fr": "French"}
# Ready-made ideal customers to start from, on the Smart mode page
EXAMPLES = [
    ("Web design", "Small local businesses with no website, or an old, slow one that does not "
                   "work well on phones. Owner-run, with good reviews, so they can afford a new "
                   "site. Not chains or franchises."),
    ("SEO and Google ranking", "Businesses with a website but few Google reviews or a low "
                               "rating, in busy areas where customers search online. Not big "
                               "brands that have their own marketing team."),
    ("Social media marketing", "Shops, cafes, salons and clinics with few or no social media "
                               "pages, or pages that look inactive. They sell to local "
                               "customers and would gain from being seen online."),
    ("Accounting and bookkeeping", "Small and new companies, ideally under 3 years old, with a "
                                   "website and an email address. Owner-run, not part of a "
                                   "group with its own finance department."),
    ("Recruiting", "Growing companies with 10 or more staff, a careers or team page, and good "
                   "reviews. Not one-person businesses."),
    ("Software and booking apps", "Clinics, salons, gyms and restaurants that take bookings by "
                                  "phone only, with no online booking on their website."),
]


@dataclass(frozen=True)
class Provider:
    key: str
    name: str
    kind: str          # gemini, openai, anthropic
    base_url: str
    model: str         # a sensible default; "Load models" lists the real choices
    needs_key: bool
    key_url: str
    note: str


PROVIDERS = [
    Provider("gemini", "Google Gemini", "gemini",
             "https://generativelanguage.googleapis.com/v1beta", "gemini-2.5-flash", True,
             "https://aistudio.google.com/apikey", "Free key, no card needed. Good default."),
    Provider("groq", "Groq", "openai", "https://api.groq.com/openai/v1",
             "llama-3.3-70b-versatile", True, "https://console.groq.com/keys",
             "Free key, very fast."),
    Provider("openrouter", "OpenRouter", "openai", "https://openrouter.ai/api/v1",
             "meta-llama/llama-3.3-70b-instruct:free", True, "https://openrouter.ai/keys",
             "Free key; models whose names end in :free cost nothing."),
    Provider("mistral", "Mistral", "openai", "https://api.mistral.ai/v1", "mistral-small-latest",
             True, "https://console.mistral.ai/api-keys", "Free experiment plan available."),
    Provider("claude", "Anthropic Claude", "anthropic", "", "claude-opus-5-5", True,
             "https://console.anthropic.com/settings/keys",
             "Paid. Claude Haiku 5.5 (claude-haiku-5-5) is the cheapest choice for scoring leads."),
    Provider("openai", "OpenAI", "openai", "https://api.openai.com/v1", "gpt-5-mini", True,
             "https://platform.openai.com/api-keys", "Paid."),
    Provider("deepseek", "DeepSeek", "openai", "https://api.deepseek.com/v1", "deepseek-chat",
             True, "https://platform.deepseek.com/api_keys", "Paid, very cheap."),
    Provider("ollama", "Ollama (on this PC)", "openai", "http://localhost:11434/v1", "llama3.2",
             False, "https://ollama.com/download",
             "Free and private: runs on your own computer. Install Ollama, then run "
             "'ollama pull llama3.2'. A fast PC with a graphics card helps."),
    Provider("lmstudio", "LM Studio (on this PC)", "openai", "http://localhost:1234/v1", "",
             False, "https://lmstudio.ai",
             "Free and private: load a model in LM Studio and start its local server."),
    Provider("custom", "Other (OpenAI-compatible)", "openai", "", "", False, "",
             "Any service that speaks the OpenAI chat API: enter its address and model."),
]
BY_KEY = {p.key: p for p in PROVIDERS}

# Claude models that accept server-side refusal fallbacks; on a decline the API
# re-runs the request on a suitable model instead of returning nothing
CLAUDE_FALLBACK_MODELS = ("claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5")
CLAUDE_EFFORT_MODELS = ("claude-fable-5", "claude-opus-5", "claude-sonnet-5", "claude-haiku-5",
                        "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6",
                        "claude-sonnet-4-6")

SYSTEM = """You qualify sales leads for someone who finds businesses on Google Maps.
For each business, judge from the details given:
1. Is it a real, operating business of the kind that was searched for (not a mislabelled,
   closed, duplicate or unrelated listing)?
2. How well does it match the ideal customer described?
Score 0-100: 80 or more is a strong fit, 50-79 a possible fit, below 50 a poor fit.
The reason is one plain sentence of at most 25 words that a salesperson can act on.
Use only the details given; do not invent facts. Answer with JSON only."""

def reply_key(extra: str) -> str:
    return EXTRAS[extra][1].split(":")[0]


def schema(extras: list[str] = ()) -> dict:
    """The reply's JSON shape, with a text field for each extra asked for."""
    names = ["id", "score", "reason"] + [reply_key(key) for key in extras]
    properties = {name: {"type": "string"} for name in names}
    properties.update(id={"type": "integer"}, score={"type": "integer"})
    return {"type": "object",
            "properties": {"results": {"type": "array", "items": {
                "type": "object", "properties": properties, "required": names,
                "additionalProperties": False}}},
            "required": ["results"], "additionalProperties": False}

LEAD_FIELDS = ("name", "category", "categories", "rating", "reviews", "price", "status", "city",
               "website", "company_age", "claimed", "description", "attributes", "hours")


class AIError(RuntimeError):
    """``fatal`` errors (a wrong key, an unknown model) stop Smart mode for this search."""

    def __init__(self, message: str, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal


# --- settings ---------------------------------------------------------------
def settings() -> dict | None:
    """The saved Smart mode setup, or None if it has not been set up."""
    provider = BY_KEY.get(db.get_setting("ai_provider", ""))
    if provider is None:
        return None
    return {
        "provider": provider.key,
        "kind": provider.kind,
        "base_url": (db.get_setting("ai_base_url", "") or provider.base_url).rstrip("/"),
        "model": db.get_setting("ai_model", "") or provider.model,
        "key": credentials.load_secret(credentials.ai_key_name(provider.key)),
        "profile": db.get_setting("ai_profile", ""),
        "dealbreakers": db.get_setting("ai_dealbreakers", ""),
        "min_score": int(db.get_setting("ai_min_score", 0) or 0),
        "max_leads": int(db.get_setting("ai_max_leads", 0) or 0),    # 0: every lead
        "per_minute": int(db.get_setting("ai_per_minute", 0) or 0),  # 0: no limit
        "contact_only": bool(db.get_setting("ai_contact_only", False)),
        "read_site": bool(db.get_setting("ai_read_site", False)),
        "extras": [key for key in EXTRAS if db.get_setting(key, False)],
        "language": LANGUAGE_NAMES.get(db.get_setting("language", "") or "", ""),
    }


def worth_checking(cfg: dict, lead: dict) -> bool:
    """With "only leads I can contact" on, a lead needs a phone number or an email."""
    return not cfg.get("contact_only") or bool(lead.get("phone") or lead.get("emails"))


class Pace:
    """At most ``per_minute`` requests a minute (0: no limit), so a free key's limit is
    never hit."""

    def __init__(self, per_minute: int):
        self.gap = 60 / per_minute if per_minute else 0
        self.last = -self.gap

    def wait(self, cancelled=lambda: False) -> None:
        while not cancelled() and time.monotonic() < self.last + self.gap:
            time.sleep(max(0.0, min(0.25, self.last + self.gap - time.monotonic())))
        self.last = time.monotonic()


# --- saved ideal customers ----------------------------------------------------
def profiles() -> dict[str, dict]:
    """The user's saved ideal customers, by name, in the order saved: each one's
    description ("profile") and deal-breakers ("never")."""
    return dict(db.get_setting("ai_profiles", {}) or {})


def save_profile(name: str, profile: str, never: str = "") -> None:
    saved = profiles()
    saved.pop(name, None)  # saving over one moves it to the end
    saved[name] = {"profile": profile, "never": never}
    db.set_setting("ai_profiles", saved)


def delete_profile(name: str) -> None:
    saved = profiles()
    saved.pop(name, None)
    db.set_setting("ai_profiles", saved)


def verdict(score: int) -> str:
    return "Good fit" if score >= GOOD_FIT else "Maybe" if score >= MAYBE else "Poor fit"


def tag(score: int) -> str:
    return "Hot" if score >= GOOD_FIT else "Warm" if score >= MAYBE else "Cold"


# --- prompt -----------------------------------------------------------------
def describe(lead: dict, read_site: bool = False) -> dict:
    """The parts of a lead worth an AI's attention, kept short."""
    facts = {k: lead[k] for k in LEAD_FIELDS if lead.get(k) not in (None, "", [])}
    if read_site and lead.get("site_text"):
        facts["website_text"] = lead["site_text"]
    for key in ("description", "attributes", "hours"):
        if key in facts:
            facts[key] = str(facts[key])[:300]
    facts["has_email"] = bool(lead.get("emails"))
    facts["has_phone"] = bool(lead.get("phone"))
    facts["social_media"] = [n for n in ("facebook", "instagram", "linkedin", "twitter",
                                         "youtube", "tiktok") if lead.get(n)]
    return facts


def build_prompt(cfg: dict, searched_for: str, leads: list[dict]) -> str:
    items = [{"id": i, **describe(lead, cfg.get("read_site", False))}
             for i, lead in enumerate(leads)]
    extras = cfg.get("extras", [])
    profile = (cfg.get("profile") or "").strip() or "Any genuine business of this kind."
    text = f"Searched for: {searched_for}\n\nIdeal customer: {profile}\n\n"
    if (cfg.get("dealbreakers") or "").strip():
        text += ("Never a fit (score 0 if a business is one of these): "
                 f"{cfg['dealbreakers'].strip()}\n\n")
    if extras:
        text += "Also give, for each business:\n" + "".join(
            f"- {EXTRAS[key][1]}\n" for key in extras) + "\n"
    if cfg.get("language"):
        text += f"Write the reason and every other text in {cfg['language']}.\n\n"
    shape = '"id": <id>, "score": <0-100>, "reason": "<sentence>"' + "".join(
        f', "{reply_key(key)}": "<text>"' for key in extras)
    return (text + f"Businesses:\n{json.dumps(items, ensure_ascii=False)}\n\n"
            'Reply with {"results": [{' + shape + '}]} covering every business.')


def parse_reply(text: str, leads: list[dict], extras: list[str] = ()) -> dict[str, dict]:
    """place_id -> AI fields. Tolerates code fences and chatter around the JSON."""
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        raise AIError("The AI did not answer in the expected format.")
    try:
        data = json.loads(match.group(0))
    except ValueError as error:
        raise AIError("The AI did not answer in the expected format.") from error
    scored = {}
    for item in data.get("results", []) if isinstance(data, dict) else []:
        try:
            index, score = int(item["id"]), max(0, min(100, int(item["score"])))
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= index < len(leads):
            fields = scored[leads[index]["place_id"]] = {
                "ai_score": score, "ai_verdict": verdict(score), "ai_tag": tag(score),
                "ai_reason": str(item.get("reason", "")).strip()[:300]}
            for key in extras:
                fields[EXTRAS[key][0]] = str(item.get(reply_key(key), "")).strip()[:300]
    return scored


# --- transports -------------------------------------------------------------
def _http_error(response: httpx.Response) -> AIError:
    status = response.status_code
    if status in (401, 403):
        return AIError("The AI key was not accepted. Check it on the Smart mode page.", fatal=True)
    if status == 404:
        return AIError("That model was not found. Press 'Load models' and pick one.", fatal=True)
    return AIError(f"The AI service answered with error {status}: {response.text[:200]}")


def _post(url: str, body: dict, headers: dict, timeout: float) -> dict:
    """POST with patience for free-tier rate limits (429): wait and retry a few times."""
    for attempt in range(4):
        try:
            response = httpx.post(url, json=body, headers=headers, timeout=timeout)
        except httpx.ConnectError as error:
            raise AIError("Could not reach the AI. If it runs on this PC, is it started?",
                          fatal=True) from error
        except httpx.HTTPError as error:
            raise AIError(f"The AI did not answer: {error}") from error
        if response.status_code == 429 and attempt < 3:
            wait = response.headers.get("retry-after", "")
            time.sleep(min(float(wait) if wait.replace(".", "").isdigit() else 20, 60))
            continue
        if response.status_code >= 400:
            raise _http_error(response)
        return response.json()
    raise AIError("The AI service is limiting requests. Try again in a few minutes.")


def _gemini(cfg: dict, prompt: str) -> str:
    data = _post(f"{cfg['base_url']}/models/{cfg['model']}:generateContent",
                 {"systemInstruction": {"parts": [{"text": SYSTEM}]},
                  "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                  "generationConfig": {"responseMimeType": "application/json",
                                       "temperature": 0.2}},
                 {"x-goog-api-key": cfg["key"]}, 120)
    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    return "".join(part.get("text", "") for part in parts)


def _openai(cfg: dict, prompt: str) -> str:
    headers = {"Authorization": f"Bearer {cfg['key']}"} if cfg["key"] else {}
    local = cfg["base_url"].startswith(("http://localhost", "http://127.0.0.1"))
    data = _post(f"{cfg['base_url']}/chat/completions",
                 {"model": cfg["model"], "temperature": 0.2,
                  "messages": [{"role": "system", "content": SYSTEM},
                               {"role": "user", "content": prompt}]},
                 headers, 600 if local else 120)  # a local model on a modest PC can be slow
    return (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""


def _claude(cfg: dict, prompt: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=cfg["key"], max_retries=4, timeout=180)
    output_config: dict = {"format": {"type": "json_schema",
                                      "schema": schema(cfg.get("extras", []))}}
    if cfg["model"].startswith(CLAUDE_EFFORT_MODELS):
        output_config["effort"] = "low"  # scoring is classification: low effort holds quality
    request = {"model": cfg["model"], "max_tokens": 16000, "system": SYSTEM,
               "messages": [{"role": "user", "content": prompt}], "output_config": output_config}
    try:
        if cfg["model"] in CLAUDE_FALLBACK_MODELS:
            response = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **request)
        else:
            response = client.messages.create(**request)
    except anthropic.AuthenticationError as error:
        raise AIError("The Claude key was not accepted. Check it on the Smart mode page.",
                      fatal=True) from error
    except anthropic.NotFoundError as error:
        raise AIError("That Claude model was not found. Press 'Load models' and pick one.",
                      fatal=True) from error
    except anthropic.RateLimitError as error:
        raise AIError("Claude is limiting requests. Try again in a few minutes.") from error
    except anthropic.APIStatusError as error:
        raise AIError(f"Claude answered with error {error.status_code}: {error.message}") from error
    except anthropic.APIConnectionError as error:
        raise AIError("Could not reach Claude. Check the internet connection.") from error
    if response.stop_reason == "refusal":
        raise AIError("Claude declined to score this batch.")
    return next((block.text for block in response.content if block.type == "text"), "")


CALLERS = {"gemini": _gemini, "openai": _openai, "anthropic": _claude}


def score(cfg: dict, searched_for: str, leads: list[dict]) -> dict[str, dict]:
    """Score up to BATCH_SIZE leads in one request: place_id -> ai_score/verdict/reason."""
    if cfg.get("kind") != "openai" and not cfg.get("key"):
        raise AIError("Add your AI key on the Smart mode page first.", fatal=True)
    if not cfg.get("model"):
        raise AIError("Pick a model on the Smart mode page first.", fatal=True)
    if not cfg.get("base_url") and cfg["kind"] != "anthropic":
        raise AIError("Enter the AI service's address on the Smart mode page.", fatal=True)
    text = CALLERS[cfg["kind"]](cfg, build_prompt(cfg, searched_for, leads))
    return parse_reply(text, leads, cfg.get("extras", []))


def list_models(cfg: dict) -> list[str]:
    """The models this provider offers to this key, for the model drop-down."""
    try:
        if cfg["kind"] == "anthropic":
            import anthropic

            return [m.id for m in anthropic.Anthropic(api_key=cfg["key"]).models.list()]
        if cfg["kind"] == "gemini":
            response = httpx.get(f"{cfg['base_url']}/models", params={"pageSize": 200},
                                 headers={"x-goog-api-key": cfg["key"]}, timeout=20)
            if response.status_code >= 400:
                raise _http_error(response)
            return [m["name"].removeprefix("models/") for m in response.json().get("models", [])
                    if "generateContent" in m.get("supportedGenerationMethods", [])]
        headers = {"Authorization": f"Bearer {cfg['key']}"} if cfg["key"] else {}
        response = httpx.get(f"{cfg['base_url']}/models", headers=headers, timeout=20)
        if response.status_code >= 400:
            raise _http_error(response)
        return sorted(m["id"] for m in response.json().get("data", []))
    except httpx.ConnectError as error:
        raise AIError("Could not reach the AI. If it runs on this PC, is it started?") from error
    except httpx.HTTPError as error:
        raise AIError(f"Could not load the model list: {error}") from error
    except Exception as error:  # noqa: BLE001 - SDK errors, odd JSON: report, never crash
        if isinstance(error, AIError):
            raise
        raise AIError(f"Could not load the model list: {error}") from error


SAMPLE_LEAD = {"place_id": "test", "name": "Bright Smile Dental Clinic", "category": "Dentist",
               "rating": 4.7, "reviews": 212, "city": "Lahore", "website": "brightsmile.example",
               "emails": "info@brightsmile.example", "company_age": "Established (8 years)",
               "status": "Open"}


def test(cfg: dict) -> dict:
    """Score one made-up lead, proving the key, the model and the JSON all work."""
    result = score(cfg, "dentist in Lahore", [SAMPLE_LEAD])
    if "test" not in result:
        raise AIError("The AI answered, but not with a score. Try a different model.")
    return result["test"]
