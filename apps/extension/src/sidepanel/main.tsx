import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import type { QuizQuestion, QuizResponse } from "@hyris/contracts";
import { QuizSetup } from "../components/QuizSetup";
import { usePageProbe } from "../lib/page";
import { useQuizProfile } from "../lib/prefs";
import { useTheme } from "../lib/theme";
import { QUIZ_KEY, STATUS_KEY, profileSummary, readSession, type QuizStatus } from "../lib/session";
import "../styles/theme.css";
import "../styles/sidepanel.css";

const LOAD_STEPS = ["Reading the page…", "Finding key concepts…", "Writing questions…", "Validating quality…"];
const STEP_MS = 750;
const KEYS = "ABCDEF";

function SidePanel() {
  useTheme(); // applies data-theme, kept in sync with the popup

  const [status, setStatus] = useState<QuizStatus | null>(null);
  const [quiz, setQuiz] = useState<QuizResponse | null>(null);

  useEffect(() => {
    readSession().then((s) => { setStatus(s.status); setQuiz(s.quiz); });

    const onChanged = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      if (area !== "session") return;
      if (changes[STATUS_KEY]) setStatus((changes[STATUS_KEY].newValue as QuizStatus) ?? null);
      if (changes[QUIZ_KEY]) setQuiz((changes[QUIZ_KEY].newValue as QuizResponse) ?? null);
    };
    chrome.storage.onChanged.addListener(onChanged);
    return () => chrome.storage.onChanged.removeListener(onChanged);
  }, []);

  return (
    <div className="sp-inner">
      <div className="sp-head">
        <div className="t">
          hyris
          <span className="micro">{status ? "Active recall session" : "Turn this page into a quiz"}</span>
        </div>
        <button className="sp-close" onClick={() => window.close()} title="Close">×</button>
      </div>
      <div className="sp-body">
        <Body status={status} quiz={quiz} />
      </div>
    </div>
  );
}

function Body({ status, quiz }: { status: QuizStatus | null; quiz: QuizResponse | null }) {
  // The prototype waits for both the fetch and the loading animation before
  // showing question 1; keep that beat rather than flashing straight through.
  // Starts true so reopening the panel on an already-finished quiz goes
  // straight to the questions instead of replaying the loader.
  const [stepsDone, setStepsDone] = useState(true);
  const [step, setStep] = useState(0);
  const animatingRun = useRef<number | null>(null);

  useEffect(() => {
    if (status?.state !== "loading" || animatingRun.current === status.runId) return;
    animatingRun.current = status.runId;
    setStepsDone(false);
    setStep(0);
    let i = 0;
    const t = setInterval(() => {
      i++;
      if (i < LOAD_STEPS.length) setStep(i);
      else { clearInterval(t); setStepsDone(true); }
    }, STEP_MS);
    return () => clearInterval(t);
  }, [status?.state, status?.runId]);

  if (!status) return <SetupView />;

  if (status.state === "error") {
    return (
      <div className="loader-wrap">
        <div className="orb dead" />
        <div>
          <div className="load-step micro">Couldn’t build the quiz</div>
          <div className="load-sub msg">{status.message}</div>
        </div>
        {status.retriable && (
          <button
            className="btn-solid retry-btn"
            onClick={() => chrome.runtime.sendMessage({
              type: "HYRIS_GENERATE_QUIZ",
              profile: status.profile,
              tabId: status.tabId,
            })}
          >
            ↻ Try again
          </button>
        )}
      </div>
    );
  }

  if (status.state === "loading" || !quiz || !stepsDone) {
    return (
      <div className="loader-wrap">
        <div className="orb" />
        <div>
          <div className="load-step micro">{LOAD_STEPS[step]}</div>
          <div className="load-sub micro">{profileSummary(status.profile)}</div>
        </div>
      </div>
    );
  }

  return <Quiz key={status.runId} quiz={quiz} source={status.source} />;
}

function SetupView() {
  const [profile, updateProfile] = useQuizProfile();
  const { target, words } = usePageProbe();
  const [busy, setBusy] = useState(false);

  function generate() {
    if (!target) return;
    setBusy(true);
    // The panel is already open, so this only kicks off the run; the status
    // written by the background swaps this view for the loader.
    void chrome.runtime.sendMessage({ type: "HYRIS_GENERATE_QUIZ", profile, tabId: target.tabId });
  }

  return (
    <QuizSetup
      profile={profile}
      onChange={updateProfile}
      onGenerate={generate}
      busy={busy}
      words={words}
      ready={!!target}
    />
  );
}

interface Answered { concept: string; correct: boolean }

function Quiz({ quiz, source }: { quiz: QuizResponse; source: string }) {
  const questions = quiz.quiz.questions;
  const [idx, setIdx] = useState(0);
  const [score, setScore] = useState(0);
  const [picked, setPicked] = useState<number | null>(null);
  const [answered, setAnswered] = useState<Answered[]>([]);
  const [done, setDone] = useState(false);

  function answer(i: number) {
    if (picked !== null) return;
    const q = questions[idx];
    const correct = i === q.correct_answer;
    setPicked(i);
    if (correct) setScore((s) => s + 1);
    setAnswered((a) => [...a, { concept: q.concept ?? "General", correct }]);
  }

  function next() {
    if (idx + 1 >= questions.length) { setDone(true); return; }
    setIdx(idx + 1);
    setPicked(null);
    document.querySelector(".sp-body")?.scrollTo(0, 0);
  }

  function retry() { setIdx(0); setScore(0); setPicked(null); setAnswered([]); setDone(false); }

  if (done) return <Results questions={questions} score={score} answered={answered} source={source} onRetry={retry} />;

  const q: QuizQuestion = questions[idx];
  const progress = ((picked === null ? idx : idx + 1) / questions.length) * 100;

  return (
    <div>
      <div className="progress-row micro">
        <span>Question {idx + 1} / {questions.length}</span>
        <span>{score} correct</span>
      </div>
      <div className="p-track"><div className="p-fill" style={{ width: `${progress}%` }} /></div>

      {q.bloom_level && <span className="bloom micro">{q.bloom_level}</span>}
      <div className="q-text">{q.question}</div>

      <div>
        {q.options.map((o, i) => (
          <button
            key={i}
            className={`opt${optionState(i, picked, q.correct_answer)}`}
            onClick={() => answer(i)}
          >
            <div className="key">{KEYS[i]}</div>
            <div>{o}</div>
          </button>
        ))}
      </div>

      {picked !== null && (
        <>
          <div className="explain">
            <b>{picked === q.correct_answer ? "✓ Correct." : "✗ Not quite."}</b>{" "}
            {q.explanation}
          </div>
          <button className="next-btn" onClick={next}>
            {idx + 1 === questions.length ? "See results" : "Next"}
          </button>
        </>
      )}
    </div>
  );
}

function optionState(i: number, picked: number | null, correct: number): string {
  if (picked === null) return "";
  if (i === correct) return " correct locked";
  if (i === picked) return " wrong locked";
  return " locked";
}

function Results({ questions, score, answered, source, onRetry }: {
  questions: QuizQuestion[];
  score: number;
  answered: Answered[];
  source: string;
  onRetry: () => void;
}) {
  const total = questions.length;
  const pct = Math.round((score / total) * 100);
  const verdict = pct >= 80 ? "strong recall" : pct >= 50 ? "review the gaps" : "worth a re-read";

  // A concept counts as mastered only if every question touching it was correct.
  const byConcept = useMemo(() => {
    const m = new Map<string, boolean>();
    answered.forEach((a) => m.set(a.concept, (m.get(a.concept) ?? true) && a.correct));
    return [...m.entries()];
  }, [answered]);

  async function newQuiz() {
    // Clearing the run drops the panel back to the setup page.
    await chrome.storage.session.remove([QUIZ_KEY, STATUS_KEY]);
  }

  return (
    <div>
      <div className="score-block">
        <div className="score-big">{pct}<span className="dim">%</span></div>
        <div className="res-verdict micro">{score}/{total} correct · {verdict}</div>
      </div>

      <div className="field-label micro">Concepts covered</div>
      {byConcept.map(([concept, ok]) => (
        <div className="concept-row" key={concept}>
          <span>{concept}</span>
          <span className={`pill ${ok ? "good" : "weak"}`}>{ok ? "mastered" : "retest"}</span>
        </div>
      ))}

      <div className="res-actions">
        <button className="btn-ghost" onClick={onRetry}>↻ Retry</button>
        <button className="btn-solid" onClick={newQuiz}>New quiz</button>
      </div>

      <div className="src-note">quiz source: {source}</div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<SidePanel />);
