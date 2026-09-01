# Hyris

Turn any web page into a personalized quiz. V1 is a LangGraph agent that plans, generates, critiques and adapts, grounded strictly in the current page, with three layers of memory.

▶️ **[Try the live prototype](https://bukunmialuko.github.io/hyris/)** (no install required)


| Aspect | V1 |
|---|---|
| Source of truth | The current page only |
| Orchestration | LangGraph (Postgres checkpointer planned; see Memory model) |
| Memory | Graph checkpoints, quiz and attempt history, learner profile |
| Tools | `clean_page` in V1, fact-check button later |

## Orchestration patterns

Code owns the control flow; the LLM fills in content. Of the classic
[agent workflow patterns](https://www.anthropic.com/engineering/building-effective-agents),
V1 composes three — deliberately stopping short of an autonomous agent:

| Pattern | Where it lives in Hyris |
|---|---|
| Prompt chaining | The backbone: `analyze_page` → `plan_quiz` → `generate_questions`, each step consuming the last one's structured output |
| Parallelization | The START fan-out: `load_memory` runs while the page is fetched and cleaned; branches meet at `plan_quiz` |
| Evaluator-optimizer | The signature loop: `generate_questions` optimizes, `critique_questions` evaluates, repair feeds verdicts back (max 2 rounds) |
| ReAct agent | Not in V1 — reserved for the V2 fact-check button, embedded as a single node |

## Structure

```
apps/extension    Chrome extension (MV3, React + Vite + TS)
apps/api          FastAPI backend (agents: generate → critique → validate)
packages/contracts  Shared quiz JSON schema + fixtures (single source of truth)
design/           Interactive HTML prototype (deployed to GitHub Pages)
research/         Jupyter notebooks for agent prototyping
docs/             Architecture notes
```

## Local development

One conda env covers all the Python here — the API, its dev tooling, and the `research/`
notebooks. Create it once, then just `conda activate agents` whenever you work on Hyris:

```bash
conda create -n agents python=3.11 -y
conda activate agents
pip install -e "apps/api[dev]" -r research/requirements.txt
```

`-e` installs the API in editable mode, so `import app.…` resolves to your working tree and
code changes take effect without reinstalling. `[dev]` adds pytest, httpx and ruff.

Then, with the env active:

```bash
# Extension
npm install
npm run dev:ext          # then load apps/extension/dist as unpacked extension

# API (copy .env.example to .env and set OPENAI_API_KEY first)
uvicorn app.main:app --reload --app-dir apps/api

# Learner profiles survive restarts only when DATABASE_URL is set (see .env.example):
#   docker compose up -d db
#   export DATABASE_URL=postgresql://hyris:hyris@localhost:5433/hyris
#   (cd apps/api && alembic upgrade head)   # creates users/quizzes/attempts
# DATABASE_URL must be EXPORTED for alembic: Settings reads .env relative to the CWD, and the
# .env lives at the repo root, not in apps/api.
# Leave it unset and the API logs a warning and keeps learner memory in-process.
# Caveat: with DATABASE_URL set and Postgres NOT running, the API refuses to start — and under
# --reload uvicorn does not exit, so it hangs instead of aborting. Start the db, or unset the var.

# Or run everything in Docker (API + Postgres) — no conda env needed
docker compose up --build

# Tests (no API key needed — the suite runs on a fake LLM)
pytest apps/api

# Lint
ruff check apps/api
```

### Editor setup

[.vscode/settings.json](.vscode/settings.json) is committed and wires up the rest: it points
Pylance at the `agents` env, puts `apps/api` on the analysis path, enables pytest discovery,
and applies ruff fixes on save. Install the three recommended extensions when VSCode offers
them (Python, Pylance, Ruff).

Two things to know:

- The interpreter path in that file is `/opt/homebrew/anaconda3/envs/agents/bin/python`. If
  your conda lives elsewhere, run `conda run -n agents which python` and update it — or just
  use **Python: Select Interpreter** and pick `agents`.
- If imports still show as unresolved, the env isn't selected. Check the interpreter in the
  status bar with a `.py` file open, then **Developer: Reload Window**.

Ruff's rules live in [apps/api/pyproject.toml](apps/api/pyproject.toml) under `[tool.ruff]`,
so the CLI and the editor always agree.

## Trying the API (Postman or curl)

Generation is asynchronous: start a run, then poll or stream.

```bash
# 1. Start a run — returns 202 with a run_id
curl -X POST http://localhost:8000/quiz/generate \
  -H "Content-Type: application/json" \
  -d '{"page_url": "https://en.wikipedia.org/wiki/Photosynthesis",
       "profile": {"question_count": 4, "difficulty": "medium"}}'

# 2a. Poll until status is done (Postman-friendly)
curl http://localhost:8000/quiz/runs/<run_id>

# 2b. Or stream progress live (SSE)
curl -N http://localhost:8000/quiz/runs/<run_id>/events
```

The poll response carries `status` (running, done, failed), the `steps` completed so far,
and the final `quiz` or a user-safe `error`.

## System design

```mermaid
flowchart LR
  CHROME["🌐 Chrome Extension<br/>popup · quiz side panel"]
  API["⚡ FastAPI<br/>async API · streams progress"]
  AGENT["🕸️ Quiz Agent<br/>LangGraph"]
  TOOL["🧹 clean_page<br/>fetches the page · strips boilerplate"]
  LLM["✨ OpenAI<br/>LLM · swappable"]
  DB[("🐘 Postgres<br/>learner profile · quiz history")]

  CHROME == "url + profile" ==> API
  API -. "live status · finished quiz" .-> CHROME
  CHROME -- "answers" --> API
  API ==> AGENT
  AGENT --- TOOL
  AGENT <--> LLM
  AGENT <--> DB
  API -- "attempts · mastery" --> DB
```

Generation is asynchronous. The extension receives a `run_id` immediately and subscribes to
progress updates, because an LLM pipeline can take 30 to 90 seconds, longer than MV3 service
workers or plain HTTP requests reliably survive. The LangGraph runtime lives inside the
FastAPI process as a single deployable, but it is kept as a separate module so it can be
split out later.

## Agent graph

The LangGraph workflow fans out in parallel from START: the memory read runs while the page
is fetched, and the branches meet at plan_quiz. Tools never raise; failures route to a
graceful exit. Safety guardrails run as first-class nodes: an SSRF check
before any fetch, input moderation before the article reaches an LLM, and output moderation
of every question before delivery — all fail closed, so nothing unsafe ever ships.

```mermaid
flowchart TB
  START(["START"]) --> LM["load_memory<br/>learner profile + recent quizzes"]
  START --> CLEAN["🧹 clean_page<br/>fetch url · strip boilerplate"]
  CLEAN --> OK{"ok?"}
  OK -- "fetch failed" --> FAIL["end_gracefully<br/>stream error to side panel"]
  FAIL --> DONE(["END"])
  OK -- "yes" --> GI["🛡️ guard_input<br/>moderate article · fail closed"]
  GI -- "unsafe" --> FAIL
  GI -- "safe" --> AP["analyze_page<br/>concepts · sufficiency"]
  AP --> SUFF{"enough substance?"}
  SUFF -- "no" --> ADJ["adjust_scope<br/>final = min(requested, cap, supportable)"]
  SUFF -- "yes" --> PLAN
  ADJ --> PLAN["plan_quiz<br/>fan-in: blueprint from concepts + memory"]
  LM --> PLAN
  PLAN --> GENQ["generate_questions<br/>one per blueprint slot"]
  GENQ --> GATE{"schema valid?"}
  GATE -- "invalid, max 2 retries" --> GENQ
  GATE -- "valid" --> CRIT["critique_questions<br/>verdict per question vs article"]
  CRIT --> VERDICT{"all pass or round == 2?"}
  VERDICT -- "failures" --> REGEN["repair_questions<br/>failed slots only, with feedback"]
  REGEN --> GATE
  VERDICT -- "done" --> FIN["finalize_quiz<br/>assemble · persist"]
  FIN --> GO["🛡️ guard_output<br/>moderate every question · fail closed"]
  GO -- "unsafe" --> FAIL
  GO -- "safe" --> WM["write_memory<br/>update learner profile"]
  WM --> DONE
```

## Graph state

Every node reads from and writes to one shared typed state. The parallel branches write
different keys, so the fan-in needs no reducers.

| Field | What it holds | Written by |
|---|---|---|
| `page_url` | The only input from the extension, plus profile settings | input |
| `learner_context` | Mastered concepts, weak concepts, recent question hashes | `load_memory` |
| `clean_text`, `title`, `truncated` | Boilerplate-free article, capped at 6k words | `clean_page` |
| `concepts` | Quiz-worthy concepts with salience and verbatim supporting spans | `analyze_page` |
| `sufficiency`, `max_supportable` | Can the page support the request, and how far | `analyze_page` |
| `final_count`, `note` | `min(requested, cap 20, supportable)` and the user-facing note | `adjust_scope` |
| `blueprint` | Slots: concept, Bloom level, variant flag | `plan_quiz` |
| `questions`, `pending_slots`, `feedback` | Generated questions and the repair queue | `generate_questions`, gate, critic |
| `round`, `gen_retries` | Loop bounds: max 2 repair rounds, max 2 schema retries | gate, critic |
| `quiz` | The final contract-shaped quiz | `finalize_quiz` |
| `error` | User-safe message when a run ends gracefully | any guard or tool |

## Memory model

Three layers, one Postgres instance. **Only the learner profile is wired today** — with
`DATABASE_URL` set, the app lifespan opens one `PostgresStore`, runs its migrations once, and closes
it on shutdown, so mastery and quiz history survive a restart. The other two rows are planned.

| Layer | Kind | Backed by | Status |
|---|---|---|---|
| Graph checkpoints | Thread | LangGraph `PostgresSaver` | **Planned** — still `MemorySaver`, so runs do not survive a restart |
| Quiz and attempt history | Episodic | `quizzes`, `quiz_attempts` tables | **Planned** — tables defined in `models/entities.py`, not yet connected |
| Learner profile | Semantic | LangGraph `PostgresStore` | **Live** — per-concept mastery (EMA) and per-domain question history, persisted |

The loop closes on every attempt: correct answers raise a concept's mastery, wrong answers
lower it, and the next quiz on that topic plans around what changed.

## Guardrails

All safety checks **fail closed**: if a check cannot run, the run ends gracefully — no quiz
ever ships unchecked.

| Stage | Guard | What it blocks |
|---|---|---|
| Before fetch | SSRF guard | Private, loopback, link-local and cloud-metadata addresses |
| Pre-agent | `guard_input` moderation | Pages with self-harm, sexual content involving minors, extremism, weapons instructions — refused before any LLM sees them |
| In every prompt | Injection hardening | Article text is delimited as untrusted data, never instructions |
| During generation | Schema gate + critic | Malformed questions, wrong answer keys, ungrounded or ambiguous questions |
| Post-agent | `guard_output` moderation | Any unsafe generated question, dropped before delivery |

Deferred to the API port: rate limiting, per-user cost caps, auth.

## Quiz planning

The number of questions delivered is `min(requested, hard cap of 20, what the page supports)`.
The planner ranks concepts by the learner's history: weak concepts come first, new material
next, mastered concepts last and one Bloom level harder. When the page has fewer concepts
than requested questions, the planner reuses rich concepts at other Bloom levels (define it,
apply it, analyze it) before shrinking the quiz — and it never pads with trivia. The user is
told only when the delivered count falls notably short.

Example: 6 questions requested from 3 concepts, difficulty hard, with one weak and one
mastered concept in memory:

| Slot | Concept              | Bloom level | Why                          |
|------|----------------------|-------------|------------------------------|
| 0    | multi-head attention | analyse     | weak concept, retest first   |
| 1    | positional encoding  | analyse     | new material                 |
| 2    | self-attention       | evaluate    | mastered, bumped harder      |
| 3    | multi-head attention | evaluate    | variant, next Bloom level    |
| 4    | positional encoding  | evaluate    | variant                      |
| 5    | self-attention       | apply       | variant                      |

Every slot is a unique concept and Bloom level pair, so questions stay distinct.

## V1 scope

Chrome Extension + FastAPI + LangGraph agent + LLM + PostgreSQL. The current page is the only
source of truth. One tool (`clean_page`) and three memory layers: graph checkpoints, quiz and
attempt history, and a learner profile that adapts difficulty over time. No web search, no
RAG, no microservices. In one phrase: an evaluator-optimizer workflow with parallel fan-out.

## License

MIT © 2026 Oluwabukunmi Aluko — see [LICENSE](LICENSE).
