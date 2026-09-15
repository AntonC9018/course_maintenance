#!/usr/bin/env node
// Static Mermaid rendering via pinned Playwright + Chromium (issue #12,
// DIAG-1/DIAG-2/DIAG-4). Reads diagram source from stdin, writes SVG to
// stdout. Exit 0 success, 2 diagram syntax failure (diagnostic on stderr),
// 1 internal/toolchain error (Python falls back deterministically).
//
// Usage: node render-mermaid.mjs <diagram_index> < diagram.mmd > out.svg
//
// Determinism (DIAG-4): the render id is always `mermaid-static-<idx>` so
// repeat builds produce identical SVGs up to the normalization in
// publishing/mermaid.py (which strips residual random ids/UUIDs/hashes).
// No Mermaid client JS is emitted to the site (DIAG-3): this script runs
// only at build time; output is a static <svg>, never a <script>.

import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const idxRaw = process.argv[2] ?? "0";
const diagramIndex = Number.parseInt(idxRaw, 10);
const renderId = `mermaid-static-${Number.isFinite(diagramIndex) ? diagramIndex : 0}`;

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf-8");
    process.stdin.on("data", (c) => (data += c));
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

async function main() {
  const code = await readStdin();
  if (!code || !code.trim()) {
    console.error("empty Mermaid diagram (no content between fences)");
    process.exit(2);
  }
  let chromium;
  try {
    const { chromium: ch } = await import("playwright");
    chromium = ch;
  } catch (e) {
    console.error(`playwright unavailable: ${e?.message ?? e}`);
    process.exit(1);
  }
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
  } catch (e) {
    console.error(`chromium launch failed: ${e?.message ?? e}`);
    process.exit(1);
  }
  try {
    const page = await browser.newPage();
    await page.setContent(
      "<!doctype html><html><head><meta charset='utf-8'></head><body></body></html>"
    );
    // Load the pinned mermaid bundle from node_modules (no CDN, DIAG-3).
    const here = path.dirname(fileURLToPath(import.meta.url));
    const require = createRequire(import.meta.url);
    let mermaidPath;
    try {
      mermaidPath = require.resolve("mermaid/dist/mermaid.min.js");
    } catch {
      // Fallback: relative to this script (renderer/ + out_dir copies).
      mermaidPath = path.join(here, "node_modules", "mermaid", "dist", "mermaid.min.js");
      try {
        readFileSync(mermaidPath);
      } catch {
        // When site build copies package.json to out_dir and runs npm ci
        // there, the bundle lives one level up from this script? The Python
        // wrapper invokes this file from renderer/, so node_modules is a
        // sibling. Try cwd as well.
        mermaidPath = path.join(process.cwd(), "node_modules", "mermaid", "dist", "mermaid.min.js");
      }
    }
    await page.addScriptTag({ path: mermaidPath });
    const result = await page.evaluate(
      async ({ id, text }) => {
        try {
          // mermaid v10 exposes window.mermaid with .initialize + .render.
          const m = window.mermaid;
          if (!m) return { ok: false, error: "mermaid bundle did not load" };
          m.initialize({ startOnLoad: false, theme: "default", securityLevel: "strict" });
          // v10: mermaid.render(id, text) -> { svg } (promise).
          // v9 fallback: mermaid.mermaidAPI.render(id, text, cb).
          if (typeof m.render === "function") {
            const out = await m.render(id, text);
            const svg = typeof out === "string" ? out : out?.svg;
            if (svg && svg.includes("<svg")) return { ok: true, svg };
            return { ok: false, error: "mermaid.render returned no SVG" };
          }
          if (m.mermaidAPI && typeof m.mermaidAPI.render === "function") {
            const svg = await new Promise((resolve, reject) => {
              try {
                m.mermaidAPI.render(id, text, (s) => resolve(s), document.body);
              } catch (e) {
                reject(e);
              }
            });
            if (svg && svg.includes("<svg")) return { ok: true, svg };
            return { ok: false, error: "mermaidAPI.render returned no SVG" };
          }
          return { ok: false, error: "unsupported mermaid API (no render)" };
        } catch (e) {
          return { ok: false, error: String(e?.message ?? e) };
        }
      },
      { id: renderId, text: code }
    );
    if (!result?.ok) {
      console.error(result?.error ?? "unknown Mermaid rendering error");
      process.exit(2);
    }
    process.stdout.write(result.svg);
    process.exit(0);
  } finally {
    try {
      await browser?.close();
    } catch {
      // ignore close errors
    }
  }
}

main().catch((e) => {
  console.error(String(e?.message ?? e));
  process.exit(1);
});
