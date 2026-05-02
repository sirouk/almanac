#!/usr/bin/env python3
from __future__ import annotations

import http.server
import json
import os
import shutil
import socketserver
import subprocess
import tempfile
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE_SCRIPT = REPO / "skills" / "arclink-first-contact" / "scripts" / "run-first-contact.sh"


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write_fake_rpc(path: Path) -> None:
    path.write_text(
        "#!/usr/bin/env python3\n"
        "from __future__ import annotations\n"
        "import argparse, json\n"
        "parser = argparse.ArgumentParser()\n"
        "parser.add_argument('--url', required=True)\n"
        "parser.add_argument('--tool', required=True)\n"
        "parser.add_argument('--json-args', default='{}')\n"
        "args = parser.parse_args()\n"
        "if args.tool == 'catalog.vaults':\n"
        "    print(json.dumps({'vaults': [{'vault_name': 'Projects', 'subscribed': True, 'default_subscribed': True}]}))\n"
        "elif args.tool == 'vaults.refresh':\n"
        "    print(json.dumps({'active_subscriptions': ['Projects']}))\n"
        "elif args.tool == 'agents.managed-memory':\n"
        "    print(json.dumps({'agent_id': 'agent-test', 'qmd-ref': 'ok', 'vault_path_contract': 'user-home-arclink-v1'}))\n"
        "elif args.tool == 'status':\n"
        "    print(json.dumps({'vault_warning_count': 0, 'vault_warnings': []}))\n"
        "elif args.tool == 'notion.search':\n"
        "    print(json.dumps({'ok': True, 'results': [], 'collection': 'notion-shared'}))\n"
        "else:\n"
        "    raise SystemExit(f'unsupported tool: {args.tool}')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def write_fake_arclink_control(path: Path) -> None:
    path.write_text(
        "from __future__ import annotations\n"
        "import json\n"
        "from pathlib import Path\n"
        "\n"
        "def write_managed_memory_stubs(*, hermes_home, payload):\n"
        "    state_dir = Path(hermes_home) / 'state'\n"
        "    state_dir.mkdir(parents=True, exist_ok=True)\n"
        "    (state_dir / 'arclink-vault-reconciler.json').write_text(json.dumps(payload, indent=2, sort_keys=True) + '\\n', encoding='utf-8')\n"
        ,
        encoding="utf-8",
    )


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def make_qmd_handler(calls: list[dict[str, object]]):
    expected_session = "test-session-123"

    class QmdHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw or "{}")
            calls.append(payload)
            method = payload.get("method")
            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "serverInfo": {"name": "qmd", "version": "2.1.0"},
                    },
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("mcp-session-id", expected_session)
                self.end_headers()
                self.wfile.write(json.dumps(response).encode("utf-8"))
                return
            if self.headers.get("mcp-session-id") != expected_session:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": {"message": "missing or wrong mcp-session-id"}}).encode("utf-8"))
                return
            if method == "notifications/initialized":
                self.send_response(200)
                self.end_headers()
                return
            if method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "result": {
                        "tools": [
                            {"name": "query"},
                            {"name": "get"},
                            {"name": "multi_get"},
                            {"name": "status"},
                        ]
                    },
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response).encode("utf-8"))
                return
            if method == "tools/call" and isinstance(payload.get("params"), dict) and payload["params"].get("name") == "query":
                response = {
                    "jsonrpc": "2.0",
                    "id": payload.get("id"),
                    "result": {
                        "content": [{"type": "text", "text": "No results found"}],
                        "structuredContent": {"results": []},
                    },
                }
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response).encode("utf-8"))
                return
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": {"message": f"unexpected method: {method}"}}).encode("utf-8"))

        def log_message(self, format: str, *args: object) -> None:  # noqa: A003
            return

    return QmdHandler


def test_first_contact_runs_real_qmd_probe() -> None:
    calls: list[dict[str, object]] = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_qmd_handler(calls))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo_dir = root / "shared-repo"
            bin_dir = repo_dir / "bin"
            python_dir = repo_dir / "python"
            script_path = repo_dir / "skills" / "arclink-first-contact" / "scripts" / "run-first-contact.sh"
            hermes_home = root / "hermes-home"
            agents_state_dir = root / "agents-state" / "agent-test"

            script_path.parent.mkdir(parents=True, exist_ok=True)
            bin_dir.mkdir(parents=True, exist_ok=True)
            python_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE_SCRIPT, script_path)
            script_path.chmod(0o755)
            write_fake_rpc(bin_dir / "arclink-rpc")
            write_fake_arclink_control(python_dir / "arclink_control.py")

            token_file = hermes_home / "secrets" / "arclink-bootstrap-token"
            token_file.parent.mkdir(parents=True, exist_ok=True)
            token_file.write_text("tok_test\n", encoding="utf-8")

            enrollment_state = hermes_home / "state" / "arclink-enrollment.json"
            enrollment_state.parent.mkdir(parents=True, exist_ok=True)
            enrollment_state.write_text(json.dumps({"agent_id": "agent-test"}) + "\n", encoding="utf-8")

            agents_state_dir.mkdir(parents=True, exist_ok=True)
            (agents_state_dir / "managed-memory.json").write_text(
                json.dumps(
                    {
                        "agent_id": "agent-test",
                        "arclink-skill-ref": "Use arclink-qmd-mcp for retrieval.",
                        "vault-ref": "Vault root: /srv/arclink/vault",
                        "resource-ref": "Canonical user access rails.",
                        "qmd-ref": "qmd MCP (deep retrieval): http://127.0.0.1:8181/mcp",
                        "notion-ref": "Shared Notion knowledge rail: notion.search / notion.fetch / notion.query.",
                        "vault_path_contract": "user-home-arclink-v1",
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            qmd_url = f"http://127.0.0.1:{server.server_port}/mcp"
            result = subprocess.run(
                [str(script_path)],
                env={
                    **os.environ,
                    "HERMES_HOME": str(hermes_home),
                    "HOME": str(root / "home-test"),
                    "ARCLINK_MCP_URL": "http://127.0.0.1:8282/mcp",
                    "ARCLINK_QMD_URL": qmd_url,
                    "ARCLINK_BOOTSTRAP_TOKEN_FILE": str(token_file),
                    "ARCLINK_SHARED_REPO_DIR": str(repo_dir),
                    "ARCLINK_AGENTS_STATE_DIR": str(root / "agents-state"),
                    "ARCLINK_NOTION_INDEX_ROOTS": "https://www.notion.so/Root-aaaaaaaaaaaabbbbbbbbbbbbbbbb",
                },
                text=True,
                capture_output=True,
                check=False,
            )
            expect(result.returncode == 0, f"expected first-contact to succeed, rc={result.returncode} stderr={result.stderr!r}")

            summary = json.loads(result.stdout)
            expect(summary["ok"] is True, summary)
            expect(summary["qmd_probe"]["ok"] is True, summary)
            expect(summary["qmd_probe"]["server_name"] == "qmd", summary)
            expect(summary["qmd_probe"]["server_version"] == "2.1.0", summary)
            expect(summary["qmd_probe"]["session_header_required"] is True, summary)
            expect("query" in summary["qmd_probe"]["tool_names"], summary)
            expect(summary["qmd_probe"]["probe_tool"] == "query", summary)
            expect(summary["qmd_probe"]["probe_collections"] == ["vault"], summary)
            expect(summary["notion_probe"]["ok"] is True, summary)
            expect(summary["notion_probe"]["collection"] == "notion-shared", summary)
            expect(summary["managed_memory"]["state_written"] is True, summary)
            expect(summary["managed_memory"]["legacy_stub_present"] is False, summary)

            methods = [str(call.get("method")) for call in calls]
            expect(methods == ["initialize", "notifications/initialized", "tools/list", "tools/call"], methods)
            final_call = calls[-1]
            expect(final_call["params"]["name"] == "query", final_call)  # type: ignore[index]
            expect(final_call["params"]["arguments"]["collections"] == ["vault"], final_call)  # type: ignore[index]
            expect(final_call["params"]["arguments"]["searches"][0]["type"] == "lex", final_call)  # type: ignore[index]
            print("PASS test_first_contact_runs_real_qmd_probe")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main() -> int:
    test_first_contact_runs_real_qmd_probe()
    print("PASS all 1 first-contact regression tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
