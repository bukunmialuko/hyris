import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { QuizSetup } from "../components/QuizSetup";
import { usePageProbe } from "../lib/page";
import { useQuizProfile } from "../lib/prefs";
import { useTheme } from "../lib/theme";
import "../styles/theme.css";
import "../styles/popup.css";

function Popup() {
  const [theme, toggleTheme] = useTheme();
  const [profile, updateProfile] = useQuizProfile();
  const { target, words } = usePageProbe();
  const [busy, setBusy] = useState(false);

  // Docks the panel showing this same setup page — no quiz is generated.
  function pinPanel() {
    if (!target) return;
    void chrome.sidePanel.open({ windowId: target.windowId }).catch(() => {});
    window.close();
  }

  function generate() {
    if (!target) return;
    setBusy(true);
    // Open for the window, not the tab, so the panel stays docked to the right
    // edge as you move between tabs. Must be first — it needs a live gesture.
    void chrome.sidePanel.open({ windowId: target.windowId }).catch(() => {});
    chrome.runtime.sendMessage({ type: "HYRIS_GENERATE_QUIZ", profile, tabId: target.tabId }).then(
      () => window.close(),
      () => setBusy(false),
    );
  }

  return (
    <>
      <div className="popup-head">
        <div className="t">hyris<small>Turn this page into a quiz</small></div>
        <div className="actions">
          <button className="theme-toggle micro" onClick={toggleTheme} title={`Switch to ${theme === "dark" ? "light" : "dark"}`}>
            ◐
          </button>
          <button
            className="theme-toggle icon"
            onClick={pinPanel}
            disabled={!target}
            title="Pin this panel to the right"
            aria-label="Pin this panel to the right"
          >
            <PanelRightIcon />
          </button>
        </div>
      </div>

      <div className="popup-body">
        <QuizSetup
          profile={profile}
          onChange={updateProfile}
          onGenerate={generate}
          busy={busy}
          words={words}
          ready={!!target}
        />
      </div>
    </>
  );
}

function PanelRightIcon() {
  return (
    <svg viewBox="0 0 16 16" aria-hidden="true">
      <rect x="1.25" y="2.75" width="13.5" height="10.5" rx="2.5"
            fill="none" stroke="currentColor" strokeWidth="1.4" />
      <path d="M10 3.45h2.25A2 2 0 0 1 14.05 5.45v5.1a2 2 0 0 1-2 2H10z"
            fill="currentColor" />
    </svg>
  );
}

createRoot(document.getElementById("root")!).render(<Popup />);
