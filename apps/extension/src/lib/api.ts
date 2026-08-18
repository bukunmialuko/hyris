import type { QuizResponse } from "@hyris/contracts";
import type { PageContent } from "./extract";
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

  if (API_BASE) {
    const r = await fetch(`${API_BASE}/quiz/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page, profile: toContractProfile(profile) }),
    });
    if (!r.ok) throw new Error(`The quiz service answered ${r.status}.`);
    return { quiz: await r.json(), source: "hyris api" };
  }

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
