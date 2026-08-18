# Hyris — Claude instructions

Hyris is a monorepo: a Chrome extension (MV3, React/Vite/TS) in `apps/extension`,
a FastAPI quiz-generation backend in `apps/api`, and the shared quiz JSON contract
in `packages/contracts` (single source of truth — extension consumes it, API produces it).

## Commits

- **One-line conventional commits only.** `type(scope): subject` on a single
  line. No body, no footer, no bullet list.
- **Never add `Co-Authored-By`** or any other trailer. Nothing that attributes
  the commit to Claude.
- **Suggest, never apply.** End a response with a proposed commit when there are
  uncommitted changes worth committing. Only run `git commit` when explicitly
  told to.
- Types: `feat`, `fix`, `refactor`, `docs`, `chore`, `test`, `build`, `perf`.
- Subject in imperative mood, lowercase, no trailing period.
