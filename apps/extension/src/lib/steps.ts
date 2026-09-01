// Turning graph node names into something a learner can read.
//
// The names come straight from the API's `steps` array (app/agent/graph.py). Nodes the learner
// gains nothing from seeing — the schema gate, the graceful exit — are mapped to null and skipped,
// so the loader never announces plumbing.

const LABELS: Record<string, string | null> = {
  load_memory: "Recalling what you know…",
  clean_page: "Reading the page…",
  guard_input: "Checking the page is safe…",
  analyze_page: "Finding key concepts…",
  adjust_scope: "Sizing the quiz to the page…",
  plan_quiz: "Planning the questions…",
  generate_questions: "Writing questions…",
  critique_questions: "Checking every answer…",
  finalize_quiz: "Assembling your quiz…",
  guard_output: "Final safety check…",
  write_memory: "Saving what you covered…",

  // Internal control flow, not progress worth narrating.
  schema_gate: null,
  end_gracefully: null,
};

const OPENING = "Starting…";

/**
 * The label for the furthest meaningful step reached.
 *
 * Takes the last showable step rather than the last step outright: `generate_questions` is revisited
 * on every repair round, so a naive "last node" would bounce the learner between "Writing
 * questions" and "Checking every answer". Unknown nodes are ignored rather than shown raw — a node
 * added server-side should not leak an identifier into the UI.
 */
export function progressLabel(steps: string[]): string {
  for (let i = steps.length - 1; i >= 0; i--) {
    const label = LABELS[steps[i]];
    if (label) return label;
  }
  return OPENING;
}

/** How far along the run is, 0-1, for the progress affordance. */
export function progressFraction(steps: string[]): number {
  const total = Object.values(LABELS).filter(Boolean).length;
  const seen = new Set(steps.filter((s) => LABELS[s]));
  return Math.min(seen.size / total, 1);
}
