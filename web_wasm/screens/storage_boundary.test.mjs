import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function listScreenFiles() {
  return fs.readdirSync(__dirname)
    .filter((name) => name.endsWith(".js") && !name.endsWith(".test.mjs"));
}

test("screen modules do not directly access browser storage APIs", () => {
  const screenFiles = listScreenFiles();
  const violations = [];

  screenFiles.forEach((fileName) => {
    const fullPath = path.join(__dirname, fileName);
    const source = fs.readFileSync(fullPath, "utf-8");
    if (/\blocalStorage\b|\bindexedDB\b/.test(source)) {
      violations.push(fileName);
    }
  });

  assert.deepEqual(
    violations,
    [],
    `screen modules must not directly touch browser storage APIs: ${violations.join(", ")}`,
  );
});

test("screen modules only use loadSlot for explicit user-driven restore", () => {
  const screenFiles = listScreenFiles();
  const violations = [];

  screenFiles.forEach((fileName) => {
    const fullPath = path.join(__dirname, fileName);
    const source = fs.readFileSync(fullPath, "utf-8");
    if (/saveRepository\.(load|loadLocalMirror)\s*\(/.test(source)) {
      violations.push(fileName);
    }
  });

  assert.deepEqual(
    violations,
    [],
    `screen modules must not call saveRepository.load()/loadLocalMirror(): ${violations.join(", ")}`,
  );
});
