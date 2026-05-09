#!/usr/bin/env python3
"""ArcLink live proof orchestration runner.

Composes host readiness, provider diagnostics, journey model, and evidence
ledger into a single dry-run or live proof pass. Default mode is dry-run
with no secrets required. Missing credentials are reported by env var name
only; secret values are never printed, logged, or written.

Statuses:
  blocked_missing_credentials - required env vars absent
  dry_run_ready               - all env vars present, live not requested
  live_ready_pending_execution - live requested but no runners registered
  live_executed                - live run completed (passed or failed)
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urljoin

from arclink_diagnostics import run_diagnostics
from arclink_evidence import (
    generate_run_id,
    get_commit_hash,
    ledger_from_journey,
)
from arclink_host_readiness import run_readiness
from arclink_live_journey import (
    JourneyStep,
    build_journey,
    evaluate_journey,
    journey_summary,
)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

@dataclass
class LiveProofResult:
    """Result of a live proof orchestration run."""
    status: str  # blocked_missing_credentials | dry_run_ready | live_ready_pending_execution | live_executed
    journey: str = "hosted"
    missing_env: list[str] = field(default_factory=list)
    host_readiness: dict[str, Any] = field(default_factory=dict)
    provider_diagnostics: dict[str, Any] = field(default_factory=dict)
    journey_summary: dict[str, Any] = field(default_factory=dict)
    evidence_path: str = ""
    exit_code: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


# ---------------------------------------------------------------------------
# Credential collection
# ---------------------------------------------------------------------------

def _collect_missing_env(steps: list[JourneyStep], env: Mapping[str, str]) -> list[str]:
    """Return deduplicated list of missing env var names across all steps."""
    seen: set[str] = set()
    result: list[str] = []
    any_opt_in_enabled = any(
        env.get(key, "").strip()
        for step in steps
        for key in step.required_env
        if key.startswith("ARCLINK_PROOF_")
    )
    for step in steps:
        proof_flags = [key for key in step.required_env if key.startswith("ARCLINK_PROOF_")]
        if proof_flags and any_opt_in_enabled and not any(env.get(key, "").strip() for key in proof_flags):
            continue
        for key in step.required_env:
            if key not in seen and not env.get(key, "").strip():
                seen.add(key)
                result.append(key)
    return result


# ---------------------------------------------------------------------------
# Default workspace live runners
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[1]
_BROWSER_STEP_SPECS: dict[str, dict[str, Any]] = {
    "drive_tls_desktop_proof": {"plugin": "drive", "viewport": "desktop"},
    "drive_tls_mobile_proof": {"plugin": "drive", "viewport": "mobile"},
    "code_tls_desktop_proof": {"plugin": "code", "viewport": "desktop"},
    "code_tls_mobile_proof": {"plugin": "code", "viewport": "mobile"},
    "terminal_tls_desktop_proof": {"plugin": "terminal", "viewport": "desktop"},
    "terminal_tls_mobile_proof": {"plugin": "terminal", "viewport": "mobile"},
}


def _redacted_command_label(args: list[str]) -> str:
    if args[:2] == ["./deploy.sh", "docker"] and len(args) >= 3:
        return "deploy.sh docker " + args[2]
    if args[:1] == ["npx"]:
        return "npx playwright workspace-proof"
    return Path(args[0]).name if args else "command"


def _command_timeout(env: Mapping[str, str], key: str, default: int) -> int:
    raw = str(env.get(key) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(10, min(value, 60 * 60))


def _run_redacted_command(
    args: list[str],
    *,
    env: Mapping[str, str],
    timeout: int,
    cwd: Path = _REPO_ROOT,
    parse_json_stdout: bool = False,
) -> dict[str, Any]:
    command_env = os.environ.copy()
    command_env.update({str(key): str(value) for key, value in env.items()})
    completed = subprocess.run(
        args,
        cwd=str(cwd),
        env=command_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"{_redacted_command_label(args)} failed with exit code {completed.returncode}")
    payload: dict[str, Any] = {"command": _redacted_command_label(args), "exit_code": completed.returncode}
    if parse_json_stdout:
        for line in reversed((completed.stdout or "").splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                result = parsed.get("result") if isinstance(parsed.get("result"), dict) else {}
                payload["browser"] = {
                    "plugin": str(parsed.get("plugin") or ""),
                    "viewport": str(parsed.get("viewport") or ""),
                    "checks": int(result.get("checks") or 0),
                    "roots": int(result.get("roots") or 0),
                    "repos": int(result.get("repos") or 0),
                }
                screenshot = str(parsed.get("screenshot") or "").strip()
                if screenshot:
                    payload["screenshot"] = screenshot
                break
    return payload


def _docker_upgrade_reconcile_runner(env: Mapping[str, str]) -> dict[str, Any]:
    timeout = _command_timeout(env, "ARCLINK_WORKSPACE_PROOF_DOCKER_TIMEOUT_SECONDS", 45 * 60)
    return _run_redacted_command(["./deploy.sh", "docker", "upgrade"], env=env, timeout=timeout)


def _docker_health_runner(env: Mapping[str, str]) -> dict[str, Any]:
    timeout = _command_timeout(env, "ARCLINK_WORKSPACE_PROOF_HEALTH_TIMEOUT_SECONDS", 15 * 60)
    return _run_redacted_command(["./deploy.sh", "docker", "health"], env=env, timeout=timeout)


def _workspace_proof_url(base_url: str, plugin: str) -> str:
    clean = base_url.strip()
    if not clean:
        raise RuntimeError("workspace proof URL is missing")
    if not clean.lower().startswith("https://"):
        raise RuntimeError("workspace proof URL must use HTTPS")
    return urljoin(clean.rstrip("/") + "/", plugin.lstrip("/") + "/")


def _browser_runner_script() -> str:
    return textwrap.dedent(
        r"""
        const { chromium, devices } = require("@playwright/test");
        const fs = require("fs");
        const path = require("path");

        function authHeaders() {
          const raw = (process.env.ARCLINK_WORKSPACE_PROOF_AUTH || "").trim();
          if (!raw) return {};
          const lower = raw.toLowerCase();
          if (lower.startsWith("cookie:")) {
            return { Cookie: raw.slice(7) };
          }
          if (lower.startsWith("bearer ")) {
            return { Authorization: raw };
          }
          if (lower.startsWith("bearer:")) {
            return { Authorization: "Bearer " + raw.slice(7) };
          }
          return { Authorization: "Bearer " + raw };
        }

        async function requestJSON(page, path, options = {}) {
          const response = await page.evaluate(async ({ path, options }) => {
            const init = Object.assign({ credentials: "same-origin" }, options || {});
            if (init.body && typeof init.body !== "string" && !(init.body instanceof FormData)) {
              init.headers = Object.assign({ "Content-Type": "application/json" }, init.headers || {});
              init.body = JSON.stringify(init.body);
            }
            const res = await fetch(path, init);
            const text = await res.text();
            let json = {};
            try { json = text ? JSON.parse(text) : {}; } catch (_) { json = { raw: text.slice(0, 120) }; }
            return { ok: res.ok, status: res.status, json };
          }, { path, options });
          if (!response.ok) throw new Error(path + " returned HTTP " + response.status);
          return response.json;
        }

        async function openPluginPage(page, title, readyText) {
          await page.goto(process.env.ARCLINK_WORKSPACE_PROOF_URL, { waitUntil: "domcontentloaded" });
          await page.getByText(title).first().waitFor({ timeout: 15000 });
          const plugin = process.env.ARCLINK_WORKSPACE_PROOF_PLUGIN || "";
          if (plugin) {
            const pluginLink = page.locator("a[href$='/" + plugin + "']").first();
            await pluginLink.click({ timeout: 5000, force: true }).catch(async () => {
              await page.evaluate((targetPlugin) => {
                const links = Array.from(document.querySelectorAll("a"));
                const link = links.find((item) => String(item.href || "").replace(/\/$/, "").endsWith("/" + targetPlugin));
                if (link) link.click();
              }, plugin);
            });
            await page.waitForURL(new RegExp("/" + plugin + "$"), { timeout: 10000 }).catch(() => {});
          }
          await page.getByText(readyText || title).last().waitFor({ timeout: 15000 });
        }

        async function captureSanitizedScreenshot(page, plugin, viewport) {
          const screenshotDir = (process.env.ARCLINK_WORKSPACE_PROOF_SCREENSHOT_DIR || "").trim();
          if (!screenshotDir) return "";
          fs.mkdirSync(screenshotDir, { recursive: true });
          await page.addStyleTag({
            content: `
              .hermes-drive-file-name,
              .hermes-drive-name,
              .hermes-drive-file-facts,
              .hermes-drive-meta,
              .hermes-drive-path,
              .hermes-drive-preview,
              .hermes-drive-text-preview,
              .hermes-drive-preview-fullscreen,
              .hermes-code-item-name,
              .hermes-code-item-lang,
              .hermes-code-path,
              .hermes-code-textarea,
              .hermes-code-preview,
              .hermes-code-preview-fullscreen,
              .hermes-code-diff,
              .hermes-code-search-results,
              .hermes-code-change-name,
              .hermes-code-source-head,
              .hermes-code-last-git-result,
              .hermes-terminal-screen,
              .hermes-terminal-facts,
              .hermes-terminal-group-label,
              .hermes-terminal-session strong,
              .hermes-terminal-session span,
              input,
              textarea,
              pre {
                color: transparent !important;
                text-shadow: none !important;
                caret-color: transparent !important;
              }
              .hermes-drive-preview *,
              .hermes-drive-preview-fullscreen *,
              .hermes-code-preview *,
              .hermes-code-preview-fullscreen *,
              .hermes-code-textarea *,
              .hermes-code-diff *,
              .hermes-terminal-screen * {
                color: transparent !important;
                text-shadow: none !important;
              }
            `,
          }).catch(() => {});
          const filename = [plugin, viewport, Date.now()].join("-") + ".png";
          const screenshotPath = path.join(screenshotDir, filename);
          await page.screenshot({ path: screenshotPath, fullPage: false, animations: "disabled" });
          return screenshotPath;
        }

        async function uploadDriveFile(page, root, name, content) {
          const response = await page.evaluate(async ({ root, name, content }) => {
            const form = new FormData();
            form.append("path", "/");
            form.append("root", root);
            form.append("conflict", "keep-both");
            form.append("files", new File([content], name, { type: "text/plain" }));
            const res = await fetch("/api/plugins/drive/upload", {
              method: "POST",
              credentials: "same-origin",
              body: form,
            });
            const text = await res.text();
            return { ok: res.ok, status: res.status, json: text ? JSON.parse(text) : {} };
          }, { root, name, content });
          if (!response.ok) throw new Error("drive upload returned HTTP " + response.status);
          return response.json;
        }

        async function driveProof(page) {
          await openPluginPage(page, "Drive", "New Folder");
          const status = await requestJSON(page, "/api/plugins/drive/status");
          if (!status.available) throw new Error("Drive plugin unavailable");
          const roots = (status.roots || []).filter((root) => root.available);
          if (!roots.length) throw new Error("Drive has no available roots");
          const root = (roots.find((item) => item.id === "vault") || roots[0]).id;
          const slug = "arclink-proof-" + Date.now();
          const upload = await uploadDriveFile(page, root, slug + ".txt", "workspace proof");
          const path = upload.uploaded[0].path;
          const renamed = "/" + slug + "-renamed.txt";
          const moved = "/" + slug + "-folder/" + slug + "-renamed.txt";
          await requestJSON(page, "/api/plugins/drive/rename", { method: "POST", body: { root, path, name: slug + "-renamed.txt" } });
          await requestJSON(page, "/api/plugins/drive/mkdir", { method: "POST", body: { root, path: "/" + slug + "-folder" } });
          await requestJSON(page, "/api/plugins/drive/duplicate", { method: "POST", body: { root, path: renamed } });
          await requestJSON(page, "/api/plugins/drive/move", { method: "POST", body: { root, source_path: renamed, destination_path: moved } });
          await requestJSON(page, "/api/plugins/drive/delete", { method: "POST", body: { root, path: moved } });
          const trash = await requestJSON(page, "/api/plugins/drive/trash?root=" + encodeURIComponent(root));
          const record = (trash.items || []).find((item) => item.original_path === moved);
          if (!record) throw new Error("Drive trash record missing");
          await requestJSON(page, "/api/plugins/drive/restore", { method: "POST", body: { root, path: record.trash_path } });
          if (roots.length > 1) {
            await page.getByRole("button", { name: roots[1].label }).first().click();
          }
          return { checks: 8, roots: roots.length };
        }

        async function codeProof(page) {
          await openPluginPage(page, "Code", "Explorer");
          const status = await requestJSON(page, "/api/plugins/code/status");
          if (!status.available) throw new Error("Code plugin unavailable");
          const slug = "arclink-proof-" + Date.now() + ".md";
          const repos = await requestJSON(page, "/api/plugins/code/repos");
          const repo = repos.repos && repos.repos.length ? repos.repos[0] : null;
          const repoPath = repo ? repo.path : "";
          const workspacePath = repo ? ((repoPath === "/" ? "" : repoPath.replace(/\/$/, "")) + "/" + slug) : ("/" + slug);
          const saved = await requestJSON(page, "/api/plugins/code/save", {
            method: "POST",
            body: { path: workspacePath, content: "# Workspace proof\n" },
          });
          await requestJSON(page, "/api/plugins/code/file?path=" + encodeURIComponent(saved.path));
          const updated = await requestJSON(page, "/api/plugins/code/save", {
            method: "POST",
            body: { path: saved.path, expected_hash: saved.hash, content: "# Workspace proof\n\nedited\n" },
          });
          await requestJSON(page, "/api/plugins/code/search?q=" + encodeURIComponent("Workspace proof") + "&path=%2F");
          if (repo) {
            await requestJSON(page, "/api/plugins/code/git/status?repo=" + encodeURIComponent(repoPath));
            await requestJSON(page, "/api/plugins/code/git/diff?repo=" + encodeURIComponent(repoPath) + "&path=" + encodeURIComponent(slug) + "&untracked=true");
            await requestJSON(page, "/api/plugins/code/git/stage", { method: "POST", body: { repo: repoPath, path: slug } });
            await requestJSON(page, "/api/plugins/code/git/unstage", { method: "POST", body: { repo: repoPath, path: slug } });
          }
          await requestJSON(page, "/api/plugins/code/ops/trash", { method: "POST", body: { path: updated.path, confirm: true } });
          await page.getByRole("button", { name: "Light" }).first().click().catch(() => {});
          return { checks: repo ? 8 : 6, repos: (repos.repos || []).length };
        }

        async function terminalProof(page) {
          await openPluginPage(page, "Terminal", "Sessions");
          const status = await requestJSON(page, "/api/plugins/terminal/status");
          if (!status.available) throw new Error("Terminal plugin unavailable");
          const created = await requestJSON(page, "/api/plugins/terminal/sessions", {
            method: "POST",
            body: { name: "Proof Terminal", cwd: "/" },
          });
          const session = created.session;
          await requestJSON(page, "/api/plugins/terminal/sessions/" + encodeURIComponent(session.id) + "/input", {
            method: "POST",
            body: { input: "printf 'workspace-proof-ok\\n'\n" },
          });
          await page.reload({ waitUntil: "domcontentloaded" });
          await openPluginPage(page, "Terminal", "Sessions");
          const revisited = await requestJSON(page, "/api/plugins/terminal/sessions/" + encodeURIComponent(session.id));
          if (!String(revisited.session.scrollback || "").includes("workspace-proof-ok")) {
            throw new Error("Terminal proof output missing after reload");
          }
          await requestJSON(page, "/api/plugins/terminal/sessions/" + encodeURIComponent(session.id) + "/rename", {
            method: "POST",
            body: { name: "Proof Terminal Renamed", folder: "Proof" },
          });
          await requestJSON(page, "/api/plugins/terminal/sessions/" + encodeURIComponent(session.id) + "/close", {
            method: "POST",
            body: { confirm: true },
          });
          return { checks: 6 };
        }

        async function main() {
          const plugin = process.env.ARCLINK_WORKSPACE_PROOF_PLUGIN;
          const viewport = process.env.ARCLINK_WORKSPACE_PROOF_VIEWPORT;
          const device = viewport === "mobile" ? devices["iPhone 13"] : { viewport: { width: 1440, height: 1000 } };
          const browser = await chromium.launch({ headless: true });
          const context = await browser.newContext(Object.assign({}, device, { extraHTTPHeaders: authHeaders(), ignoreHTTPSErrors: false }));
          const page = await context.newPage();
          let result;
          if (plugin === "drive") result = await driveProof(page);
          else if (plugin === "code") result = await codeProof(page);
          else if (plugin === "terminal") result = await terminalProof(page);
          else throw new Error("unknown plugin proof: " + plugin);
          const screenshot = await captureSanitizedScreenshot(page, plugin, viewport);
          await browser.close();
          console.log(JSON.stringify({ plugin, viewport, result, screenshot }));
        }

        main().catch((error) => {
          console.error(error && error.message ? error.message : String(error));
          process.exit(1);
        });
        """
    ).strip()


def _browser_proof_runner(step_name: str, env: Mapping[str, str]) -> dict[str, Any]:
    spec = _BROWSER_STEP_SPECS[step_name]
    plugin = str(spec["plugin"])
    viewport = str(spec["viewport"])
    timeout = _command_timeout(env, "ARCLINK_WORKSPACE_PROOF_BROWSER_TIMEOUT_SECONDS", 5 * 60)
    proof_env = dict(env)
    proof_env["ARCLINK_WORKSPACE_PROOF_PLUGIN"] = plugin
    proof_env["ARCLINK_WORKSPACE_PROOF_VIEWPORT"] = viewport
    proof_env["ARCLINK_WORKSPACE_PROOF_URL"] = _workspace_proof_url(str(env.get("ARCLINK_WORKSPACE_PROOF_TLS_URL") or ""), plugin)
    proof_env.setdefault("ARCLINK_WORKSPACE_PROOF_SCREENSHOT_DIR", "../evidence/workspace-screenshots")
    with tempfile.TemporaryDirectory(prefix=".arclink-workspace-proof-", dir=str(_REPO_ROOT / "web")) as tmp:
        script = Path(tmp) / "workspace-proof.cjs"
        script.write_text(_browser_runner_script(), encoding="utf-8")
        result = _run_redacted_command(
            ["node", str(script)],
            env=proof_env,
            timeout=timeout,
            cwd=_REPO_ROOT / "web",
            parse_json_stdout=True,
        )
    result.update({"plugin": plugin, "viewport": viewport, "tls": True})
    return result


def build_workspace_live_runners(env: Mapping[str, str]) -> dict[str, Any]:
    """Build real no-secret workspace live runners for Docker and TLS proof."""
    runners: dict[str, Any] = {
        "workspace_docker_upgrade_reconcile": lambda _step: _docker_upgrade_reconcile_runner(env),
        "workspace_docker_health": lambda _step: _docker_health_runner(env),
    }
    for step_name in _BROWSER_STEP_SPECS:
        runners[step_name] = lambda _step, name=step_name: _browser_proof_runner(name, env)
    return runners


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_live_proof(
    *,
    env: Mapping[str, str] | None = None,
    runners: dict[str, Any] | None = None,
    live: bool = False,
    artifact_dir: str | None = None,
    skip_ports: bool = True,
    docker_binary: str = "docker",
    compose_runner: Any | None = None,
    journey: str = "hosted",
) -> LiveProofResult:
    """Execute live proof orchestration.

    Args:
        env: Environment mapping (defaults to os.environ).
        runners: Step runners keyed by step name for live execution.
        live: If True and ARCLINK_E2E_LIVE is set, attempt live execution.
        artifact_dir: Directory to write evidence JSON. Defaults to ./evidence/.
        skip_ports: Skip port bind checks (default True for CI).
        docker_binary: Docker binary for readiness checks.
        compose_runner: Injected compose runner for readiness checks.
        journey: Proof journey to evaluate: hosted, external, workspace, or all.
    """
    source = dict(env) if env is not None else dict(os.environ)

    # Phase 1: Host readiness
    readiness = run_readiness(
        env=source,
        skip_ports=skip_ports,
        docker_binary=docker_binary,
        compose_runner=compose_runner,
    )

    # Phase 2: Provider diagnostics
    diagnostics = run_diagnostics(env=source, docker_binary=docker_binary)

    # Phase 3: Journey planning
    steps = build_journey(journey)
    all_missing = _collect_missing_env(steps, source)
    effective_runners = runners
    if effective_runners is None and journey == "workspace":
        effective_runners = build_workspace_live_runners(source)

    # Determine status
    live_requested = live and bool(source.get("ARCLINK_E2E_LIVE", "").strip())

    if all_missing:
        status = "blocked_missing_credentials"
    elif not live_requested:
        status = "dry_run_ready"
    elif not effective_runners:
        status = "live_ready_pending_execution"
    else:
        status = "live_executed"

    # Phase 4: Evaluate journey (runs step runners if live_executed)
    if status == "live_executed":
        # evaluate_journey checks os.environ for credentials, so patch it
        old_env = os.environ.copy()
        os.environ.update(source)
        try:
            evaluate_journey(steps, runners=effective_runners, stop_on_failure=True)
        finally:
            os.environ.clear()
            os.environ.update(old_env)
    elif status == "blocked_missing_credentials":
        # Mark steps with their skip reasons
        for step in steps:
            m = [k for k in step.required_env if not source.get(k, "").strip()]
            if m:
                step.status = "skipped"
                step.skip_reason = f"missing env: {', '.join(m)}"

    # Phase 5: Build evidence ledger
    commit = get_commit_hash()
    run_id = generate_run_id(commit=commit)
    ledger = ledger_from_journey(steps, run_id=run_id, commit_hash=commit)

    # Phase 6: Write artifact
    evidence_path = ""
    if artifact_dir is not None or status in ("dry_run_ready", "live_executed"):
        out_dir = Path(artifact_dir or "evidence")
        out_dir.mkdir(parents=True, exist_ok=True)
        artifact_file = out_dir / f"{run_id}.json"
        artifact_file.write_text(ledger.to_json())
        evidence_path = str(artifact_file)

    # Determine exit code
    if status == "live_executed":
        exit_code = 0 if ledger.all_passed else 1
    elif status in ("dry_run_ready", "blocked_missing_credentials", "live_ready_pending_execution"):
        exit_code = 0
    else:
        exit_code = 1

    return LiveProofResult(
        status=status,
        journey=journey,
        missing_env=all_missing,
        host_readiness=readiness.to_dict(),
        provider_diagnostics=diagnostics.to_dict(),
        journey_summary=journey_summary(steps),
        evidence_path=evidence_path,
        exit_code=exit_code,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="ArcLink live proof orchestration. Dry-run by default.",
    )
    parser.add_argument(
        "--live", action="store_true",
        help="Attempt live execution (requires ARCLINK_E2E_LIVE=1 and credentials)",
    )
    parser.add_argument(
        "--artifact-dir", default=None,
        help="Directory for evidence JSON output (default: evidence/)",
    )
    parser.add_argument(
        "--docker-binary", default="docker",
        help="Docker binary name or path",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output full result as JSON",
    )
    parser.add_argument(
        "--journey",
        choices=("hosted", "external", "workspace", "all"),
        default="hosted",
        help="Proof journey to plan or execute (default: hosted)",
    )
    args = parser.parse_args(argv)

    result = run_live_proof(
        live=args.live,
        artifact_dir=args.artifact_dir,
        docker_binary=args.docker_binary,
        journey=args.journey,
    )

    if args.json_output:
        print(result.to_json())
    else:
        print(f"Status: {result.status}")
        print(f"Journey: {result.journey}")
        if result.missing_env:
            print(f"Missing: {', '.join(result.missing_env)}")
        if result.evidence_path:
            print(f"Evidence: {result.evidence_path}")
        summary = result.journey_summary.get("by_status", {})
        if summary:
            parts = [f"{k}={v}" for k, v in sorted(summary.items())]
            print(f"Journey: {', '.join(parts)}")

    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
