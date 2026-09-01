import type { Quiz, QuizQuestion, QuizResponse } from "@hyris/contracts";
import type { PageContent } from "./extract";
import { getUserId } from "./userId";
import { toContractProfile } from "./profile";
import type { QuizProfile } from "./session";

// Both come from .env at the repo root (see .env.example). An explicit fixture
// URL wins; otherwise a live backend is used. There is no baked-in default —
// if neither is set that is a setup problem, and we say so rather than
// quietly pulling someone else's fixture.
const QUIZ_URL = import.meta.env.VITE_QUIZ_URL || "";
const API_BASE = import.meta.env.VITE_API_BASE || "";

/** Misconfiguration rather than a transient failure — retrying cannot help. */
export class ConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ConfigError";
  }
}

export interface QuizResult {
  quiz: QuizResponse;
  source: string;
}

export async function generateQuiz(page: PageContent, profile: QuizProfile): Promise<QuizResult> {
  if (QUIZ_URL) return { quiz: await fetchFixture(QUIZ_URL), source: "remote json" };

  if (API_BASE) return { quiz: await generateViaApi(page, profile), source: "hyris api" };

  throw new ConfigError("No quiz source is configured. Set VITE_QUIZ_URL or VITE_API_BASE in .env, then rebuild.");
}

async function fetchFixture(url: string): Promise<QuizResponse> {
  let r: Response;
  try {
    r = await fetch(url, { cache: "no-store" });
  } catch {
    throw new Error("Couldn’t reach the quiz source. Check your connection.");
  }
  if (!r.ok) throw new Error(`The quiz source answered ${r.status}.`);
  try {
    return await r.json();
  } catch {
    throw new Error("The quiz source didn’t return valid JSON.");
  }
}


// ---------------------------------------------------------------- live backend
//
// /quiz/generate is asynchronous: it answers 202 with a run id, then the graph runs in the
// background. We poll result_url rather than consuming events_url, because EventSource is not
// exposed in an MV3 service worker — which is where this code runs.

/** 202 body from POST /quiz/generate. */
interface RunCreated {
  run_id: string;
  result_url: string;
}

/** GET /quiz/runs/{id}. `quiz` is the bare quiz, not the {quiz} envelope the contract uses. */
interface RunStatus {
  status: "running" | "done" | "failed";
  quiz: (Omit<Quiz, "questions"> & { questions: ApiQuestion[] }) | null;
  error: string | null;
}

/** The API keys questions by slot_id; the contract calls that field id. */
type ApiQuestion = Omit<QuizQuestion, "id"> & { slot_id: number };

// Generation is several LLM round-trips (analyse, write, critique, and up to two repair rounds),
// so the ceiling is generous. Poll gently and back off: a tight loop would just burn the service
// worker's lifetime waiting on a model.
const POLL_TIMEOUT_MS = 180_000;
const POLL_MIN_MS = 600;
const POLL_MAX_MS = 3_000;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function generateViaApi(page: PageContent, profile: QuizProfile): Promise<QuizResponse> {
  // Deliberately not caught: a storage failure must not silently merge this user's history into
  // the shared "anonymous" profile. chrome.storage.sync also fails when sync is disabled or the
  // user is signed out, and that should surface as the extension's normal error state.
  const headers = { "Content-Type": "application/json", "X-User-Id": await getUserId() };

  let started: Response;
  try {
    started = await fetch(`${API_BASE}/quiz/generate`, {
      method: "POST",
      headers,
      // The API takes the page URL and fetches the article itself; it does not want our extracted
      // text. Identity travels in the header, never the body.
      body: JSON.stringify({ page_url: page.url, profile: toContractProfile(profile) }),
    });
  } catch {
    throw new Error("Couldn’t reach the quiz service. Is it running?");
  }
  if (!started.ok) throw new Error(`The quiz service answered ${started.status}.`);

  const { result_url } = (await started.json()) as RunCreated;
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  let wait = POLL_MIN_MS;

  while (Date.now() < deadline) {
    await sleep(wait);
    wait = Math.min(wait * 1.5, POLL_MAX_MS);

    const r = await fetch(`${API_BASE}${result_url}`, { headers, cache: "no-store" });
    if (!r.ok) throw new Error(`The quiz service answered ${r.status}.`);
    const run = (await r.json()) as RunStatus;

    if (run.status === "failed") throw new Error(run.error ?? "The quiz run failed.");
    if (run.status === "done") {
      if (!run.quiz?.questions?.length) throw new Error("The quiz came back empty.");
      return { quiz: toContractQuiz(run.quiz) };
    }
  }
  throw new Error("The quiz took too long. Try again.");
}

/** Wrap the bare quiz in the contract's envelope and give each question the id the contract wants. */
function toContractQuiz(q: NonNullable<RunStatus["quiz"]>): Quiz {
  return {
    ...q,
    questions: q.questions.map(({ slot_id, ...rest }) => ({ ...rest, id: String(slot_id) })),
  };
}
