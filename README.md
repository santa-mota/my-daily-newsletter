# My Daily Newsletter

Personal **AI news + research digest** delivered over **WhatsApp**, with hooks for **LLM generation**, **preference overrides**, **saved items** (reactions), and **scheduled** daily sends.

## Quick start

```bash
cd my-daily-newsletter
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# Edit .env — see comments inside.

uvicorn newsletter.app:app --reload --port 8000
```

Expose `POST /webhooks/whatsapp` (and `GET` for verification) on the public internet with HTTPS (e.g. VPS + reverse proxy, or a tunnel in dev). Configure the same URL in Meta’s WhatsApp Cloud API webhook settings.

## Layout

- `src/newsletter/` — FastAPI app, WhatsApp client, persistence, digest orchestration stubs.
- `src/newsletter/prompt_data/daily_digest_system.md` — Verbose system prompt for the digest generator.
- `.env.example` — Required secrets and tuning.

## Validation

There is no `mint` target in this repo. After changes: `python -m compileall src` and fix any issues reported by your editor / `ruff` if installed.
