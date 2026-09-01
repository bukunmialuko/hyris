import type { Difficulty, EducationLevel, QuestionProfile } from "@hyris/contracts";
import type { QuizProfile } from "./session";

// The popup speaks in labels; the API speaks in the contract's enums.
const EDUCATION_LEVEL: Record<string, EducationLevel> = {
  "High School": "high_school",
  "Undergraduate": "undergraduate",
  "Master's": "masters",
  "Research": "research",
};

export function toContractProfile(p: QuizProfile): QuestionProfile {
  return {
    education_level: EDUCATION_LEVEL[p.persona] ?? "masters",
    difficulty: p.difficulty.toLowerCase() as Difficulty,
    question_count: p.question_count,
    allow_trick_questions: false,
    require_explanations: true,
  };
}
