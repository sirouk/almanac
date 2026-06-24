#!/usr/bin/env python3
"""Replay Raven captain journeys through the real public-bot handlers.

The harness intentionally does not log in to Telegram/Discord or impersonate a
Captain transport account. It replays the same inbound bot turns against an
existing control DB, copying that DB by default so journey discovery is safe.
Use ``--mutate-live-db`` only when explicitly validating stateful live behavior.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import Any, Iterable, Mapping, Sequence

from arclink_control import utc_now_iso
from arclink_public_bots import (
    ArcLinkPublicBotTurn,
    arclink_public_bot_turn_discord_components,
    arclink_public_bot_turn_telegram_reply_markup,
    handle_arclink_public_bot_turn,
)


DEFAULT_DB_PATH = Path("arclink-priv/state/arclink-control.sqlite3")
DEFAULT_ACADEMY_FOCUS = (
    "Personal training: exercise programming, nutrition and meal planning, "
    "and natural supplements for a balanced, healthy life."
)
DEFAULT_ACADEMY_EXAM = "\n".join(
    [
        "Design a safe 3-day/week beginner strength and cardio plan with sensible progression, citing a governed source.",
        "Build one day of balanced meals plus a natural supplement suggestion for recovery with caveats, grounded in a source.",
    ]
)
DEFAULT_ACADEMY_SOURCES = "none"
DEFAULT_ACADEMY_BOUNDARIES = "never give medical diagnosis or replace a doctor; flag when to consult a licensed professional"


class _HarnessLiveTrainer:
    live = True

    def synthesize(self, *, role_title: str, topic: str, charter: Mapping[str, Any], sources: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        return {
            "engine": "live-router",
            "authored": True,
            "lesson_notes": [
                {
                    "source_uid": str(source.get("source_uid") or ""),
                    "note": (
                        "Use this governed source to answer the Captain's acceptance scenarios with retrieve-first, "
                        "cite-first discipline and domain-specific caveats."
                    ),
                }
                for source in sources
                if str(source.get("source_uid") or "")
            ],
            "soul_capsule": (
                f"You are {role_title or 'an Academy-trained specialist'}. Use the governed lesson notes only, "
                "retrieve before answering, cite before making specialist claims, and refuse boundary violations."
            ),
            "retrieval_rules": ["retrieve a governed lesson note before answering", "cite a retrieved source before specialist claims"],
            "quality_metrics": {"engine": "harness-live", "source_count": len(sources)},
        }


@dataclass
class JourneyStep:
    name: str
    sent: str
    action: str
    status: str
    reply_preview: str
    buttons: list[dict[str, str]] = field(default_factory=list)
    telegram_callbacks: list[str] = field(default_factory=list)
    discord_custom_ids: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)


@dataclass
class HarnessResult:
    ok: bool
    mode: str
    channel: str
    channel_identity: str
    user_id: str
    deployment_id: str
    db_path: str
    copied_db: bool
    steps: list[JourneyStep]
    errors: list[str] = field(default_factory=list)
    backend: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "mode": self.mode,
            "channel": self.channel,
            "channel_identity": self.channel_identity,
            "user_id": self.user_id,
            "deployment_id": self.deployment_id,
            "db_path": self.db_path,
            "copied_db": self.copied_db,
            "steps": [
                {
                    "name": step.name,
                    "sent": step.sent,
                    "action": step.action,
                    "status": step.status,
                    "reply_preview": step.reply_preview,
                    "buttons": step.buttons,
                    "telegram_callbacks": step.telegram_callbacks,
                    "discord_custom_ids": step.discord_custom_ids,
                    "checks": step.checks,
                }
                for step in self.steps
            ],
            "errors": list(self.errors),
            "backend": dict(self.backend),
        }


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=60000")
    return conn


def _preview(text: str, *, limit: int = 360) -> str:
    clean = " ".join(str(text or "").split())
    return clean[:limit].rstrip()


def _turn_buttons(turn: ArcLinkPublicBotTurn) -> list[dict[str, str]]:
    return [
        {
            "label": str(button.label or ""),
            "command": str(button.command or ""),
            "url": str(button.url or ""),
            "style": str(button.style or ""),
        }
        for button in (turn.buttons or ())
    ]


def _telegram_callbacks(turn: ArcLinkPublicBotTurn) -> list[str]:
    markup = arclink_public_bot_turn_telegram_reply_markup(turn) or {}
    callbacks: list[str] = []
    for row in markup.get("inline_keyboard") or []:
        for button in row or []:
            if isinstance(button, Mapping) and button.get("callback_data"):
                callbacks.append(str(button.get("callback_data") or ""))
    return callbacks


def _discord_custom_ids(turn: ArcLinkPublicBotTurn) -> list[str]:
    callbacks: list[str] = []
    for row in arclink_public_bot_turn_discord_components(turn) or []:
        for button in row.get("components") or []:
            if isinstance(button, Mapping) and button.get("custom_id"):
                callbacks.append(str(button.get("custom_id") or ""))
    return callbacks


def _step(name: str, sent: str, turn: ArcLinkPublicBotTurn, *, checks: Mapping[str, bool] | None = None) -> JourneyStep:
    return JourneyStep(
        name=name,
        sent=sent,
        action=str(turn.action or ""),
        status=str(turn.status or ""),
        reply_preview=_preview(turn.reply),
        buttons=_turn_buttons(turn),
        telegram_callbacks=_telegram_callbacks(turn),
        discord_custom_ids=_discord_custom_ids(turn),
        checks=dict(checks or {}),
    )


def _callback_to_message(raw: str) -> str:
    value = str(raw or "").strip()
    if value.startswith("arclink:"):
        value = value[len("arclink:") :]
    return value.strip()


def _first_callback(turn: ArcLinkPublicBotTurn, *, contains: str = "", exclude: Iterable[str] = ()) -> str:
    needles = [str(item).casefold() for item in exclude]
    target = str(contains or "").casefold()
    candidates: list[str] = []
    for button in turn.buttons or ():
        command = str(button.command or "").strip()
        label = str(button.label or "").strip()
        if not command or command.startswith("/cancel"):
            continue
        haystack = f"{label} {command}".casefold()
        if target and target not in haystack:
            continue
        if any(needle and needle in haystack for needle in needles):
            continue
        candidates.append(command)
    if not candidates:
        callbacks = [_callback_to_message(item) for item in _telegram_callbacks(turn)]
        for command in callbacks:
            if command and not command.startswith("/cancel"):
                candidates.append(command)
    if not candidates:
        raise RuntimeError(f"no usable button found for action={turn.action!r}")
    return candidates[0]


def _deployment_context(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str = "",
    user_id: str = "",
    deployment_id: str = "",
) -> dict[str, str]:
    where: list[str] = []
    params: list[str] = []
    if channel_identity:
        where.append("LOWER(s.channel) = LOWER(?) AND LOWER(s.channel_identity) = LOWER(?)")
        params.extend([channel, channel_identity])
    if deployment_id:
        where.append("s.deployment_id = ?")
        params.append(deployment_id)
    if user_id:
        where.append("s.user_id = ?")
        params.append(user_id)
    if not where:
        raise ValueError("provide --channel-identity, --deployment-id, or --user-id")
    row = conn.execute(
        f"""
        SELECT s.session_id, s.channel, s.channel_identity, s.user_id, s.deployment_id,
               d.prefix, d.status AS deployment_status
        FROM arclink_onboarding_sessions s
        LEFT JOIN arclink_deployments d ON d.deployment_id = s.deployment_id
        WHERE {' OR '.join(f'({item})' for item in where)}
        ORDER BY
          CASE d.status WHEN 'active' THEN 0 WHEN 'first_contacted' THEN 1 ELSE 2 END,
          s.updated_at DESC, s.created_at DESC, s.session_id DESC
        LIMIT 1
        """,
        tuple(params),
    ).fetchone()
    if row is None:
        raise RuntimeError("could not resolve a Raven public-bot session for the supplied target")
    return {key: str(row[key] or "") for key in row.keys()}


def _send(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    text: str,
    display_name: str = "",
) -> ArcLinkPublicBotTurn:
    return handle_arclink_public_bot_turn(
        conn,
        channel=channel,
        channel_identity=channel_identity,
        text=text,
        metadata={"harness": "raven_journey", "harness_at": utc_now_iso()},
        display_name_hint=display_name,
    )


def run_entry_probe(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    display_name: str = "",
) -> list[JourneyStep]:
    steps: list[JourneyStep] = []
    agents = _send(conn, channel=channel, channel_identity=channel_identity, text="/agents", display_name=display_name)
    tg = _telegram_callbacks(agents)
    dc = _discord_custom_ids(agents)
    checks = {
        "has_academy_button": any("academy" in item.casefold() for item in tg + dc),
        "has_train_crew_button": any("train_crew" in item.casefold() or "train-crew" in item.casefold() for item in tg + dc),
        "telegram_active_academy_raven": any(item == "arclink:/raven academy" for item in tg),
        "discord_active_academy_raven": any(item == "arclink:/raven academy" for item in dc),
    }
    steps.append(_step("agents_menu", "/agents", agents, checks=checks))
    academy = _send(conn, channel=channel, channel_identity=channel_identity, text="/raven academy", display_name=display_name)
    steps.append(
        _step(
            "academy_entry",
            "/raven academy",
            academy,
            checks={
                "announces_interview": "real interview" in academy.reply.casefold(),
                "selects_agent": academy.action == "academy_training_select_agent",
            },
        )
    )
    crew = _send(conn, channel=channel, channel_identity=channel_identity, text="/raven train_crew", display_name=display_name)
    steps.append(
        _step(
            "crew_entry",
            "/raven train_crew",
            crew,
            checks={
                "opens_crew_training": crew.action.startswith("crew_training_"),
                "asks_role": "what is your role" in crew.reply.casefold(),
            },
        )
    )
    return steps


def run_academy_walk(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    display_name: str = "",
    target_deployment_id: str = "",
    major: str = "domain_tutor",
    focus: str = DEFAULT_ACADEMY_FOCUS,
    exam: str = DEFAULT_ACADEMY_EXAM,
    sources: str = DEFAULT_ACADEMY_SOURCES,
    boundaries: str = DEFAULT_ACADEMY_BOUNDARIES,
    open_mode: bool = False,
) -> list[JourneyStep]:
    steps: list[JourneyStep] = []
    turn = _send(conn, channel=channel, channel_identity=channel_identity, text="/raven academy", display_name=display_name)
    steps.append(_step("academy_entry", "/raven academy", turn, checks={"selects_agent": turn.action == "academy_training_select_agent"}))
    if turn.action == "academy_training_select_agent":
        command = _first_callback(turn, contains=target_deployment_id) if target_deployment_id else _first_callback(turn)
        turn = _send(conn, channel=channel, channel_identity=channel_identity, text=command, display_name=display_name)
        steps.append(_step("academy_select_agent", command, turn, checks={"choose_major": turn.action == "academy_training_choose_major"}))
    if turn.action == "academy_training_choose_major":
        command = _first_callback(turn, contains=major) if major else _first_callback(turn)
        turn = _send(conn, channel=channel, channel_identity=channel_identity, text=command, display_name=display_name)
        steps.append(_step("academy_choose_major", command, turn, checks={"focus_prompt": turn.action == "academy_training_focus"}))
    for name, answer, expected in (
        ("academy_focus", focus, "academy_training_charter_exam"),
        ("academy_exam", exam, "academy_training_sources"),
        ("academy_sources", sources, "academy_training_charter_boundaries"),
        ("academy_boundaries", boundaries, "academy_training_charter_preview"),
    ):
        turn = _send(conn, channel=channel, channel_identity=channel_identity, text=answer, display_name=display_name)
        steps.append(_step(name, answer, turn, checks={f"reached_{expected}": turn.action == expected}))
    if open_mode:
        turn = _send(conn, channel=channel, channel_identity=channel_identity, text="open", display_name=display_name)
        steps.append(_step("academy_open_mode", "open", turn, checks={"mode_opened": turn.action == "academy_mode_opened"}))
    return steps


def validate_training_backend(
    conn: sqlite3.Connection,
    *,
    deployment_id: str,
    actor: str,
) -> dict[str, Any]:
    """On a copied DB, prove the selected Agent can train, graduate, exam-pass, and stage apply.

    This does not call the live router and does not write an agent home. It uses
    the production Academy APIs with a fake-live trainer/runner so the same
    graduation/apply gates are exercised deterministically.
    """
    from arclink_academy_programs import (
        FakeAgentRunner,
        academy_trainee_graduation_state,
        end_academy_mode,
        get_open_academy_mode,
        materialize_operator_academy_sources,
        run_academy_acceptance_exam,
        run_academy_trainer_synthesize,
        stage_academy_apply,
    )

    trainee = conn.execute(
        """
        SELECT *
        FROM academy_trainees
        WHERE deployment_id = ?
        ORDER BY updated_at DESC, created_at DESC, trainee_id DESC
        LIMIT 1
        """,
        (deployment_id,),
    ).fetchone()
    if trainee is None:
        raise RuntimeError("Academy interview did not create a trainee for backend validation")
    trainee_id = str(trainee["trainee_id"])
    materialized = materialize_operator_academy_sources(
        conn,
        deployment_id=deployment_id,
        trainee_id=trainee_id,
        entries=[
            {
                "url": "https://example.test/arclink-raven-journey/governed-source",
                "title": "Raven journey governed source",
                "summary": (
                    "Derived source notes for a safe personal-training domain tutor: progressive overload, recovery, "
                    "balanced meals, hydration, supplement caveats, and consult-professional boundaries."
                ),
            }
        ],
        proposed_by="system:raven-journey-harness",
        commit=False,
    )
    open_mode = get_open_academy_mode(conn, trainee_id=trainee_id)
    if open_mode is None:
        raise RuntimeError("Academy Mode was not open for backend validation")
    ended = end_academy_mode(conn, session_id=str(open_mode["session_id"]), actor=actor, graduate=True)
    if not ended.get("graduated"):
        raise RuntimeError(f"Academy Mode did not graduate in backend validation: {ended.get('status')}")
    synthesis = run_academy_trainer_synthesize(
        conn,
        trainee_id=trainee_id,
        scope="private",
        client=_HarnessLiveTrainer(),
        live_authorized=True,
        commit=False,
    )
    exam = run_academy_acceptance_exam(
        conn,
        trainee_id=trainee_id,
        agent_runner=FakeAgentRunner(live=True, runner_kind="harness-fake-live"),
        live_authorized=True,
        commit=False,
    )
    state = academy_trainee_graduation_state(conn, trainee_id)
    staged = stage_academy_apply(
        conn,
        trainee_id=trainee_id,
        adapter_name="ssh",
        live_authorized=True,
        actor=actor,
        target_kind="deployment",
        target_id=deployment_id,
    )
    return {
        "trainee_id": trainee_id,
        "materialized_count": len(materialized.get("proposals") or []),
        "graduated": bool(ended.get("graduated")),
        "synthesis_authored": bool(synthesis.get("authored")),
        "lesson_note_count": int(synthesis.get("lesson_note_count") or 0),
        "exam_passed": bool(exam.get("passed")),
        "graduation_state": state.get("state"),
        "graduation_badge": state.get("badge"),
        "apply_status": staged.get("status"),
        "apply_writes_enabled": bool(staged.get("writes_enabled")),
        "apply_exam_gate_ok": bool(staged.get("academy_exam_gate_ok")),
        "apply_synthesis_drives": bool(staged.get("academy_synthesis_drives")),
    }


def run_crew_walk(
    conn: sqlite3.Connection,
    *,
    channel: str,
    channel_identity: str,
    display_name: str = "",
    confirm: bool = False,
) -> list[JourneyStep]:
    scripted = [
        ("crew_entry", "/raven train_crew", "crew_training_prompt_role"),
        ("crew_role", "founder building a health coaching business", "crew_training_prompt_mission"),
        ("crew_mission", "ship a coherent client onboarding and coaching workflow in the next 12 weeks", "crew_training_prompt_treatment"),
        ("crew_treatment", "coach", "crew_training_prompt_preset"),
        ("crew_preset", "Vanguard", "crew_training_prompt_capacity"),
        ("crew_capacity", "life coaching", "crew_training_review"),
    ]
    steps: list[JourneyStep] = []
    turn: ArcLinkPublicBotTurn | None = None
    for name, text, expected in scripted:
        turn = _send(conn, channel=channel, channel_identity=channel_identity, text=text, display_name=display_name)
        steps.append(_step(name, text, turn, checks={f"reached_{expected}": turn.action == expected}))
    if confirm and turn is not None:
        turn = _send(conn, channel=channel, channel_identity=channel_identity, text="confirm", display_name=display_name)
        steps.append(_step("crew_confirm", "confirm", turn, checks={"applied_or_blocked_honestly": turn.action in {"crew_training_applied", "crew_training_failed"}}))
    return steps


def _all_checks(steps: Sequence[JourneyStep]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    for step in steps:
        for name, ok in step.checks.items():
            if not ok:
                errors.append(f"{step.name}.{name}")
    return not errors, errors


def run_harness(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    mutate_live_db: bool = False,
    channel: str = "telegram",
    channel_identity: str = "",
    user_id: str = "",
    deployment_id: str = "",
    mode: str = "all",
    display_name: str = "",
    open_academy_mode: bool = False,
    confirm_crew: bool = False,
    validate_backend: bool = False,
) -> HarnessResult:
    source_db = db_path
    copied = False
    tempdir: tempfile.TemporaryDirectory[str] | None = None
    active_db = source_db
    if not mutate_live_db:
        tempdir = tempfile.TemporaryDirectory(prefix="arclink-raven-journey-")
        active_db = Path(tempdir.name) / "journey.sqlite3"
        shutil.copy2(source_db, active_db)
        copied = True
    try:
        conn = _connect(active_db)
        try:
            ctx = _deployment_context(
                conn,
                channel=channel,
                channel_identity=channel_identity,
                user_id=user_id,
                deployment_id=deployment_id,
            )
            resolved_identity = str(channel_identity or ctx["channel_identity"])
            resolved_channel = str(ctx.get("channel") or channel)
            steps: list[JourneyStep] = []
            if mode in {"all", "entry"}:
                steps.extend(run_entry_probe(conn, channel=resolved_channel, channel_identity=resolved_identity, display_name=display_name))
            if mode in {"all", "academy"}:
                steps.extend(
                    run_academy_walk(
                        conn,
                        channel=resolved_channel,
                        channel_identity=resolved_identity,
                        display_name=display_name,
                        target_deployment_id=str(ctx.get("deployment_id") or deployment_id),
                        open_mode=open_academy_mode,
                    )
                )
            if mode in {"all", "crew"}:
                steps.extend(run_crew_walk(conn, channel=resolved_channel, channel_identity=resolved_identity, display_name=display_name, confirm=confirm_crew))
            ok, errors = _all_checks(steps)
            backend: dict[str, Any] = {}
            if validate_backend:
                if not open_academy_mode:
                    errors.append("backend_validation_requires_open_academy_mode")
                    ok = False
                elif mutate_live_db:
                    errors.append("backend_validation_refuses_live_db_mutation")
                    ok = False
                else:
                    backend = validate_training_backend(
                        conn,
                        deployment_id=str(ctx.get("deployment_id") or deployment_id),
                        actor=str(ctx.get("user_id") or user_id or "system:raven-journey-harness"),
                    )
                    expected = {
                        "graduated": True,
                        "synthesis_authored": True,
                        "exam_passed": True,
                        "graduation_state": "graduated",
                        "apply_status": "handoff_to_hermes_home",
                        "apply_writes_enabled": True,
                        "apply_exam_gate_ok": True,
                        "apply_synthesis_drives": True,
                    }
                    for key, value in expected.items():
                        if backend.get(key) != value:
                            errors.append(f"backend.{key}")
                    ok = ok and not errors
            return HarnessResult(
                ok=ok,
                mode=mode,
                channel=resolved_channel,
                channel_identity=resolved_identity,
                user_id=str(ctx.get("user_id") or user_id),
                deployment_id=str(ctx.get("deployment_id") or deployment_id),
                db_path=str(active_db),
                copied_db=copied,
                steps=steps,
                errors=errors,
                backend=backend,
            )
        finally:
            conn.close()
    finally:
        if tempdir is not None:
            tempdir.cleanup()


def _print_text(result: HarnessResult) -> None:
    status = "PASS" if result.ok else "FAIL"
    print(f"{status} Raven journey harness ({result.mode})")
    print(f"target: {result.channel}:{result.channel_identity} user={result.user_id or '-'} deployment={result.deployment_id or '-'}")
    print(f"db: {result.db_path} ({'copy' if result.copied_db else 'LIVE MUTATION'})")
    for index, step in enumerate(result.steps, start=1):
        checks = ", ".join(f"{key}={'ok' if value else 'FAIL'}" for key, value in step.checks.items()) or "no checks"
        print(f"\n{index}. {step.name}: sent={step.sent!r} action={step.action} status={step.status}")
        print(f"   checks: {checks}")
        print(f"   reply: {step.reply_preview}")
        if step.telegram_callbacks or step.discord_custom_ids:
            print(f"   telegram: {step.telegram_callbacks}")
            print(f"   discord:  {step.discord_custom_ids}")
    if result.errors:
        print("\nfailed checks:")
        for item in result.errors:
            print(f"- {item}")
    if result.backend:
        print("\nbackend validation:")
        for key in (
            "trainee_id",
            "materialized_count",
            "graduated",
            "synthesis_authored",
            "lesson_note_count",
            "exam_passed",
            "graduation_state",
            "graduation_badge",
            "apply_status",
            "apply_writes_enabled",
            "apply_exam_gate_ok",
            "apply_synthesis_drives",
        ):
            if key in result.backend:
                print(f"- {key}: {result.backend[key]}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay Raven captain journeys through the real public-bot handlers.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Control DB path. Defaults to arclink-priv/state/arclink-control.sqlite3")
    parser.add_argument("--mutate-live-db", action="store_true", help="Use the DB in place. Default copies to a temp DB and cleans it up.")
    parser.add_argument("--channel", choices=("telegram", "discord"), default="telegram")
    parser.add_argument("--channel-identity", default="", help="Stored public-bot identity, e.g. tg:123 or discord:456")
    parser.add_argument("--user-id", default="", help="Resolve the latest public-bot session for this Captain user id")
    parser.add_argument("--deployment-id", default="", help="Resolve the latest public-bot session for this deployment id")
    parser.add_argument("--mode", choices=("entry", "academy", "crew", "all"), default="all")
    parser.add_argument("--display-name", default="", help="Display-name hint for replayed turns")
    parser.add_argument("--open-academy-mode", action="store_true", help="Continue the Academy walk past preview and open Academy Mode. Safe only on DB copy unless intentional.")
    parser.add_argument("--confirm-crew", action="store_true", help="Confirm the Crew recipe in the walk. Safe only on DB copy unless intentional.")
    parser.add_argument(
        "--validate-backend",
        action="store_true",
        help=(
            "On a copied DB, after --open-academy-mode, inject a governed source, graduate, "
            "fake-live synthesize/exam, and verify the apply gate. Refuses --mutate-live-db."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of a human summary")
    args = parser.parse_args(argv)

    try:
        result = run_harness(
            db_path=Path(args.db),
            mutate_live_db=bool(args.mutate_live_db),
            channel=args.channel,
            channel_identity=args.channel_identity,
            user_id=args.user_id,
            deployment_id=args.deployment_id,
            mode=args.mode,
            display_name=args.display_name,
            open_academy_mode=bool(args.open_academy_mode),
            confirm_crew=bool(args.confirm_crew),
            validate_backend=bool(args.validate_backend),
        )
    except Exception as exc:  # noqa: BLE001 - CLI reports redacted, non-secret structural failure.
        payload = {"ok": False, "error": str(exc)}
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"FAIL Raven journey harness: {exc}")
        return 1
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        _print_text(result)
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
