// Content script: extracts readable text from the current page on request.

interface ExtractResult {
  url: string;
  title: string;
  text: string;
  wordCount: number;
}

function extractPage(): ExtractResult {
  // V1: naive extraction. Swap for Readability.js later.
  const article = document.querySelector("article, main, [role='main']") ?? document.body;
  const clone = article.cloneNode(true) as HTMLElement;
  clone.querySelectorAll("script, style, nav, footer, aside, iframe").forEach((el) => el.remove());
  const text = (clone.textContent ?? "").replace(/\s+/g, " ").trim();
  return {
    url: location.href,
    title: document.title,
    text,
    wordCount: text.split(" ").length,
  };
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "HYRIS_EXTRACT_PAGE") {
    sendResponse(extractPage());
  }
  return true;
});
