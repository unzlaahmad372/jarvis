# JARVIS Architecture & Phase Readiness Checklist

Use this checklist when reviewing Amazon Q's work. Do not accept "implemented" without evidence.

## 1. Environment

- [ ] `.venv` is created in the project root.
- [ ] `.venv` is gitignored.
- [ ] A clean terminal can activate the environment.
- [ ] Backend installs from the documented command.
- [ ] Frontend installs from the lockfile.
- [ ] Supported Python and Node versions are documented.
- [ ] `.env.example` exists and contains no secrets.
- [ ] Local server binds to `127.0.0.1` by default.

## 2. Architecture Boundaries

- [ ] FastAPI/backend does not depend on React implementation details.
- [ ] GUI communicates only through defined API contracts.
- [ ] LLM provider is replaceable.
- [ ] Embedding provider is replaceable.
- [ ] Vector store is behind an interface.
- [ ] Tools are behind ToolRegistry/ToolExecutor.
- [ ] Policy decisions are deterministic code, not LLM decisions.
- [ ] ContextBuilder owns prompt-budget assembly.
- [ ] Secrets/vault is separate from RAG knowledge.

## 3. Mock/Fake Test Requirement

For every implemented module ask Amazon Q:

> Show me the module's test manifest, its dependency fakes/mocks, and the tests covering happy path, failure path, boundaries and security behavior. Do not change code yet; first report gaps.

Then verify:

- [ ] LLM has FakeLLMProvider.
- [ ] Embeddings have FakeEmbeddingProvider.
- [ ] Vector store has fake/in-memory implementation.
- [ ] DB tests use temporary SQLite or fake repository.
- [ ] Clock/scheduler can use fake time.
- [ ] Kubernetes uses FakeKubernetesClient.
- [ ] Prometheus uses fake HTTP responses/transport.
- [ ] Jenkins uses FakeJenkinsClient or mocked transport.
- [ ] Grafana uses FakeGrafanaClient or mocked transport.
- [ ] Spinnaker uses FakeSpinnakerClient or mocked transport.
- [ ] File-opening tests use a fake OS opener and temporary allowed roots.
- [ ] STT/TTS have fake providers.
- [ ] Tools can be replaced with fake tools.
- [ ] GUI can mock backend/API requests.
- [ ] Unit tests do not need Internet, credentials, Ollama, Kubernetes or a GPU.

## 4. Security

- [ ] No secrets are committed.
- [ ] Secret scanner/pre-commit check exists or is planned.
- [ ] Path traversal tests exist.
- [ ] Symlink escape tests exist where filesystem tools exist.
- [ ] FileAccessRegistry grants/revokes roots explicitly; no unrestricted filesystem default.
- [ ] `open_file` validates the normalized path before handing it to the OS.
- [ ] Jenkins/Grafana/Spinnaker URLs are restricted to configured trusted origins.
- [ ] Prompt-injection content is treated as untrusted data.
- [ ] SENSITIVE actions require confirmation.
- [ ] DANGEROUS actions cannot silently execute.
- [ ] Confirmation is bound to exact tool + exact normalized parameters.
- [ ] Confirmation expires and cannot be reused for another action.
- [ ] Feature flags gate risky capabilities in deterministic code.
- [ ] Logs are tested for secret redaction.

## 5. Data & Recovery

- [ ] SQLite schema is versioned/migrated.
- [ ] Embedding/index version is recorded.
- [ ] Prompt/policy versions are recorded.
- [ ] Vector index can be rebuilt from source documents/metadata.
- [ ] Forget vs purge behavior is explicit.
- [ ] Backup has checksum/integrity metadata.
- [ ] Restore test/drill exists when backups are introduced.

## 6. RAG Quality

- [ ] Synthetic Golden Q&A corpus exists.
- [ ] Expected source documents are encoded in eval cases.
- [ ] Retrieval metrics are recorded.
- [ ] Unsupported claims/citation mistakes are checked.
- [ ] Changes to embeddings/chunking/prompts trigger regression eval.

## 7. Context Management

- [ ] Hard context budget is enforced.
- [ ] System/security instructions cannot be truncated away.
- [ ] RAG/memory/history have bounded allocations.
- [ ] Long chats compact/summarize safely.
- [ ] Token usage is observable.
- [ ] Oversized tool results are bounded.

## 8. GUI

- [ ] React + TypeScript + Vite frontend starts independently.
- [ ] Chat is usable and responsive.
- [ ] Error/loading/streaming states exist.
- [ ] Source citations are visible.
- [ ] Tool execution is visible.
- [ ] Risk/confirmation reason is visible.
- [ ] System dependency health is visible.
- [ ] Basic keyboard/accessibility behavior is tested.
- [ ] Layout works at desktop and smaller widths.
- [ ] Unicode works; architecture does not block future Urdu/RTL support.
- [ ] HUD design tokens are centralized; feature components do not hard-code visual constants everywhere.
- [ ] Command Center and Focus layouts use the same backend/domain state rather than duplicated business logic.
- [ ] `JarvisCore` exposes semantic text state in addition to animation.
- [ ] `prefers-reduced-motion` is honored.
- [ ] API/UI feature tests can run using MSW or an equivalent local mock transport.
- [ ] Important HUD components can render in isolation with deterministic mock data.
- [ ] Playwright/equivalent visual baselines exist for the selected high-value screens when the GUI stabilizes.
- [ ] Visual regression tests freeze time/data and disable nondeterministic animation.
- [ ] Browser components never call Jenkins/Grafana/Spinnaker directly; operational access remains backend-side.
- [ ] The HUD remains usable when one or more optional dependencies are degraded.

## 9. Dependency Health

- [ ] `/health/live` works.
- [ ] `/health/ready` works.
- [ ] Database health is separate.
- [ ] Ollama health is separate.
- [ ] Vector-store health is separate.
- [ ] Optional integrations can be DEGRADED/NOT_CONFIGURED without falsely killing core readiness.

## 10. CI Quality Gate

Run or have Amazon Q run the project's equivalent commands. Typical shape:

```bash
# backend
pytest
ruff check .
mypy app
pip-audit

# frontend
cd frontend
npm test
npm run lint
npm run typecheck
npm run build
```

Use the actual scripts chosen by the repository; do not blindly add duplicate tooling.

Verify:

- [ ] Unit tests pass.
- [ ] Integration tests pass.
- [ ] Contract/schema tests pass.
- [ ] Security tests pass.
- [ ] Frontend tests pass.
- [ ] Lint passes.
- [ ] Type checking passes.
- [ ] Dependency audit has no unreviewed critical findings.
- [ ] Coverage report is generated.

## 11. Failure Injection

For each external dependency, ask:

> What happens if this dependency is slow, unavailable, malformed, unauthorized or returns partial data? Show the test proving JARVIS fails safely.

- [ ] Ollama failure tested.
- [ ] DB failure/lock tested where relevant.
- [ ] Vector-store failure tested.
- [ ] Kubernetes 401/403/500/timeout tested when introduced.
- [ ] Prometheus malformed/timeout tested when introduced.
- [ ] Jenkins 401/403/timeout/malformed response tested when introduced.
- [ ] Grafana 401/403/timeout/missing dashboard tested when introduced.
- [ ] Spinnaker 401/403/timeout/malformed execution tested when introduced.
- [ ] OS file-open failure and denied path tested when introduced.
- [ ] Scheduler retry/restart tested when introduced.
- [ ] No failure path fabricates a successful result.


## 12. CI/CD & Local File Operations Review

When Phase 7 or filesystem opening is implemented, verify:

- [ ] Jenkins adapter can query jobs/builds without browser scraping as the primary method.
- [ ] Jenkins can compute deterministic stats such as recent success rate and duration.
- [ ] Jenkins console output is bounded/sanitized before entering LLM context.
- [ ] Grafana dashboard lookup/opening uses configured trusted instances.
- [ ] Metric claims come from an actual metrics/data API, not inferred from a URL or screenshot.
- [ ] Spinnaker adapter can query pipeline executions and stage status/duration.
- [ ] Cross-system answers retain source URLs/IDs and timestamps.
- [ ] Read-only adapters cannot trigger/retry/cancel jobs in their initial phase.
- [ ] File access is based on explicitly granted roots.
- [ ] Revoking a root immediately prevents later open/read/search operations.
- [ ] Ambiguous file matches are shown to the user rather than opened by guess.
- [ ] Opening a file is separate from indexing/reading it.
- [ ] Unit tests do not launch a real browser, Jenkins, Grafana, Spinnaker or OS application.

Use this focused review prompt:

```text
Perform a READ-ONLY review of the Jenkins, Grafana, Spinnaker and local-file modules.

For each module show:
1. public interface/tools
2. configured trust boundary (server origins or filesystem roots)
3. fake/mock implementation
4. happy-path tests
5. auth/permission failure tests
6. timeout/malformed-data tests
7. URL/path validation tests
8. exact provenance returned to the GUI
9. whether any state-changing operation is possible

Then prove that ordinary unit/CI tests contact no real Jenkins, Grafana, Spinnaker, browser or private filesystem path.
Do not modify code during this review.
```


## 13. HUD GUI Review

When the GUI shell or Operations Command Center is implemented, run this read-only review:

```text
Perform a READ-ONLY HUD GUI review. Do not modify code.

Compare the current frontend against Sections 81-84 of JARVIS_MASTER_SPEC.md.

Report:
1. design-token implementation
2. component boundaries for JarvisCore/HudPanel/gauges/status/tool cards
3. Command Center vs Focus mode architecture
4. API mocking strategy and available deterministic mock scenarios
5. component tests and counts
6. Playwright/E2E/visual regression coverage
7. reduced-motion/accessibility behavior
8. responsive behavior at desktop/laptop/tablet/mobile widths
9. rendering/performance risks
10. any place frontend code directly contacts operational systems
11. screenshots or local test artifacts produced by the repository, if any
12. known visual/interaction gaps

Do not claim a movie-style appearance is complete merely because colors resemble the reference. Judge usability, hierarchy, responsiveness, accessibility and operational clarity.
```

## 13. Phase Exit Review Prompt for Amazon Q

Paste this at the end of every phase:

```text
Perform a READ-ONLY phase readiness review. Do not modify code yet.

Compare the current repository against JARVIS_MASTER_SPEC.md and JARVIS_READINESS_CHECKLIST.md.

For every implemented module report:
1. purpose and public interface
2. dependencies
3. mocks/fakes/stubs available
4. happy-path tests
5. failure-path tests
6. boundary/security tests
7. integration tests
8. known untested risks

Then run the existing test, lint, type-check, dependency-audit, frontend-test and build commands.

Report exact pass/fail counts and coverage.

Check for:
- hard-coded secrets
- unsafe network exposure
- missing policy checks
- unbounded LLM/tool calls
- missing context limits
- schema/index versioning problems
- API contract drift
- skipped tests
- TODOs in claimed-complete functionality

Do not fix anything during this review.
Give me a prioritized gap list: BLOCKER, HIGH, MEDIUM, LOW.
Finish with READY FOR NEXT PHASE: YES or NO and explain the gating failures.
```

## 14. Rule of Thumb

A convincing demo is not the same as a completed phase.

For JARVIS, completion means:

**works + fails safely + is testable + is observable + is recoverable + does not bypass policy.**

## 15. Voice Architecture Review

When any Phase 5 voice capability is implemented, verify:

- [ ] Push-to-talk works before wake-word mode is relied on.
- [ ] STT and speaker verification are separate interfaces.
- [ ] VoiceSessionManager owns lifecycle/state transitions.
- [ ] Domain vocabulary is editable and tested.
- [ ] Ambiguous STT normalization does not silently invent technical terms.
- [ ] FakeAudioInputProvider exists.
- [ ] FakeWakeWordProvider exists when wake-word support is implemented.
- [ ] FakeSpeakerVerificationProvider exists when enrollment is implemented.
- [ ] FakeSTT and FakeTTS providers exist.
- [ ] Unit/CI tests require no real microphone, speaker, user voice, GPU, or cloud API.
- [ ] Raw enrollment audio is not logged.
- [ ] Speaker embeddings are excluded from RAG and source control.
- [ ] Speaker profiles are versioned and deletable.
- [ ] Wake-word always-listening mode is OFF by default.
- [ ] Microphone/listening state is visible in the UI.
- [ ] Voice identity alone cannot approve SENSITIVE/DANGEROUS operations.
- [ ] Exact confirmation integrity remains enforced for voice-initiated tools.
- [ ] Barge-in/interrupt behavior has deterministic tests.
- [ ] ActiveUIContext is compact, structured, and cannot bypass policy.

Use this focused review prompt:

```text
Perform a READ-ONLY review of the JARVIS voice implementation. Do not modify code.

Compare it against Sections 85-94 of JARVIS_MASTER_SPEC.md and JARVIS_VOICE_DESIGN_BRIEF.md.

Report:
1. voice interfaces and implementations
2. push-to-talk lifecycle
3. wake-word lifecycle if present
4. speaker enrollment/verification if present
5. domain-vocabulary strategy
6. VoiceSessionManager states
7. barge-in/cancel behavior
8. GUI voice-state integration
9. security boundaries and voice modes
10. handling/storage/deletion of speaker-profile data
11. mocks/fakes available
12. unit/integration/E2E test counts
13. failure-injection coverage
14. whether any unit/CI test requires real audio hardware or personal voice data
15. known privacy/security/latency risks

Do not fix anything during the review. Finish with READY FOR VOICE PHASE EXIT: YES or NO.
```

# Runtime / Web / Tracing / Watcher Readiness Addendum

Use these checks during the relevant phase exit review.

## Runtime Mode
- [ ] Native Local Mode works without Docker.
- [ ] `.venv` instructions were executed from a clean shell successfully.
- [ ] SQLite/local vector storage works with no external DB/vector daemon.
- [ ] Containerized Mode, if present, is optional and does not become a hidden prerequisite.
- [ ] Runtime-profile-specific wiring is isolated in bootstrap/configuration code.

## Model Capability Probing
- [ ] Active Ollama/model capability probing is implemented behind the LLM provider abstraction.
- [ ] ContextBuilder uses provider/model capability data when valid.
- [ ] Safe fallback behavior is tested when model metadata is missing or malformed.
- [ ] Context budget changes correctly after switching models.

## OpenTelemetry
- [ ] Request/orchestrator/tool spans can be emitted when tracing is enabled.
- [ ] Trace hierarchy shows tool fan-out/sub-task structure.
- [ ] Token/latency/error attributes are available where supported.
- [ ] Trace attributes are sanitized.
- [ ] No prompts, document bodies, secrets, raw voice audio, speaker embeddings, or hidden chain-of-thought are exported by default.
- [ ] JARVIS still works when no telemetry collector is configured.

## Inbox Watcher
- [ ] File events are debounced.
- [ ] Incomplete file copies are not parsed prematurely.
- [ ] Stable files reach the canonical ingestion pipeline.
- [ ] Duplicate hashes are skipped correctly.
- [ ] Modified files update safely.
- [ ] Temporary files are ignored.
- [ ] Parser failure does not terminate the watcher.
- [ ] Watch roots are explicitly configured and limited.
- [ ] Watcher tests use fake events/temp directories.

## Local Web Hardening
- [ ] Backend defaults to `127.0.0.1`.
- [ ] Exact allowed frontend origins are configured.
- [ ] Wildcard CORS is not enabled for privileged APIs.
- [ ] Unapproved origins are rejected in tests.
- [ ] Authentication mode and corresponding CSRF strategy are documented.
- [ ] Cookie-auth state changes require valid CSRF protection.
- [ ] Origin/Host checks are covered where applicable.
- [ ] Browser security checks cannot bypass PolicyEngine confirmation or tool permissions.

## Frontend Reactive State
- [ ] A lightweight state manager such as Zustand is used for cross-cutting UI/HUD state.
- [ ] Server-authoritative security state is not trusted from the client store.
- [ ] Streaming events update state deterministically.
- [ ] Stale/out-of-order events are tested.
- [ ] Tool, voice, health, and approval state transitions have mock tests.
- [ ] No deep prop-drilling is used for global real-time state.



## Location / Trusted-Person Module Readiness

Before declaring any location module complete, verify:

- [ ] no dependency on undocumented Google Maps Location Sharing endpoints
- [ ] no browser session-cookie scraping
- [ ] `LocationProvider` is abstracted and mockable
- [ ] consent/revocation is modeled per person/device
- [ ] fresh vs stale location is explicit
- [ ] stale data is never phrased as definitely current
- [ ] exact/approximate disclosure policies are tested
- [ ] guest/untrusted client cannot retrieve protected family location
- [ ] raw location history is excluded from normal RAG indexing
- [ ] history is OFF by default unless explicitly enabled
- [ ] retained history can be purged
- [ ] reverse-geocode failure does not invent a location name
- [ ] geofence events are deterministic and tested for jitter/debounce
- [ ] all unit tests use synthetic coordinates and fake providers
- [ ] optional real-provider smoke tests are isolated and never required in CI


## Kiro / External Agent Readiness

Before declaring Kiro integration complete, verify:

- [ ] Kiro is integrated through official ACP (`kiro-cli acp`) rather than an unverified MCP wrapper.
- [ ] MCP and ACP configurations are kept separate.
- [ ] ACP initialize/capability negotiation is tested.
- [ ] Kiro session create/load/cancel are tested.
- [ ] workspace path must pass JARVIS allowlist policy before launch.
- [ ] Kiro running as the host user is not described or treated as sandboxed.
- [ ] default Kiro delegated mode is read-only.
- [ ] write/refactor operations enter JARVIS policy/confirmation flow.
- [ ] broad `--trust-all-tools` is not used for normal JARVIS sessions.
- [ ] inherited environment variables are minimized/allowlisted.
- [ ] Kiro auth state is checked through supported CLI status, not by reading Kiro token files.
- [ ] missing/unauthed/crashed Kiro does not break core JARVIS startup.
- [ ] stdout protocol and stderr diagnostic streams are handled separately.
- [ ] cancellation, timeout, crash and process cleanup are tested.
- [ ] external-agent telemetry is sanitized.
- [ ] normal CI uses fake ACP/Kiro components.
- [ ] optional real-Kiro smoke tests are isolated behind an explicit flag.
- [ ] Kiro terms/product-usage authorization for the intended JARVIS workflow has been reviewed before enabling live delegation.

## Architecture Proposal Review Gate

For every significant new capability, record:
- [ ] ACCEPT / ACCEPT WITH MODIFICATION / DEFER / REJECT
- [ ] what existing JARVIS capability overlaps with it
- [ ] why it improves or fails to improve the existing design
- [ ] security/privacy impact
- [ ] runtime/dependency cost
- [ ] mock/failure-test plan
- [ ] phase placement
- [ ] ADR required: YES/NO


## 18. Chief Architect Baseline / Scope-Freeze Gate

Before Phase 0 begins or before accepting a large Phase 0 change set:

- [ ] `JARVIS_ARCHITECT_APPROVAL.md` has been read.
- [ ] Section 123 of `JARVIS_MASTER_SPEC.md` is treated as the initial-build override.
- [ ] v0.1 is understood as Phases 0–2 only.
- [ ] Phase 0 does not include RAG implementation, memory, voice, DevOps adapters, automation, location, MCP or Kiro.
- [ ] No empty placeholder packages were generated for future phases.
- [ ] Python 3.12 + `.venv` native runtime is the primary path.
- [ ] SQLite/SQLAlchemy/Alembic foundation is established without requiring external DB services.
- [ ] request/correlation IDs exist from the beginning.
- [ ] browser event contract has sequence/request identity when streaming is introduced.
- [ ] production-style local UI path is same-origin where practical; Vite cross-origin is dev-only and explicitly allowed.
- [ ] a default workspace/domain concept exists without creating separate databases per workspace.
- [ ] OpenTelemetry/exporter infrastructure is not made a mandatory runtime dependency.
- [ ] Docker, Redis/Celery/Kafka and microservices are not required.

A scope-freeze violation is a **HIGH** issue unless it fixes a security/data-loss blocker.
