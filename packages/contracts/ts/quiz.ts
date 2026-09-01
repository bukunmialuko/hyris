// The API boundary, hand-maintained against apps/api/app/schemas/quiz.py.
//
// Not generated: `npm run types` runs json2ts over quiz.schema.json, which describes the quiz
// payload alone and cannot express the run, attempt and history shapes below. Change a Pydantic
// model, change this file.

export type EducationLevel = "high_school" | "undergraduate" | "masters" | "research";
export type Difficulty = "easy" | "medium" | "hard" | "expert";
export type BloomLevel = "remember" | "understand" | "apply" | "analyse" | "evaluate" | "create";
export type RunState = "running" | "done" | "failed";

export interface QuestionProfile {
  education_level: EducationLevel;
  difficulty: Difficulty;
  question_count: number;
  allow_trick_questions?: boolean;
  require_explanations?: boolean;
}

export interface QuizQuestion {
  /** The blueprint slot this question fills. Unique within a quiz, and the key an attempt uses. */
  slot_id: number;
  concept?: string | null;
  bloom_level?: BloomLevel | null;
  question: string;
  /** Always four; the API pins min_length=4, max_length=4. */
  options: string[];
  /** Index into `options`, 0-3. */
  correct_answer: number;
  explanation?: string | null;
}

export interface Quiz {
  id: string;
  title: string;
  /** Set when the delivered count falls notably short of the request. */
  note?: string;
  /** The article was longer than MAX_WORDS and was cut. */
  truncated?: boolean;
  questions: QuizQuestion[];
}

// ------------------------------------------------------------------ runs

export interface GenerateRequest {
  page_url: string;
  profile: QuestionProfile;
}

export interface RunCreated {
  run_id: string;
  events_url: string;
  result_url: string;
}

export interface RunStatus {
  run_id: string;
  status: RunState;
  /** Graph node names, in the order they completed. Empty when rebuilt from a checkpoint. */
  steps: string[];
  quiz: Quiz | null;
  error: string | null;
}

// -------------------------------------------------------------- attempts

export interface AttemptRequest {
  quiz_id: string;
  /** {stringified slot_id: chosen option index}. An omitted question is marked wrong. */
  answers: Record<string, number>;
  /** Idempotency key: resubmitting the same one records nothing and moves no mastery. */
  attempt_id?: string;
}

export interface QuestionResult {
  question_id: string;
  concept?: string | null;
  picked: number | null;
  correct_answer: number;
  correct: boolean;
}

export interface AttemptResult {
  attempt_id: string;
  quiz_id: string;
  score: number;
  total: number;
  results: QuestionResult[];
}

// --------------------------------------------------------------- history

export interface QuizSummary {
  id: string;
  title: string;
  source_url: string;
  question_count: number;
  /** ISO 8601. */
  created_at: string;
}

export interface QuizHistory {
  quizzes: QuizSummary[];
}

// ------------------------------------------------------------------ auth

export interface DeviceToken {
  user_id: string;
  token: string;
}
