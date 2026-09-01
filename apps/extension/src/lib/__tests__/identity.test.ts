import { beforeEach, describe, expect, it, vi } from "vitest";
import { authHeaders, forgetDevice, getDevice } from "../identity";

const BASE = "http://localhost:8000";

/** Just enough chrome.storage.sync to exercise the read/write/re-read path. */
function stubStorage() {
  const data: Record<string, unknown> = {};
  vi.stubGlobal("chrome", {
    storage: {
      sync: {
        get: async (k: string) => (k in data ? { [k]: data[k] } : {}),
        set: async (o: Record<string, unknown>) => void Object.assign(data, o),
        remove: async (k: string) => void delete data[k],
      },
    },
  });
  return data;
}

const ok = (body: unknown) =>
  ({ ok: true, status: 201, json: async () => body }) as unknown as Response;
const status = (code: number) =>
  ({ ok: false, status: code, json: async () => ({}) }) as unknown as Response;

beforeEach(async () => {
  vi.unstubAllGlobals();
  stubStorage();
  await forgetDevice();
});

describe("getDevice", () => {
  it("registers once, then reuses the stored device", async () => {
    const fetchMock = vi.fn(async () => ok({ user_id: "u1", token: "t1" }));
    vi.stubGlobal("fetch", fetchMock);

    expect(await getDevice(BASE)).toEqual({ user_id: "u1", token: "t1" });
    expect(await getDevice(BASE)).toEqual({ user_id: "u1", token: "t1" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("collapses concurrent first-run callers onto one registration", async () => {
    const fetchMock = vi.fn(async () => ok({ user_id: "u1", token: "t1" }));
    vi.stubGlobal("fetch", fetchMock);

    await Promise.all([getDevice(BASE), getDevice(BASE), getDevice(BASE)]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  // A server without AUTH_SECRET issues no identities; the caller is "anonymous" and that is fine.
  it("treats 503 as 'this server has no identities' rather than an error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => status(503)));

    expect(await getDevice(BASE)).toBeNull();
    expect(await authHeaders(BASE)).toEqual({});
  });

  // Without this, a server running without AUTH_SECRET is re-asked on every poll of a run.
  it("asks a server with no identities only once", async () => {
    const fetchMock = vi.fn(async () => status(503));
    vi.stubGlobal("fetch", fetchMock);

    expect(await getDevice(BASE)).toBeNull();
    expect(await getDevice(BASE)).toBeNull();
    expect(await getDevice(BASE)).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("surfaces other failures", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => status(500)));
    await expect(getDevice(BASE)).rejects.toThrow(/register/i);
  });

  it("reports an unreachable service rather than a raw network error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("failed to fetch"); }));
    await expect(getDevice(BASE)).rejects.toThrow(/reach the quiz service/i);
  });
});

describe("authHeaders", () => {
  it("presents the token as a bearer credential", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ok({ user_id: "u1", token: "t1" })));
    expect(await authHeaders(BASE)).toEqual({ Authorization: "Bearer t1" });
  });

  // Rotating AUTH_SECRET invalidates every token; forgetting lets the next call re-register
  // instead of leaving the extension permanently 401ing.
  it("re-registers after the stored device is forgotten", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(ok({ user_id: "u1", token: "t1" }))
      .mockResolvedValueOnce(ok({ user_id: "u2", token: "t2" }));
    vi.stubGlobal("fetch", fetchMock);

    expect(await authHeaders(BASE)).toEqual({ Authorization: "Bearer t1" });
    await forgetDevice();
    expect(await authHeaders(BASE)).toEqual({ Authorization: "Bearer t2" });
  });
});
