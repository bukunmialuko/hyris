# Hyris

Turn any web page into an AI-generated quiz. Read → click → quiz in the side panel.

**[Live prototype →](https://bukunmialuko.github.io/hyris/)** — interactive walkthrough of the extension UI, no install required.

## Structure

```
apps/extension    Chrome extension (MV3, React + Vite + TS)
apps/api          FastAPI backend (agents: generate → critique → validate)
packages/contracts  Shared quiz JSON schema + fixtures (single source of truth)
design/           Interactive HTML prototype (deployed to GitHub Pages)
docs/             Architecture notes
```

## Quick start

```bash
# Extension
npm install
npm run dev:ext          # then load apps/extension/dist as unpacked extension

# API
cd apps/api
pip install -e ".[dev]"
uvicorn app.main:app --reload

# Local Postgres
docker compose up -d
```

## The contract

`packages/contracts/quiz.schema.json` defines the quiz shape. The extension consumes it,
the API produces it. During development the extension can point at
`packages/contracts/fixtures/hyris-quiz.json` (e.g. via a GitHub raw URL) instead of the API.

## Prototype deploy

`.github/workflows/pages.yml` publishes `design/hyris-prototype.html` to GitHub Pages as the
site root. It redeploys on every push to `main` that touches the prototype, and can be run
manually from the Actions tab.

## V1 scope

Chrome Extension + FastAPI + LLM + PostgreSQL. No RAG, no vector DB, no microservices.

## License

MIT © 2026 Oluwabukunmi Aluko — see [LICENSE](LICENSE).
