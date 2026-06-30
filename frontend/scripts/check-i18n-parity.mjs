#!/usr/bin/env node
/**
 * Build-time i18n key-parity gate (ISSUE-196).
 *
 * Fails the build (non-zero exit) when any locale is *short of* `en` — i.e. a
 * user switching to ar/hi/ur would hit an English fallback (or a bare key) for
 * some string. English is the source of truth: every key defined in `en` must
 * exist in every other locale.
 *
 * This parses `src/lib/i18n.ts` as text (no bundler / TS loader needed) so it can
 * run as the first step of `pnpm build`. The translations object is formatted one
 * key per line at a fixed indent, which makes a line-based scan reliable; the
 * script also guards against duplicate keys within a locale.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(__dirname, '../src/lib/i18n.ts');

const lines = fs.readFileSync(SRC, 'utf8').split('\n');

/** Detect each `<lang>: {` … `},` block and collect its top-level keys. */
const blocks = {};
let current = null;
let startLine = 0;
for (let i = 0; i < lines.length; i++) {
  const open = lines[i].match(/^  (en|ar|hi|ur): \{$/);
  if (open) {
    current = open[1];
    startLine = i + 1;
    continue;
  }
  if (current && /^  \},?$/.test(lines[i])) {
    blocks[current] = [startLine, i - 1];
    current = null;
  }
}

const LOCALES = ['en', 'ar', 'hi', 'ur'];
const missingBlocks = LOCALES.filter((l) => !blocks[l]);
if (missingBlocks.length) {
  console.error(`✗ i18n parity: could not locate locale block(s): ${missingBlocks.join(', ')}`);
  console.error('  The translations object in src/lib/i18n.ts is not in the expected shape.');
  process.exit(1);
}

const duplicates = [];
const keys = {};
for (const lang of LOCALES) {
  const [a, b] = blocks[lang];
  const set = new Set();
  for (let i = a; i <= b; i++) {
    const trimmed = lines[i].trim();
    if (trimmed.startsWith('//')) continue;
    const m = lines[i].match(/^    ([a-zA-Z_][a-zA-Z0-9_]*):/);
    if (!m) continue;
    if (set.has(m[1])) duplicates.push(`${lang}.${m[1]}`);
    set.add(m[1]);
  }
  keys[lang] = set;
}

const enKeys = [...keys.en];
let failed = false;

if (duplicates.length) {
  failed = true;
  console.error(`✗ i18n parity: ${duplicates.length} duplicate key(s):`);
  console.error('  ' + duplicates.join(', '));
}

for (const lang of LOCALES.filter((l) => l !== 'en')) {
  const missing = enKeys.filter((k) => !keys[lang].has(k));
  const extra = [...keys[lang]].filter((k) => !keys.en.has(k));
  if (missing.length) {
    failed = true;
    console.error(`✗ i18n parity: '${lang}' is short of 'en' by ${missing.length} key(s):`);
    console.error('  ' + missing.join(', '));
  }
  if (extra.length) {
    // Not "short of en", but means `en` lacks a key the locale defines — drift
    // that should be reconciled. Treated as a failure to keep all locales aligned.
    failed = true;
    console.error(`✗ i18n parity: '${lang}' has ${extra.length} key(s) absent from 'en':`);
    console.error('  ' + extra.join(', '));
  }
}

if (failed) {
  console.error('\ni18n key-parity gate failed. Add the missing keys before building.');
  process.exit(1);
}

console.log(`✓ i18n parity: all ${LOCALES.length} locales aligned on ${enKeys.length} keys.`);
