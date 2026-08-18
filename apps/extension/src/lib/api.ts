import type { QuizResponse } from "@hyris/contracts";

// While the backend isn't live, point this at your GitHub raw fixture:
// https://raw.githubusercontent.com/<user>/<repo>/main/packages/contracts/fixtures/hyris-quiz.json
const QUIZ_URL = import.meta.env.VITE_QUIZ_URL ?? "";
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export async function generateQuiz(page: unknown, profile: unknown): Promise<QuizResponse> {
  // Mock mode: static JSON (ignores page/profile)
  if (QUIZ_URL) {
    const r = await fetch(QUIZ_URL, { cache: "no-store" });
    if (!r.ok) throw new Error(`Fixture fetch failed: ${r.status}`);
    return r.json();
  }

  // Real mode: FastAPI backend
  const r = await fetch(`${API_BASE}/quiz/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page, profile }),
  });
  if (!r.ok) throw new Error(`Quiz generation failed: ${r.status}`);
  return r.json();
}
