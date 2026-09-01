import React, { useEffect, useState } from "react";
import type { QuizSummary } from "@hyris/contracts";
import { fetchHistory } from "../lib/api";

/**
 * The conventional history glyph: a clock wrapped by a counter-clockwise arrow. Drawn on the same
 * 16px grid and 1.4 stroke as the popup's panel icon so the two read as one set.
 */
export function HistoryIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <path
        d="M2.4 6.4A5.9 5.9 0 1 1 2 8.6"
        fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"
      />
      <path
        d="M1.1 3.1v3.4h3.4"
        fill="none" stroke="currentColor" strokeWidth="1.4"
        strokeLinecap="round" strokeLinejoin="round"
      />
      <path
        d="M8 4.8V8l2.1 1.6"
        fill="none" stroke="currentColor" strokeWidth="1.4"
        strokeLinecap="round" strokeLinejoin="round"
      />
    </svg>
  );
}

/** "3 days ago" from an ISO timestamp, in the units a reading habit is actually felt in. */
function since(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.round(ms / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function domainOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

type Load =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; quizzes: QuizSummary[] };

export function History() {
  const [load, setLoad] = useState<Load>({ state: "loading" });

  useEffect(() => {
    let live = true;
    fetchHistory().then(
      (h) => live && setLoad({ state: "ready", quizzes: h.quizzes }),
      (e: unknown) =>
        live && setLoad({ state: "error", message: e instanceof Error ? e.message : String(e) }),
    );
    return () => {
      live = false;
    };
  }, []);

  if (load.state === "loading") return <div className="hist-note micro">Loading…</div>;
  if (load.state === "error") return <div className="hist-note micro">{load.message}</div>;

  if (!load.quizzes.length) {
    return (
      <div className="hist-note micro">
        No quizzes yet. Generate one and it’ll show up here.
      </div>
    );
  }

  return (
    <div>
      <div className="field-label micro">Past quizzes</div>
      {load.quizzes.map((q) => (
        // A summary carries no questions, so this reopens the source rather than the quiz.
        <button
          key={q.id}
          className="hist-row"
          onClick={() => void chrome.tabs.create({ url: q.source_url })}
          title={`Open ${q.source_url}`}
        >
          <span className="hist-title">{q.title}</span>
          <span className="hist-meta micro">
            {domainOf(q.source_url)} · {q.question_count} questions · {since(q.created_at)}
          </span>
        </button>
      ))}
    </div>
  );
}
