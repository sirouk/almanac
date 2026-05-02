#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <hermes-bin> <hermes-home> [gateway-setup-args...]" >&2
  exit 2
fi

HERMES_BIN="$1"
HERMES_HOME_DIR="$2"
shift 2

if [[ ! -x "$HERMES_BIN" ]]; then
  echo "Hermes binary is not executable: $HERMES_BIN" >&2
  exit 1
fi

PYTHON_BIN="${HERMES_GATEWAY_SETUP_PYTHON:-$(dirname "$HERMES_BIN")/python3}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3 || true)"
fi

if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo "python3 is required to run ArcLink-managed Hermes gateway setup." >&2
  exit 1
fi

set +e
HERMES_HOME="$HERMES_HOME_DIR" "$PYTHON_BIN" - "$@" <<'PY'
import sys

try:
    from hermes_cli import gateway as gw
except Exception as exc:
    print(
        f"ArcLink could not import Hermes gateway internals for managed setup: {exc}",
        file=sys.stderr,
    )
    raise SystemExit(86)

original_prompt_yes_no = gw.prompt_yes_no
notified = False


def _is_gateway_service_prompt(question: object) -> bool:
    text = " ".join(str(question or "").lower().split())
    return (
        ("install the gateway as a" in text and "service" in text)
        or "start the gateway service" in text
        or "start the service now" in text
        or "restart the gateway to pick up changes" in text
        or text == "start it now?"
    )


def _notify_once() -> None:
    global notified
    if notified:
        return
    notified = True
    gw.print_info(
        "  ArcLink manages gateway persistence with its own systemd units; "
        "skipping Hermes-native service install/start."
    )


def arclink_prompt_yes_no(question: object, default: bool = True) -> bool:
    if _is_gateway_service_prompt(question):
        _notify_once()
        return False
    return original_prompt_yes_no(question, default)


def arclink_install_linux_gateway_from_setup(force: bool = False):
    _notify_once()
    return None, False


gw.prompt_yes_no = arclink_prompt_yes_no
gw.install_linux_gateway_from_setup = arclink_install_linux_gateway_from_setup
gw.gateway_setup()
PY
status=$?
set -e

if [[ "$status" -eq 0 ]]; then
  exit 0
fi

if [[ "$status" -eq 86 ]]; then
  echo "Falling back to plain Hermes gateway setup; Hermes-native service prompts may appear." >&2
  exec env HERMES_HOME="$HERMES_HOME_DIR" "$HERMES_BIN" gateway setup "$@"
fi

exit "$status"
