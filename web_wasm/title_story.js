const TITLE_STORY_URL = new URL("../assets/data/merged_fixed.json", import.meta.url).href;
const DEFAULT_TITLE_STORY_INDICES = [1, 2];

let titleStoryLinesPromise = null;

export function normalizeTitleStoryContent(rawContent) {
  return String(rawContent || "")
    .replace(/^>-\s*/, "")
    .replace(/\\r\\n|\\n|\\r/g, "\n")
    .replace(/\\t/g, "")
    .replace(/\[0x[0-9a-fA-F]+\]/g, "")
    .split("\n")
    .map((line) => line.replace(/^\t+/, "").trimEnd())
    .filter((line) => line.trim().length > 0);
}

export function buildTitleStoryLinesFromRows(rows, indices = DEFAULT_TITLE_STORY_INDICES) {
  if (!Array.isArray(rows)) return [];
  return indices.flatMap((index) => {
    const hit = rows.find((row) => Number(row?.index) === Number(index));
    return normalizeTitleStoryContent(hit?.content || "");
  });
}

export async function loadTitleStoryLines(indices = DEFAULT_TITLE_STORY_INDICES) {
  if (!titleStoryLinesPromise) {
    titleStoryLinesPromise = fetch(TITLE_STORY_URL, { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error(`title story fetch failed: ${response.status}`);
        return response.json();
      })
      .then((rows) => buildTitleStoryLinesFromRows(rows, indices))
      .catch((error) => {
        titleStoryLinesPromise = null;
        throw error;
      });
  }
  return titleStoryLinesPromise;
}
