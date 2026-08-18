import type { Difficulty, EducationLevel, QuestionProfile } from "@hyris/contracts";
import type { QuizProfile } from "./session";

// The popup speaks in labels; the API speaks in the contract's enums.
const EDUCATION_LEVEL: Record<string, EducationLevel> = {
  "High School": "high_school",
  "Undergraduate": "undergraduate",
  "Master's": "masters",
  "Research": "research",
};

const COGNITIVE_LEVEL: Record<string, string> = {
  Easy: "recall",
  Medium: "comprehension",
  Hard: "analysis",
  Expert: "evaluation",
};

export function toContractProfile(p: QuizProfile): QuestionProfile {
  return {
    education_level: EDUCATION_LEVEL[p.persona] ?? "masters",
    difficulty: p.difficulty.toLowerCase() as Difficulty,
    cognitive_level: COGNITIVE_LEVEL[p.difficulty] ?? "analysis",
    question_style: "conceptual",
    question_count: p.question_count,
    allow_trick_questions: false,
    require_explanations: true,
  };
}
