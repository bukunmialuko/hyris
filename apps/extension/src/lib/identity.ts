// One device identity per Chrome profile, synced so a learner's history follows them across
// machines. Registered once at POST /auth/device and presented as a bearer token thereafter.
//
// This replaces the old X-User-Id header, which was a *claim*: any caller could name any learner
// and read their memory. The trust model is otherwise identical -- no sign-up, one identity per
// browser profile -- except the server signs the id, so we can only present one it minted for us.

import type { DeviceToken } from "@hyris/contracts";

const KEY = "hyrisDevice";

/** Servers running without AUTH_SECRET cannot issue identities; every caller is "anonymous". */
const NO_IDENTITIES = 503;

let inFlight: Promise<DeviceToken | null> | null = null;

// Remembered for the life of this service worker so a server with no AUTH_SECRET is asked once,
// not on every poll. Workers are torn down after ~30s idle, so if the server is later restarted
// with a secret, the next worker picks that up without the user doing anything.
let noIdentities = false;

async function readStored(): Promise<DeviceToken | null> {
  const v = await chrome.storage.sync.get(KEY);
  const d = v[KEY] as DeviceToken | undefined;
  return d && typeof d.token === "string" && typeof d.user_id === "string" ? d : null;
}

async function register(apiBase: string): Promise<DeviceToken | null> {
  let r: Response;
  try {
    r = await fetch(`${apiBase}/auth/device`, { method: "POST" });
  } catch {
    throw new Error("Couldn’t reach the quiz service. Is it running?");
  }

  // Not an error: the server simply has no identities to hand out, so we stay anonymous and every
  // caller shares one learner profile. That is what keeps a bare local dev server usable.
  if (r.status === NO_IDENTITIES) {
    noIdentities = true;
    return null;
  }
  if (!r.ok) throw new Error(`Couldn’t register this device (${r.status}).`);

  const device = (await r.json()) as DeviceToken;
  await chrome.storage.sync.set({ [KEY]: device });

  // Re-read rather than trusting what we just wrote: the service worker can be torn down between
  // the set and the next get, and two callers racing here would otherwise end up with different
  // identities. Whoever loses the race must adopt the winner's, or their history is written under
  // an id no later request will ever send again.
  return (await readStored()) ?? device;
}

/** The stored device, registering on first use. Null means this server issues no identities. */
export async function getDevice(apiBase: string): Promise<DeviceToken | null> {
  const stored = await readStored();
  if (stored) return stored;
  if (noIdentities) return null;

  // Collapse concurrent first-run callers onto one registration.
  inFlight ??= register(apiBase).finally(() => {
    inFlight = null;
  });
  return inFlight;
}

/** Drops the stored device so the next call registers afresh. */
export async function forgetDevice(): Promise<void> {
  noIdentities = false;
  await chrome.storage.sync.remove(KEY);
}

export async function authHeaders(apiBase: string): Promise<Record<string, string>> {
  const device = await getDevice(apiBase);
  return device ? { Authorization: `Bearer ${device.token}` } : {};
}
