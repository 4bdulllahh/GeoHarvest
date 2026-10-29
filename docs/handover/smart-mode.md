# Smart mode

The AI that scores leads. Code: `app/core/ai.py`, `app/workers/ai.py`, `app/ui/pages/smart.py`, `app/core/credentials.py`. Decisions already made: don't re-ask them. Each row says what was chosen and why.

| Topic | Decision |
|---|---|
| AI providers | All of them, user brings their own key: Gemini (plain HTTPS, JSON mode), Claude (official `anthropic` SDK: structured JSON output, effort `low`, server-side refusal fallbacks on Opus 5.5 / Opus 5 / Sonnet 5.5 / Fable 5.1; default model `claude-opus-5-5`, note suggests Haiku 5.5 as cheapest), and one OpenAI-compatible connector (plain HTTPS) with presets for Groq, OpenRouter, Mistral, OpenAI, DeepSeek, Ollama and LM Studio (local), plus a custom URL. Default model names for non-Claude providers may go stale: the "Load models" button lists the real ones. Keys are DPAPI-encrypted in `%APPDATA%/GeoHarvest/secrets.dat` (`app/core/credentials.py`, from HomingPigeon) |
| AI keys | **No built-in API key anywhere** (user's explicit rule, 2026-10-17). Every provider uses only the key the user enters on the Smart mode page, stored DPAPI-encrypted. The only `api_key=` literal is `run.py`'s self-test sending "test" to a closed local port. Keep the official `anthropic` SDK (user said keep it; it costs ~5 MB) |
