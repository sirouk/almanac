/**
 * Runs the safe-navigation helper from web/src/lib/api.ts against malicious
 * server-supplied hrefs.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";

const ROOT = resolve(import.meta.dirname, "..");
const source = readFileSync(resolve(ROOT, "src/lib/api.ts"), "utf-8");
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ES2022,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const { safeNavigationHref } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);

describe("safeNavigationHref", () => {
  it("keeps http and https navigation links", () => {
    assert.equal(safeNavigationHref("https://checkout.stripe.com/test"), "https://checkout.stripe.com/test");
    assert.equal(safeNavigationHref("http://127.0.0.1:8900/dashboard"), "http://127.0.0.1:8900/dashboard");
  });

  it("trims safe server URLs before rendering", () => {
    assert.equal(safeNavigationHref("  https://github.com/example/repo/settings/keys  "), "https://github.com/example/repo/settings/keys");
  });

  it("rejects non-navigation schemes and malformed hrefs", () => {
    for (const href of [
      "javascript:alert(1)",
      "data:text/html,<script>alert(1)</script>",
      "mailto:ops@example.test",
      "ftp://example.test/file",
      "//example.test/path",
      "/relative/path",
      "",
    ]) {
      assert.equal(safeNavigationHref(href), "", href);
    }
  });

  it("rejects non-string values", () => {
    assert.equal(safeNavigationHref(null), "");
    assert.equal(safeNavigationHref({ href: "https://example.test" }), "");
  });
});

console.log("PASS all ArcLink safe URL tests");
