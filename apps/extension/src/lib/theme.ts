// Theme is shared between the popup and the side panel via chrome.storage.local,
// so toggling in one surface updates the other live.

import { useEffect, useState } from "react";

export type Theme = "light" | "dark";

const KEY = "hyrisTheme";

function apply(theme: Theme) {
  document.documentElement.dataset.theme = theme;
}

export function useTheme(): [Theme, () => void] {
  const [theme, setThemeState] = useState<Theme>("light");

  useEffect(() => {
    chrome.storage.local.get(KEY).then((v) => {
      const stored = v[KEY] as Theme | undefined;
      if (stored) { setThemeState(stored); apply(stored); }
    });

    const onChanged = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      if (area !== "local" || !changes[KEY]) return;
      const next = changes[KEY].newValue as Theme;
      setThemeState(next);
      apply(next);
    };
    chrome.storage.onChanged.addListener(onChanged);
    return () => chrome.storage.onChanged.removeListener(onChanged);
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setThemeState(next);
    apply(next);
    void chrome.storage.local.set({ [KEY]: next });
  }

  return [theme, toggle];
}
