// Hand-written for now; regenerate from quiz.schema.json with `npm run types`.

export type EducationLevel = "high_school" | "undergraduate" | "masters" | "research";
export type Difficulty = "easy" | "medium" | "hard" | "expert";
export type BloomLevel = "remember" | "understand" | "apply" | "analyse" | "evaluate" | "create";

export interface QuestionProfile {
  education_level: EducationLevel;
  difficulty: Difficulty;
  cognitive_level: string;
  question_style?: string;
  question_count: number;
  allow_trick_questions?: boolean;
  require_explanations?: boolean;
}

export interface QuizQuestion {
  id: string;
  bloom_level?: BloomLevel;
  concept?: string;
  question: string;
  options: string[];
  correct_answer: number;
  explanation?: string;
}

export interface Quiz {
  id: string;
  title: string;
  source?: {
    url?: string;
    page_title?: string;
    extracted_at?: string;
  };
  profile?: QuestionProfile;
  concepts?: string[];
  questions: QuizQuestion[];
}

export interface QuizResponse {
  quiz: Quiz;
}
