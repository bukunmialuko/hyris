import { describe, expect, it } from "vitest";
import { toContractProfile } from "../profile";

describe("toContractProfile", () => {
  it("maps UI labels onto the contract's enums", () => {
    expect(toContractProfile({ persona: "Master's", difficulty: "Hard", question_count: 5 }))
      .toEqual({
        education_level: "masters",
        difficulty: "hard",
        question_count: 5,
        allow_trick_questions: false,
        require_explanations: true,
      });
  });

  it("falls back to masters for an unknown persona", () => {
    const p = toContractProfile({ persona: "Nonsense", difficulty: "Easy", question_count: 3 });
    expect(p.education_level).toBe("masters");
  });

  // These were sent for weeks and silently dropped by Pydantic. Nothing should reintroduce them.
  it("sends no fields the API does not define", () => {
    const p = toContractProfile({ persona: "Research", difficulty: "Expert", question_count: 8 });
    expect(Object.keys(p).sort()).toEqual([
      "allow_trick_questions", "difficulty", "education_level", "question_count", "require_explanations",
    ]);
  });
});
