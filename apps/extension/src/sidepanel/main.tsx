import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import type { QuizResponse, QuizQuestion } from "@hyris/contracts";

// TODO: port quiz UI + theming from design/hyris-prototype.html (side panel section)

function SidePanel() {
  const [quiz, setQuiz] = useState<QuizResponse | null>(null);
  const [idx, setIdx] = useState(0);
  const [score, setScore] = useState(0);
  const [picked, setPicked] = useState<number | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    chrome.storage.session.get("currentQuiz").then(({ currentQuiz }) => {
      if (currentQuiz) setQuiz(currentQuiz as QuizResponse);
    });
  }, []);

  if (!quiz) return <p style={{ padding: 24 }}>Generating your quiz…</p>;

  const questions = quiz.quiz.questions;
  const q: QuizQuestion = questions[idx];

  function answer(i: number) {
    if (picked !== null) return;
    setPicked(i);
    if (i === q.correct_answer) setScore((s) => s + 1);
  }

  function next() {
    if (idx + 1 < questions.length) { setIdx(idx + 1); setPicked(null); }
    else setDone(true);
  }

  if (done) {
    const pct = Math.round((score / questions.length) * 100);
    return (
      <div style={{ padding: 24, fontFamily: "Helvetica Neue, sans-serif" }}>
        <h1>{pct}%</h1>
        <p>{score}/{questions.length} correct</p>
      </div>
    );
  }

  return (
    <div style={{ padding: 24, fontFamily: "Helvetica Neue, sans-serif" }}>
      <p style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.16em", opacity: 0.5 }}>
        Question {idx + 1} / {questions.length}
      </p>
      <h2 style={{ fontSize: 18 }}>{q.question}</h2>
      {q.options.map((o, i) => (
        <button key={i} onClick={() => answer(i)}
          style={{ display: "block", width: "100%", textAlign: "left", padding: 14, marginTop: 8,
                   borderRadius: 16, border: 0, cursor: "pointer",
                   background: picked === null ? "#fff" : i === q.correct_answer ? "#d9f2e4" : i === picked ? "#f6dcdc" : "#fff" }}>
          {o}
        </button>
      ))}
      {picked !== null && (
        <>
          {q.explanation && <p style={{ fontSize: 13, opacity: 0.7 }}>{q.explanation}</p>}
          <button onClick={next} style={{ width: "100%", padding: 14, marginTop: 12, borderRadius: 999 }}>
            {idx + 1 === questions.length ? "See results" : "Next"}
          </button>
        </>
      )}
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<SidePanel />);
