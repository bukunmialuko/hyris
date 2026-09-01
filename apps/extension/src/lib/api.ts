import type {
  AttemptRequest,
  AttemptResult,
  Quiz,
  QuizHistory,
  RunCreated,
  RunStatus,
} from "@hyris/contracts";
import type { PageContent } from "./extract";
import { authHeaders, forgetDevice } from "./identity";
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
  quiz: Quiz;
  source: string;
}

/** Called on every poll with the graph nodes finished so far. */
export type OnProgress = (steps: string[]) => void;

export async function generateQuiz(
  page: PageContent,
  profile: QuizProfile,
  onProgress: OnProgress,
): Promise<QuizResult> {
  if (QUIZ_URL) return { quiz: await fetchFixture(QUIZ_URL), source: "remote json" };

  if (API_BASE) return { quiz: await generateViaApi(page, profile, onProgress), source: "hyris api" };

  throw new ConfigError("No quiz source is configured. Set VITE_QUIZ_URL or VITE_API_BASE in .env, then rebuild.");
}

async function fetchFixture(url: string): Promise<Quiz> {
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

/**
 * One authenticated request, re-registering once on 401.
 *
 * A 401 means the token no longer verifies — almost always a rotated AUTH_SECRET. Dropping the
 * device and registering again recovers silently; the learner loses their history, but the
 * alternative is an extension that is permanently broken until reinstalled.
 */
async function authed(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
  const headers = { ...(init.headers as Record<string, string>), ...(await authHeaders(API_BASE)) };

  let r: Response;
  try {
    r = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new Error("Couldn’t reach the quiz service. Is it running?");
  }

  if (r.status === 401 && retry) {
    await forgetDevice();
    return authed(path, init, false);
  }
  return r;
}

const json = { "Content-Type": "application/json" };

// Generation is several LLM round-trips (analyse, write, critique, and up to two repair rounds),
// so the ceiling is generous. Poll gently and back off: a tight loop would just burn the service
// worker's lifetime waiting on a model.
//
// We poll rather than consuming events_url because EventSource is not exposed in an MV3 service
// worker, which is where this runs — and keeping the run owned by the worker means it survives the
// side panel being closed. The poll response carries the same step names the SSE stream does.
const POLL_TIMEOUT_MS = 180_000;
const POLL_MIN_MS = 600;
const POLL_MAX_MS = 3_000;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function generateViaApi(
  page: PageContent,
  profile: QuizProfile,
  onProgress: OnProgress,
): Promise<Quiz> {
  const started = await authed("/quiz/generate", {
    method: "POST",
    headers: json,
    // The API takes the page URL and fetches the article itself; it does not want our extracted
    // text. Identity travels in the header, never the body.
    body: JSON.stringify({ page_url: page.url, profile: toContractProfile(profile) }),
  });
  if (!started.ok) throw new Error(`The quiz service answered ${started.status}.`);

  const { result_url } = (await started.json()) as RunCreated;
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  let wait = POLL_MIN_MS;

  while (Date.now() < deadline) {
    await sleep(wait);
    wait = Math.min(wait * 1.5, POLL_MAX_MS);

    const r = await authed(result_url, { cache: "no-store" });
    if (!r.ok) throw new Error(`The quiz service answered ${r.status}.`);
    const run = (await r.json()) as RunStatus;

    onProgress(run.steps ?? []);

    if (run.status === "failed") throw new Error(run.error ?? "The quiz run failed.");
    if (run.status === "done") {
      if (!run.quiz?.questions?.length) throw new Error("The quiz came back empty.");
      return run.quiz;
    }
  }
  throw new Error("The quiz took too long. Try again.");
}

// -------------------------------------------------------------------- attempts

/**
 * Submit answers for server-side scoring. The server scores against the quiz it stored rather than
 * trusting us, and moves per-concept mastery — which is what makes the next quiz adapt.
 *
 * `attemptId` is an idempotency key: resubmitting the same one records nothing and moves no
 * mastery, so a retried request cannot double-count. A genuine retake must pass a fresh one.
 */
export async function submitAttempt(
  quizId: string,
  answers: Record<string, number>,
  attemptId: string,
): Promise<AttemptResult> {
  const body: AttemptRequest = { quiz_id: quizId, answers, attempt_id: attemptId };
  const r = await authed("/attempts", { method: "POST", headers: json, body: JSON.stringify(body) });

  // 404 means the quiz was never persisted, which is every run on a server without DATABASE_URL.
  if (r.status === 404) throw new Error("This quiz isn’t on the server, so the result wasn’t saved.");
  if (!r.ok) throw new Error(`The quiz service answered ${r.status}.`);
  return (await r.json()) as AttemptResult;
}

// --------------------------------------------------------------------- history

export async function fetchHistory(limit = 20): Promise<QuizHistory> {
  const r = await authed(`/quizzes?limit=${limit}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`The quiz service answered ${r.status}.`);
  return (await r.json()) as QuizHistory;
}

/** History is only reachable against a live backend; fixture mode has none. */
export const historyAvailable = !QUIZ_URL && !!API_BASE;
