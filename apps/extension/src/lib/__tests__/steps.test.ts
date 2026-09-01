import { describe, expect, it } from "vitest";
import { progressFraction, progressLabel } from "../steps";

describe("progressLabel", () => {
  it("opens with a neutral line before the graph reports anything", () => {
    expect(progressLabel([])).toBe("Starting…");
  });

  it("names the furthest step reached", () => {
    expect(progressLabel(["load_memory", "clean_page", "analyze_page"]))
      .toBe("Finding key concepts…");
  });

  // The repair loop routes back through generate_questions, so the raw last node oscillates.
  // Showing the last *showable* one keeps the loader moving forward.
  it("does not go backwards across a repair round", () => {
    const label = progressLabel([
      "generate_questions", "schema_gate", "critique_questions", "generate_questions",
    ]);
    expect(label).toBe("Writing questions…");
  });

  it("skips internal plumbing rather than announcing it", () => {
    expect(progressLabel(["plan_quiz", "schema_gate"])).toBe("Planning the questions…");
    expect(progressLabel(["end_gracefully"])).toBe("Starting…");
  });

  // A node added server-side must never leak a raw identifier into the UI.
  it("ignores nodes it does not recognise", () => {
    expect(progressLabel(["analyze_page", "some_new_node"])).toBe("Finding key concepts…");
  });
});

// Recorded from a real run against the live API (Wikipedia/Photosynthesis, 4 questions, 87s).
// If the graph gains or renames a node, this is what will notice.
const REAL_RUN = [
  "load_memory", "clean_page", "guard_input", "analyze_page", "adjust_scope", "plan_quiz",
  "generate_questions", "schema_gate", "critique_questions", "finalize_quiz",
  "guard_output", "write_memory",
];

describe("a recorded run", () => {
  it("has a label for every node the graph actually emits", () => {
    const unlabelled = REAL_RUN.filter((n) => progressLabel([n]) === "Starting…" && n !== "schema_gate");
    expect(unlabelled).toEqual([]);
  });

  it("advances monotonically and ends on the last real step", () => {
    const seen = REAL_RUN.map((_, i) => progressFraction(REAL_RUN.slice(0, i + 1)));
    expect(seen).toEqual([...seen].sort((a, b) => a - b));
    expect(progressLabel(REAL_RUN)).toBe("Saving what you covered…");
    expect(progressFraction(REAL_RUN)).toBe(1);
  });
});

describe("progressFraction", () => {
  it("runs from nothing to complete", () => {
    expect(progressFraction([])).toBe(0);
    expect(progressFraction(["clean_page"])).toBeGreaterThan(0);
  });

  it("counts each node once, so repair rounds cannot overflow the bar", () => {
    const once = progressFraction(["generate_questions"]);
    const thrice = progressFraction(["generate_questions", "generate_questions", "generate_questions"]);
    expect(thrice).toBe(once);
    expect(progressFraction(Array(50).fill("generate_questions"))).toBeLessThanOrEqual(1);
  });
});
