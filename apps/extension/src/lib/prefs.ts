// The quiz profile is shared between the popup and the pinned side panel, so
// pinning shows the selections you already made rather than resetting them.

import { useEffect, useState } from "react";
import type { QuizProfile } from "./session";

const KEY = "hyrisProfile";

export const DEFAULT_PROFILE: QuizProfile = {
  persona: "Master's",
  difficulty: "Hard",
  question_count: 5,
};

export function useQuizProfile(): [QuizProfile, (patch: Partial<QuizProfile>) => void] {
  const [profile, setProfile] = useState<QuizProfile>(DEFAULT_PROFILE);

  useEffect(() => {
    chrome.storage.local.get(KEY).then((v) => {
      if (v[KEY]) setProfile({ ...DEFAULT_PROFILE, ...(v[KEY] as QuizProfile) });
    });

    const onChanged = (changes: Record<string, chrome.storage.StorageChange>, area: string) => {
      if (area !== "local" || !changes[KEY]) return;
      setProfile({ ...DEFAULT_PROFILE, ...(changes[KEY].newValue as QuizProfile) });
    };
    chrome.storage.onChanged.addListener(onChanged);
    return () => chrome.storage.onChanged.removeListener(onChanged);
  }, []);

  function update(patch: Partial<QuizProfile>) {
    const next = { ...profile, ...patch };
    setProfile(next);
    void chrome.storage.local.set({ [KEY]: next });
  }

  return [profile, update];
}
