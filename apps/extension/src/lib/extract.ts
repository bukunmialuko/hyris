export interface PageContent {
  url: string;
  title: string;
  text: string;
  wordCount: number;
}

/**
 * Runs inside the page via chrome.scripting.executeScript, so it must be
 * entirely self-contained — it is serialised and re-parsed in the target
 * frame, and cannot reference anything from this module's scope.
 */
export function readPage(): PageContent {
  const STRIP = [
    "script", "style", "noscript", "nav", "header", "footer", "aside", "iframe",
    "svg", "form", "button", "select", "template",
    "[aria-hidden='true']", "[role='navigation']", "[role='banner']", "[role='contentinfo']",
  ].join(",");

  // Docs sites rarely use <article>; score every plausible container and keep
  // the richest one rather than trusting the first match.
  const CANDIDATES = [
    "main article", "article", "main", "[role='main']",
    "#content-area", "#main-content", "#content", ".prose", ".markdown", ".doc-content",
  ];

  const textOf = (el: Element): string => {
    const clone = el.cloneNode(true) as HTMLElement;
    clone.querySelectorAll(STRIP).forEach((n) => n.remove());
    return (clone.textContent ?? "").replace(/\s+/g, " ").trim();
  };

  let best = "";
  for (const sel of CANDIDATES) {
    document.querySelectorAll(sel).forEach((el) => {
      const t = textOf(el);
      if (t.length > best.length) best = t;
    });
  }
  if (best.length < 200) {
    const body = textOf(document.body);
    if (body.length > best.length) best = body;
  }

  return {
    url: location.href,
    title: document.title,
    text: best,
    wordCount: best ? best.split(/\s+/).filter(Boolean).length : 0,
  };
}

/**
 * Injected on demand instead of via a declarative content script: that only
 * runs on pages loaded *after* the extension, so anything already open —
 * including the tab you install on — silently had no script to talk to.
 */
export async function extractFromTab(tabId: number): Promise<PageContent> {
  const [injected] = await chrome.scripting.executeScript({ target: { tabId }, func: readPage });
  const result = injected?.result as PageContent | undefined;
  if (!result) throw new Error("Could not read this page");
  return result;
}
