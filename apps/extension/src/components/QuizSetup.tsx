import React from "react";
import type { QuizProfile } from "../lib/session";

const PERSONAS = [
  { value: "High School", label: "High School" },
  { value: "Undergraduate", label: "Undergrad" },
  { value: "Master's", label: "Master's" },
  { value: "Research", label: "Research" },
];
const DIFFICULTIES = ["Easy", "Medium", "Hard", "Expert"];
const COUNTS = [5, 10, 15];

/**
 * The quiz setup form. Rendered in the popup body and, when the panel is
 * pinned, in the panel itself — pinning shows this same page, docked.
 */
export function QuizSetup({ profile, onChange, onGenerate, busy, words, ready }: {
  profile: QuizProfile;
  onChange: (patch: Partial<QuizProfile>) => void;
  onGenerate: () => void;
  busy: boolean;
  words: number | null;
  ready: boolean;
}) {
  return (
    <>
      <div className="field-label micro">Persona</div>
      <Seg options={PERSONAS} value={profile.persona} onChange={(persona) => onChange({ persona })} />

      <div className="field-label micro">Difficulty</div>
      <Seg
        options={DIFFICULTIES.map((d) => ({ value: d, label: d }))}
        value={profile.difficulty}
        onChange={(difficulty) => onChange({ difficulty })}
      />

      <div className="field-label micro">Questions</div>
      <Seg
        options={COUNTS.map((c) => ({ value: c, label: String(c) }))}
        value={profile.question_count}
        onChange={(question_count) => onChange({ question_count })}
      />

      <button className="gen-btn" onClick={onGenerate} disabled={busy || !ready}>
        {busy ? "Generating…" : "Generate quiz"}
      </button>

      <PageDetect words={words} />
    </>
  );
}

function PageDetect({ words }: { words: number | null }) {
  if (words === null) {
    return <div className="page-detect micro none"><div className="dot" />reading this page…</div>;
  }
  if (words === 0) {
    return <div className="page-detect micro none"><div className="dot" />no text found on this page</div>;
  }
  return (
    <div className="page-detect micro">
      <div className="dot" />
      page detected · ~{roundWords(words).toLocaleString()} words
    </div>
  );
}

function roundWords(n: number): number {
  return n >= 1000 ? Math.round(n / 100) * 100 : n;
}

function Seg<T extends string | number>({ options, value, onChange }: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="seg">
      {options.map((o) => (
        <button
          key={String(o.value)}
          className={`chip${o.value === value ? " sel" : ""}`}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
