# Bridge Cold-Start Optimization — Adversarial Federation Brief

_32-agent ultracode federation (3 ground-truth verifiers, 4 designs x 5 adversaries + verdict, 1 synthesizer). All load-bearing claims re-verified against code by the main loop._

## Design verdicts

| Design | Verdict | Kept/Killed |
|---|---|---|
| daemon | fatal | killed |
| pool | needs-fixes | killed |
| optimized cold spawn | kept | D5 + jitter + reaper first; L3a compileall warmup safe |
| wildcard | fatal | killed |

---

## Synthesized recommendation

All decisive facts confirmed against code:

1. **Detached worker is control-side** (`Popen([sys.executable, __file__, '--public-agent-bridge-worker'])`, `Config.from_env()` + `connect_db(cfg)`). The `docker exec` is only the inner cmd. → A daemon that relocates the terminal mark *into* the container hits the wrong DB. **Fatal for in-container daemon.**
2. **Realign restart is `defer` by default**, flips to `restart` only on ref change, and even then routes through `refresh-agent-install.sh --restart-gateway` (systemd-user), NOT the docker container. The docker container recreate is the *separate* best-effort `--force-recreate hermes-gateway` path with per-deployment try/except ("one ArcPod refresh must not halt the control upgrade") and `_service_secrets_available` gating. → No reliable upgrade hook reaches any in-container long-lived process. **Fatal for daemon/sidecar lock-step.**
3. **Backoff is deterministic, no jitter** (`60 * 2**(attempts-1)` clamped `[60,3600]`). Confirmed.
4. **Allowlist is exactly 6-token `docker exec -i` or 13-token `docker compose exec`.** A `--serve-client`/`--daemon` argv fails it. The broker rebuilds only these shapes. Confirmed.
5. **D5 is violated**: `main()` prints `{"ok": True, "delivered": True}` unconditionally on clean `asyncio.run` return (line 810). The Discord `sent_ids` (741) and Telegram `result_message_id` (286, approval-only) never reach `main()`. Confirmed.

I have enough to write the decisive brief.

# Decision Brief: Public-Bot Bridge Cold-Start — Winning Architecture

**Author:** Claude Final Synthesizer · **Scope:** GAP-019 public-bot (Telegram/Discord) bridged-turn cold-start, target ≥50% bootstrap-tax cut · **Status:** Decisive recommendation, code-anchored. D5 + retry jitter + orphan reaper + L3a compileall warmup were implemented locally on 2026-06-17; live Telegram/Discord proof remains gated by `PG-PUBLIC-AGENT-DELIVERY`.

---

## 1. Verdict: WIN = "Optimized Cold Spawn" (spawn L1+L2+L3a) + a mandatory standalone **D5 + durability hardening** track. KILL the in-container daemon, the warm prefork (L3b), and the warm sidecar.

The winner is **not** a warm long-lived process. Every long-lived/forked variant (daemon, pool L3b, sidecar) dies on the **same two verified facts**, not on fixable punch-lists:

- **DB boundary (fatal):** The detached worker that writes `mark_notification_delivered/error` is a **control-side** Popen child (`python/arclink_notification_delivery.py:2093` dispatch; spawned at `:1280-1311` as `[sys.executable, __file__, '--public-agent-bridge-worker', job_path]`), running `cfg = Config.from_env()` + `connect_db(cfg)` against the **control** `notification_outbox` (terminal writes at `:1167,:1258,:1264`). Only the *inner* `docker exec` cmd crosses into the ArcPod container. Any design that moves turn execution into a resident in-container process must either (a) relocate the terminal mark into the container — which writes the **wrong DB** (per-deployment memory-state, not the control outbox), stranding rows `delivered_at IS NULL` under the ~7500s lease → ~2h stalls then duplicate turns; or (b) keep the mark control-side and **block** the worker on the daemon result — which deletes the daemon's fire-and-forget perf premise.
- **No upgrade hook reaches a resident process (fatal lock-step):** Confirmed in `bin/deploy.sh` — `realign_active_enrolled_agents_root` defaults `gateway_restart_policy="defer"` (`:5166,:5514,:5645`), flips to `restart` only on ref change (`:5552,:5693`), and even then routes through `refresh-agent-install.sh --restart-gateway` = **systemd-user** units, never the Docker container. The container recreate is a *separate, best-effort* `--force-recreate hermes-gateway` (`bin/arclink-docker.sh:2485-2497`) gated on `_service_secrets_available` and wrapped in per-deployment `try/except` ("one ArcPod refresh must not halt the control upgrade", `:2497`) called `|| true`. A skipped recreate leaves a warm process serving **stale adapter code** with no trigger to reload, and the daemon's `ARCLINK_HERMES_AGENT_REF` env / `git rev-parse HEAD` self-check is image-baked and immutable inside a live container → the per-turn ref compare is **tautological** (can never fire).

Because lock-step in this codebase is *a consequence of fresh per-turn spawn into the container*, the optimization that buys the most (skip imports) is exactly the one that breaks the hardest invariant. The win therefore keeps the spawn boundary and attacks the work *inside* a still-fresh process.

**Winning architecture = three independently-shippable, default-OFF, flag-reversible layers, each preserving the spawn boundary byte-for-byte:**

| Layer | What | Flag | Lock-step / isolation cost |
|---|---|---|---|
| **L1** | Single-platform config short-circuit — **env-starve only** | `ARCLINK_BRIDGE_SINGLE_PLATFORM_CONFIG` | none (still fresh spawn; never hand-build PlatformConfig) |
| **L2** | getMe cache (`_bot_user` per token-hash), bundled with D5 | `ARCLINK_BRIDGE_GETME_CACHE` | none (per-token-hash, isolation-safe) |
| **L3a** | `.pyc`-warmed venv (`compileall` at deploy) | (deploy-time) | none, perfect idle elasticity |
| **D5** | Real platform-ack delivery evidence (**standalone, transport-invariant, lands FIRST**) | (no flag — correctness fix) | hardens the existing fail-open path |

Plus two **mandatory standalone durability co-changes** that the attacks surfaced as latent bugs and that are correct regardless of any latency work:

- **Jitter** on `notification_error_retry_delay_seconds` (`arclink_control.py` — confirmed `60*(2**(step-1))` clamped `[60,3600]`, **no jitter**).
- **Orphan/lease reaper** (today `_load_public_agent_bridge_job` read-then-unlinks before the turn runs; no sweep exists; recovery is only ~7500s lease expiry).

### Why this survives the attacks the others failed
- **Durability (no loss/dup):** outbox row + atomic O_EXCL job + detached worker + `_claim_notification_for_delivery` single-claim (`:1757` is the real claim site; `target_kind='public-agent-turn'` filter in the SELECTs at `:1804/:2037`) + covering index (`arclink_control.py` `idx_notification_outbox_pending_target_channel_next_attempt`, confirmed verbatim) are **untouched** — the spawn boundary, lease, and terminal mark all stay where they are.
- **Isolation:** still one fresh process per turn per deployment; one token in one `os.environ` for sub-second lifetime; **no resident multi-token address space**, so the operator-twin co-mingling break (single shared `control-operator-hermes-gateway` container, `:910`) is structurally impossible.
- **Lock-step:** every turn re-execs `docker exec` into whatever runtime is currently installed — the property the whole codebase relies on — preserved by construction.

---

## 2. Resolving the hardest adversarial breaks (concrete mechanisms)

### A. Lock-step on upgrade
**Mechanism:** *Do nothing new.* L1/L2/L3a keep the per-turn `docker exec -i <container> <PUBLIC_AGENT_BRIDGE_PYTHON> <PUBLIC_AGENT_BRIDGE_SCRIPT>` spawn (`arclink_notification_delivery.py:800/:914`, allowlisted to the exact 6-token shape in `_validate_public_agent_bridge_cmd:514-528`). Each turn cold-imports `gateway.*` from `/opt/arclink/runtime` via `_add_runtime_paths()` (`arclink_public_agent_bridge.py:50,:373`). An in-place `git checkout` or a container recreate is picked up on the *next* turn with zero new machinery. **L1 constraint to honor lock-step:** env-starve form ONLY (`HERMES_GATEWAY_ONLY_PLATFORM` + unset the unused platform's token env before `load_gateway_config()`); **never** the "skip `load_gateway_config`, build `PlatformConfig()` directly" fallback — that would make ArcLink own a config structure that must track upstream Hermes across releases (a new lock-step coupling). If the installed release does not honor the single-platform env, L1 **no-ops**, it does not fall back.

### B. Per-deployment isolation + bot-token non-comingling
**Mechanism:** unchanged — one fresh process, one token. `os.environ['TELEGRAM_BOT_TOKEN']=bot_token` (`arclink_public_agent_bridge.py:382`) dies with the process. Job file stays token-stripped (`_strip_public_agent_bridge_payload_secrets`) and re-hydrated per-turn (`_hydrate_public_agent_bridge_payload_secret`). **L2 caveat:** the getMe cache is keyed `sha256(token)` (isolation-safe), but **store it outside the Agent-writable tree** (root-owned dir, the Agent uid cannot read/write — `arclink-code`/`arclink-terminal` plugins run in that container), key by `HMAC(server_secret, token)` to kill the token-confirmation oracle, TTL ≪ 24h, and treat cache-miss as **fail-open to live getMe**.

### C. Durability handoff (no loss/dup, lease + on-disk job)
**Mechanism:** spine untouched. Add the **orphan/lease reaper** the codebase lacks today: a startup + periodic scan that, for any `target_kind='public-agent-turn'` row with `delivered_at IS NULL`, a far-future `next_attempt_at`, and **no live worker/child pid**, resets `next_attempt_at <= now` — gated through a **re-claim** via `_claim_notification_for_delivery` so the atomic single-claim remains the *only* dedup across the reaper and the live loops. This closes the verified ~2h silent-stall window (read-then-unlink job, no sweep) without shortening the lease or letting the live worker reclaim DEFERRED rows.

### D. CANON-12 D5 — real platform acknowledgement
**This is the load-bearing correctness fix and it lands FIRST, on the COLD path, transport-invariant — before any latency flag.** Today `main()` prints `{"ok": True, "delivered": True}` unconditionally on clean `asyncio.run` return (`arclink_public_agent_bridge.py:810`); the worker marks delivered on bare `ok` (`:1258`).

Concrete mechanism (the "data already exists" claim is **false** as-is — must be wired):
1. **Capture at the adapter send boundary the bridge already owns.** Discord already overrides `adapter.send=_send` (`:761`) returning `SendResult(message_id=sent_ids[0]...)` (`:741`) — thread that into a per-turn collector. **Telegram has no reply-send wrapper** (only `send_exec_approval` is wrapped at `:276-311`; `:286` is the approval-*prompt* id), so **add** a wrap of the native Telegram adapter `send`/`send_message`/`edit_message` before `handle_message`, mirroring the existing approval wrapper, recording returned message ids into the same collector.
2. **Three-valued, not binary:** `confirmed` (real new message id OR a 2xx final edit that wrote non-empty content) / `unknown` (turn completed, no id captured) / `failed`. `main()` emits `{"ok": true, "delivered": <confirmed>, "message_ids": [...]}`.
3. **Streaming `transport='edit'` (default on):** gate `delivered` on the **final** edit succeeding with content, not on the placeholder send id (`_edit_message:752` echoes the input id and returns success on any non-3xx).
4. **Album leader:** keep `_absorb_telegram_album_siblings` sibling-delivered marks (`:1674`) as a **distinct `delivered_reason='absorbed_into_album_leader'`** that bypasses the message-id requirement; only the leader's real send is gated.
5. **All five gates + broker:** thread message ids through every `mark_notification_delivered` caller (`:1167` broker, `:1258` docker-exec, the sync gates, and `run_*_turns_once` at `:1858/:2074`) AND change the broker's `_run_gateway_exec_broker_request` contract (today returns bare `(True, '')` on HTTP-ok) to require a non-empty `message_id`. Otherwise the broker production path stays fail-open.
6. **Avoid the retry-dup trap:** on `unknown` do **not** auto-retry into the (now-jittered) backoff — thread `notification_id` as a send dedup key so a retried turn re-acks instead of re-sending; surface persistent `unknown` for reconciliation. Pairing "require id" with blind "retry-on-missing-id" would manufacture duplicates because Hermes turns are not idempotent.

---

## 3. What gets KILLED, and why

- **Daemon (in-container resident, request-serving) — KILLED.** Fatal DB boundary (terminal mark in wrong DB), operator-twin token co-mingling in the single shared `control-operator-hermes-gateway` container (`:910`), broker allowlist rejects `--daemon`/`--daemon-submit` shapes (`_validate_public_agent_bridge_cmd` accepts only 6-token `docker exec -i` / 13-token `docker compose exec`), upgrade hook (`realign`) never signals it, and orphan-sweep keyed on "row pending" double-delivers healthy in-flight turns. Multiple independent fatals.
- **Pool / prefork-per-Pod (L3b) — KILLED.** No supervisor exists (`hermes-gateway` is a single `exec`'d foreground process; no s6/supervisord), ref-check is tautological (image-baked runtime), abstract Unix socket = an unauthenticated turn-spawning fork-factory *inside* the untrusted container (`_hydrate` backfills the real token if `bot_token` omitted) inverting GAP-019, O(N) resident memory in the 512M cgroup with no idle eviction, and the broker transport bypasses it entirely. The *only* layer that pushed Discord past 50% is the one that breaks the hardest constraint.
- **Warm sidecar (wildcard) — KILLED.** Built on a false deployment model (runtime is one **shared** host checkout swapped in place, not per-Pod image), the named upgrade-restart step does not exist, the refuse-to-serve gate needs a runtime-ref oracle that does not exist, and it splits the side-effect (send, in sidecar) from terminal-state (mark, in worker) → committed user messages the outbox can't see → lease/backoff duplicates.

**Net:** every warm variant is uneconomic *because the durability terminal-mark and the upgrade lifecycle both live control-side / systemd-side, and the only thing that reliably crosses into the container per turn is the spawn itself.* Warming compute means re-plumbing two subsystems that the spawn model gets for free.

**Honest concession on the goal:** L1+L2+L3a lands **~30–50%** of the bootstrap tax on Telegram (getMe-heavy deployments hit 50%; the getMe RTT is the dominant variable cost), but **Discord (no getMe) reaches only ~15–25%** — it has no large variable cost to remove without import amortization, which only a resident process delivers. The ≥50%-on-both-platforms target is **not achievable without breaking lock-step**, so we deliberately accept sub-50% on Discord rather than ship a fatal warm process. If Discord ≥50% becomes non-negotiable, the only lock-step-safe avenue is reducing the cold-import graph itself (zipimport/frozen bundle, trimming `gateway.*` lazy imports) — not a warm process.

---

## 4. Prototype / rollout plan

**Highest-ROI first step (ships before any latency flag):** **D5 on the cold path + jitter + reaper.** These are correctness fixes that harden the existing fail-open path, benefit production today, and are prerequisites for safely touching the exit path later.

1. **PR-1 (D5, no flag):** add Telegram reply-send wrapper + Discord collector threading; three-valued ack; broker contract carries `message_id`; all five `mark_notification_delivered` gates require `delivered AND message_ids` (album carve-out). **Regression proofs** (FakeDockerRunner / fake adapters, no live secrets): (a) no-message turn → `mark_notification_error`, not delivered; (b) `{ok:true, delivered:false}` → not delivered; (c) album leader+siblings deliver once; (d) edit-streaming final-edit-fails → not delivered; (e) broker path requires id; (f) `unknown` does not auto-retry-resend (dedup key).
2. **PR-2 (jitter + reaper, no flag):** ±25% jitter in `notification_error_retry_delay_seconds`; orphan reaper re-claiming via `_claim_notification_for_delivery`. Proofs: correlated-failure de-sync; SIGKILL'd worker → reaper re-arms exactly once, no duplicate.
3. **PR-3 (L3a):** `compileall` at deploy alongside the ref write. Zero-flag, pure win.
4. **PR-4 (L1, `ARCLINK_BRIDGE_SINGLE_PLATFORM_CONFIG=0`):** env-starve only, gated on in-container verification the release honors `HERMES_GATEWAY_ONLY_PLATFORM`; no-op (not fall back) otherwise.
5. **PR-5 (L2, `ARCLINK_BRIDGE_GETME_CACHE=0`):** root-owned cache dir, HMAC key, short TTL, fail-open to live getMe; **bundled with D5** so a revoked token fails closed at send.

**Clean fallback:** every flag defaults OFF; the per-turn `docker exec python bridge.py` path is never deleted. Rollback = flip flags to 0, redeploy. No schema/lease/index/backoff migration (D5/jitter/reaper are forward-only correctness improvements with no rollback hazard).

**NAMED live-proof gate — `PG-PUBLIC-AGENT-DELIVERY`** (must pass before D5 defaults on and before any flag flips on a Pod): drive a real Telegram **and** a real Discord turn through each transport (docker exec, docker compose exec, broker HTTP); assert the outbox row is marked delivered **only** with a real returned platform `message_id`; assert a forced failed/no-message send marks **error** (not delivered); assert an in-place runtime ref bump mid-window still serves the current release (cold path, by construction); assert a SIGKILL'd worker re-arms exactly once via the reaper with no duplicate user message.

---

## 5. Residual risks + measurements to take

**Residual risks (honest):**
- **Discord misses ≥50%** under the lock-step-safe scope. Accepted; documented.
- **L2 getMe cache** removes the only forced per-turn bot-reachability probe; a revoked token surfaces only at send. Mitigated by the D5 send-ack gate (revoked → no id → error) — **L2 must not ship without D5**.
- **D5 Telegram wrap** touches the send path adjacent to upstream `gateway.*`; keep the wrap strictly ArcLink-side (monkeypatch `adapter.send`, like the existing approval wrapper) to avoid forking Hermes and breaking lock-step.
- **L1** depends on the installed release honoring `HERMES_GATEWAY_ONLY_PLATFORM`; if a future Hermes upgrade changes that env's semantics, L1 silently no-ops (safe) rather than misconfigures — but verify per release in the live gate.

**Latency attribution to measure before/after (local A/B harness, FakeDockerRunner timing exec→first-frame):** decompose the cold tax into its five centers and report each independently — (1) interpreter create + site init; (2) cold import of `telegram` + `gateway.config/run/platforms.base/session` (`:389-393/:678-681`); (3) `load_gateway_config()` all-platforms YAML+env parse (`gateway/config.py:545-548,1049-1103`); (4) `GatewayRunner` + `_create_adapter` (`:410-411`); (5) Telegram `Bot.initialize()` getMe RTT (`:420-421`). Report Telegram and Discord separately, and report the bootstrap-tax % reduction *excluding* the LLM turn (the up-to-7200s detached inference is untouched and must not be in the denominator). Capture first-turn-after-idle vs steady-state so the L2 cache hit-rate is visible.

**Bottom line:** keep the spawn boundary — it *is* the safety mechanism for lock-step, isolation, and the control-side durability handoff. Buy the cleanly-attainable latency with L1+L2+L3a behind flags, and spend the real engineering on the **D5 delivery-evidence + jitter + orphan-reaper** track, which is correct independent of any cold-start work and which every warm proposal proved is the actual pre-existing risk.
