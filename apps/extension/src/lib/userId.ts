// One stable id per Chrome profile, synced across the user's devices so their learner memory
// follows them. Not a credential — the API treats it as a namespace and validates it as one, so it
// must stay within [A-Za-z0-9_-]; crypto.randomUUID() does.

const KEY = "hyrisUserId";

export async function getUserId(): Promise<string> {
  const v = await chrome.storage.sync.get(KEY);
  if (typeof v[KEY] === "string") return v[KEY];

  const minted = crypto.randomUUID();
  await chrome.storage.sync.set({ [KEY]: minted });

  // Re-read rather than returning `minted`: the service worker can be torn down between the get and
  // the set, so two callers can mint different ids. Whoever loses that race must adopt the winner's
  // id, or their quiz history is written under an id no later request will ever send again.
  const after = await chrome.storage.sync.get(KEY);
  return typeof after[KEY] === "string" ? after[KEY] : minted;
}
