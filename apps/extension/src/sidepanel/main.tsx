import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import type { AttemptResult, Quiz as QuizPayload, QuizQuestion } from "@hyris/contracts";
import { QuizSetup } from "../components/QuizSetup";
import { History, HistoryIcon } from "../components/History";
import { historyAvailable, submitAttempt } from "../lib/api";
import { usePageProbe } from "../lib/page";
import { useQuizProfile } from "../lib/prefs";
import { progressFraction, progressLabel } from "../lib/steps";
import { useTheme } from "../lib/theme";
import { QUIZ_KEY, STATUS_KEY, profileSummary, readSession, type QuizStatus } from "../lib/session";
import "../styles/theme.css";
import "../styles/sidepanel.css";

const KEYS = "ABCDEF";

function SidePanel() {
  useTheme(); // applies data-theme, kept in sync with the popup

  const [status, setStatus] = useState<QuizStatus | null>(null);
  const [quiz, setQuiz] = useState<QuizPayload | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    readSession().then((s) => { setStatus(s.status); setQuiz(s.quiz); });

    const onChanged = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      if (area !== "session") return;
      if (changes[STATUS_KEY]) setStatus((changes[STATUS_KEY].newValue as QuizStatus) ?? null);
      if (changes[QUIZ_KEY]) setQuiz((changes[QUIZ_KEY].newValue as QuizPayload) ?? null);
    };
    chrome.storage.onChanged.addListener(onChanged);
    return () => chrome.storage.onChanged.removeListener(onChanged);
  }, []);

  const subtitle = showHistory
    ? "What you’ve covered"
    : status ? "Active recall session" : "Turn this page into a quiz";

  return (
    <div className="sp-inner">
      <div className="sp-head">
        <div className="t">
          hyris
          <span className="micro">{subtitle}</span>
        </div>
        <div className="sp-actions">
          {historyAvailable && (
            <button
              className={`sp-icon${showHistory ? " on" : ""}`}
              onClick={() => setShowHistory((v) => !v)}
              title={showHistory ? "Back to the quiz" : "Past quizzes"}
              aria-label={showHistory ? "Back to the quiz" : "Past quizzes"}
              aria-pressed={showHistory}
            >
              <HistoryIcon />
            </button>
          )}
          <button className="sp-icon" onClick={() => window.close()} title="Close" aria-label="Close">×</button>
        </div>
      </div>
      <div className="sp-body">
        {showHistory ? <History /> : <Body status={status} quiz={quiz} />}
      </div>
    </div>
  );
}

function Body({ status, quiz }: { status: QuizStatus | null; quiz: QuizPayload | null }) {
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

  // Real progress, reported by the graph itself — the run takes as long as it takes.
  if (status.state === "loading" || !quiz) {
    const steps = status.state === "loading" ? status.steps : [];
    return (
      <div className="loader-wrap">
        <div className="orb" />
        <div>
          <div className="load-step micro">{progressLabel(steps)}</div>
          <div className="load-sub micro">{profileSummary(status.profile)}</div>
        </div>
        <div className="p-track run">
          <div className="p-fill" style={{ width: `${progressFraction(steps) * 100}%` }} />
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

/** What the results screen renders: the server's verdict, or ours if it couldn't be reached. */
type Outcome =
  | { kind: "server"; result: AttemptResult }
  | { kind: "local"; score: number; total: number; concepts: [string, boolean][]; reason: string };

function Quiz({ quiz, source }: { quiz: QuizPayload; source: string }) {
  const questions = quiz.questions;
  const [idx, setIdx] = useState(0);
  const [picked, setPicked] = useState<number | null>(null);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // A fresh key per sitting. Retrying a failed submit reuses it so the server can't double-count;
  // retaking the quiz mints a new one, or the server would record nothing and mastery would
  // never move.
  const [attemptId, setAttemptId] = useState(() => crypto.randomUUID());

  const score = useMemo(
    () => questions.filter((q) => answers[String(q.slot_id)] === q.correct_answer).length,
    [answers, questions],
  );

  function answer(i: number) {
    if (picked !== null) return;
    setPicked(i);
    setAnswers((a) => ({ ...a, [String(questions[idx].slot_id)]: i }));
  }

  async function finish(final: Record<string, number>) {
    setSubmitting(true);
    try {
      setOutcome({ kind: "server", result: await submitAttempt(quiz.id, final, attemptId) });
    } catch (e) {
      // Never lose the learner's result to a network problem — show ours and say it didn't sync.
      setOutcome({
        kind: "local",
        score: questions.filter((q) => final[String(q.slot_id)] === q.correct_answer).length,
        total: questions.length,
        concepts: localConcepts(questions, final),
        reason: e instanceof Error ? e.message : String(e),
      });
    } finally {
      setSubmitting(false);
    }
  }

  function next() {
    if (idx + 1 >= questions.length) { void finish(answers); return; }
    setIdx(idx + 1);
    setPicked(null);
    document.querySelector(".sp-body")?.scrollTo(0, 0);
  }

  function retry() {
    setIdx(0);
    setPicked(null);
    setAnswers({});
    setOutcome(null);
    setAttemptId(crypto.randomUUID()); // a genuine retake, not a resubmit
  }

  if (submitting) {
    return (
      <div className="loader-wrap">
        <div className="orb" />
        <div className="load-step micro">Scoring…</div>
      </div>
    );
  }

  if (outcome) {
    return (
      <Results
        outcome={outcome}
        source={source}
        onRetry={retry}
        onResubmit={() => void finish(answers)}
      />
    );
  }

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

/** Offline stand-in for the server's per-concept view: a concept holds only if every question on
 *  it was right. Coarser than the server's EMA, which is why it is the fallback and not the rule. */
function localConcepts(questions: QuizQuestion[], answers: Record<string, number>): [string, boolean][] {
  const m = new Map<string, boolean>();
  for (const q of questions) {
    const name = q.concept ?? "General";
    const ok = answers[String(q.slot_id)] === q.correct_answer;
    m.set(name, (m.get(name) ?? true) && ok);
  }
  return [...m.entries()];
}

function Results({ outcome, source, onRetry, onResubmit }: {
  outcome: Outcome;
  source: string;
  onRetry: () => void;
  onResubmit: () => void;
}) {
  const score = outcome.kind === "server" ? outcome.result.score : outcome.score;
  const total = outcome.kind === "server" ? outcome.result.total : outcome.total;
  const pct = total ? Math.round((score / total) * 100) : 0;
  const verdict = pct >= 80 ? "strong recall" : pct >= 50 ? "review the gaps" : "worth a re-read";

  // The server reports per question; fold to per concept, which is the unit mastery moves in.
  const concepts = useMemo<[string, boolean][]>(() => {
    if (outcome.kind === "local") return outcome.concepts;
    const m = new Map<string, boolean>();
    for (const r of outcome.result.results) {
      const name = r.concept ?? "General";
      m.set(name, (m.get(name) ?? true) && r.correct);
    }
    return [...m.entries()];
  }, [outcome]);

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

      {outcome.kind === "local" && (
        <div className="sync-warn micro">
          Scored on this device — {outcome.reason}{" "}
          <button className="link-btn" onClick={onResubmit}>Try syncing again</button>
        </div>
      )}

      <div className="field-label micro">Concepts covered</div>
      {concepts.map(([concept, ok]) => (
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
