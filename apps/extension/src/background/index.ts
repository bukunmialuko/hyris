// Service worker: orchestrates popup → content script → API → side panel.

import { generateQuiz } from "../lib/api";

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "HYRIS_GENERATE_QUIZ") {
    handleGenerate(msg.profile)
      .then(sendResponse)
      .catch((err) => sendResponse({ error: String(err) }));
    return true; // async response
  }
});

async function handleGenerate(profile: unknown) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) throw new Error("No active tab");

  const page = await chrome.tabs.sendMessage(tab.id, { type: "HYRIS_EXTRACT_PAGE" });
  const quiz = await generateQuiz(page, profile);

  await chrome.storage.session.set({ currentQuiz: quiz });
  await chrome.sidePanel.open({ tabId: tab.id });
  return { ok: true };
}
