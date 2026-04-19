import test from "node:test";
import assert from "node:assert/strict";

import {
  buildTitleStoryLinesFromRows,
  normalizeTitleStoryContent,
} from "./title_story.js";

test("normalizeTitleStoryContent turns merged_fixed content into clean display lines", () => {
  const lines = normalizeTitleStoryContent(
    ">-\n    \\n　　そのグルガンぞくのおとこは　しずかにかたった……\\n\t[0x05]くらべれば　ちっぽけなものである。\\n\t[0x03]だが　きぼうはまだ　うしなわれてはいない。\\n",
  );

  assert.deepEqual(lines, [
    "　　そのグルガンぞくのおとこは　しずかにかたった……",
    "くらべれば　ちっぽけなものである。",
    "だが　きぼうはまだ　うしなわれてはいない。",
  ]);
});

test("buildTitleStoryLinesFromRows concatenates index 1 and 2 story lines in order", () => {
  const lines = buildTitleStoryLinesFromRows([
    { index: 2, content: ">-\n    \\n\\t[0x04]つづきの行A\\nつづきの行B\\n" },
    { index: 1, content: ">-\n    \\n最初の行A\\n最初の行B\\n" },
  ]);

  assert.deepEqual(lines, [
    "最初の行A",
    "最初の行B",
    "つづきの行A",
    "つづきの行B",
  ]);
});
