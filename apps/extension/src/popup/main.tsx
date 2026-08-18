import React, { useState } from "react";
import { createRoot } from "react-dom/client";

// TODO: port the styling from design/hyris-prototype.html (popup section)

const PERSONAS = ["High School", "Undergrad", "Master's", "Research"] as const;
const DIFFICULTIES = ["Easy", "Medium", "Hard", "Expert"] as const;
const COUNTS = [5, 10, 15] as const;

function Popup() {
  const [persona, setPersona] = useState<string>("Master's");
  const [difficulty, setDifficulty] = useState<string>("Hard");
  const [count, setCount] = useState<number>(5);
  const [busy, setBusy] = useState(false);

  async function generate() {
    setBusy(true);
    const profile = { persona, difficulty, question_count: count };
    await chrome.runtime.sendMessage({ type: "HYRIS_GENERATE_QUIZ", profile });
    window.close(); // side panel takes over
  }

  return (
    <div style={{ width: 360, padding: 20, fontFamily: "Helvetica Neue, sans-serif" }}>
      <h1 style={{ fontSize: 17 }}>hyris</h1>
      <Selector label="Persona" options={PERSONAS} value={persona} onChange={setPersona} />
      <Selector label="Difficulty" options={DIFFICULTIES} value={difficulty} onChange={setDifficulty} />
      <Selector label="Questions" options={COUNTS} value={count} onChange={setCount} />
      <button onClick={generate} disabled={busy} style={{ width: "100%", marginTop: 16, padding: 14, borderRadius: 999 }}>
        {busy ? "Generating…" : "Generate quiz"}
      </button>
    </div>
  );
}

function Selector<T extends string | number>({ label, options, value, onChange }: {
  label: string; options: readonly T[]; value: T; onChange: (v: T) => void;
}) {
  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.16em", opacity: 0.5 }}>{label}</div>
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
        {options.map((o) => (
          <button key={String(o)} onClick={() => onChange(o)}
            style={{ padding: "8px 14px", borderRadius: 999, border: 0, cursor: "pointer",
                     background: o === value ? "#111114" : "#fff", color: o === value ? "#fff" : "#555" }}>
            {o}
          </button>
        ))}
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<Popup />);
