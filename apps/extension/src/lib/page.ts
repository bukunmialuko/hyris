// Resolves the tab to quiz and how much text it holds. Shared by the popup and
// the pinned panel; the panel re-probes as you move between tabs.

import { useCallback, useEffect, useState } from "react";
import { extractFromTab } from "./extract";

// Docs sites and other SPAs often paint their content after first idle.
const PROBE_DELAYS_MS = [0, 400, 900];

export interface Target { tabId: number; windowId: number }

export function usePageProbe(): { target: Target | null; words: number | null } {
  const [target, setTarget] = useState<Target | null>(null);
  const [words, setWords] = useState<number | null>(null);

  const probe = useCallback(async () => {
    setWords(null);
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) return;
    setTarget({ tabId: tab.id, windowId: tab.windowId });

    for (const delay of PROBE_DELAYS_MS) {
      if (delay) await new Promise((r) => setTimeout(r, delay));
      try {
        const page = await extractFromTab(tab.id);
        setWords(page.wordCount);
        if (page.wordCount > 0) return;
      } catch {
        // Not injectable here (chrome://, the web store, a PDF) — keep probing.
      }
    }
    setWords((w) => w ?? 0);
  }, []);

  useEffect(() => {
    void probe();

    // Only meaningful in the panel, which outlives the tab it was opened from.
    const onActivated = () => void probe();
    const onUpdated = (_id: number, info: chrome.tabs.TabChangeInfo) => {
      if (info.status === "complete") void probe();
    };
    chrome.tabs.onActivated.addListener(onActivated);
    chrome.tabs.onUpdated.addListener(onUpdated);
    return () => {
      chrome.tabs.onActivated.removeListener(onActivated);
      chrome.tabs.onUpdated.removeListener(onUpdated);
    };
  }, [probe]);

  return { target, words };
}
