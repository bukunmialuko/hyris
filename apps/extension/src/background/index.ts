// Service worker: orchestrates popup → page extraction → API → side panel.
//
// The popup opens the side panel itself (sidePanel.open needs a live user
// gesture, which is gone by the time this fetch resolves). Here we only publish
// generation state to session storage; the panel renders whatever it sees.

import { ConfigError, generateQuiz } from "../lib/api";
import { extractFromTab } from "../lib/extract";
import { QUIZ_KEY, STATUS_KEY, type QuizProfile, type QuizStatus } from "../lib/session";

/** Thrown when the page itself can't be read — retrying is worth offering. */
class PageError extends Error {}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "HYRIS_GENERATE_QUIZ") {
    // Ack immediately so the popup can close; generation continues here.
    // The side panel sends this same message to retry a failed run.
    void runGeneration(msg.profile as QuizProfile, msg.tabId as number);
    sendResponse({ ok: true });
  }
  return false;
});

async function setStatus(status: QuizStatus) {
  await chrome.storage.session.set({ [STATUS_KEY]: status });
}

async function runGeneration(profile: QuizProfile, tabId: number) {
  const runId = Date.now();
  await chrome.storage.session.remove(QUIZ_KEY);
  await setStatus({ state: "loading", runId, profile, tabId });

  try {
    const page = await extractFromTab(tabId).catch(() => {
      throw new PageError("Can’t read this page. Try a normal web page, or reload this one.");
    });
    const { quiz, source } = await generateQuiz(page, profile);
    if (!quiz?.quiz?.questions?.length) throw new Error("The quiz came back empty.");

    await chrome.storage.session.set({ [QUIZ_KEY]: quiz });
    await setStatus({ state: "ready", runId, profile, tabId, source });
  } catch (err) {
    // A misconfigured source can't be fixed by pressing a button, so don't
    // offer one; everything else is worth another go.
    await setStatus({
      state: "error",
      runId,
      profile,
      tabId,
      message: err instanceof Error ? err.message : String(err),
      retriable: !(err instanceof ConfigError),
    });
  }
}
