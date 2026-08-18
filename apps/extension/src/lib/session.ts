// Shape of the generation state the background writes and the side panel reads.

import type { QuizResponse } from "@hyris/contracts";

export const QUIZ_KEY = "currentQuiz";
export const STATUS_KEY = "hyrisStatus";

export interface QuizProfile {
  persona: string;
  difficulty: string;
  question_count: number;
}

// tabId rides along so the panel can retry a failed run on its own.
interface StatusBase {
  runId: number;
  profile: QuizProfile;
  tabId: number;
}

export type QuizStatus =
  | (StatusBase & { state: "loading" })
  | (StatusBase & { state: "ready"; source: string })
  | (StatusBase & { state: "error"; message: string; retriable: boolean });

export interface SessionState {
  status: QuizStatus | null;
  quiz: QuizResponse | null;
}

export async function readSession(): Promise<SessionState> {
  const v = await chrome.storage.session.get([QUIZ_KEY, STATUS_KEY]);
  return {
    status: (v[STATUS_KEY] as QuizStatus) ?? null,
    quiz: (v[QUIZ_KEY] as QuizResponse) ?? null,
  };
}

export function profileSummary(p: QuizProfile): string {
  return `${p.persona} · ${p.difficulty} · ${p.question_count} questions`;
}
