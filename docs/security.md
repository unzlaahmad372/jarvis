# JARVIS Security Model

**Last updated: Phase 44**

## Threat model

Protects against:
- accidental network exposure (loopback-only binding)
- hostile web-origin calls (explicit CORS allow-list)
- prompt injection from retrieved document content
- unsafe file access (FileAccessRegistry)
- path traversal attacks (path normalisation before permission checks)
- cascading tool failures from missing parameters (planner `_has_required_params` guard)
- application mistakes and misconfiguration

Does **not** claim to protect against malware already executing as the same OS user.

## Local/cloud boundary

- All LLM inference uses local Ollama by default
- `JARVIS_ALLOW_CLOUD=false` and `JARVIS_ENABLE_CLOUD=false` by default
- Cloud processing requires both flags set to `true` and explicit user approval per request
- No data is sent to external services without explicit opt-in

## Network exposure

- FastAPI binds to `127.0.0.1` only by default
- `JARVIS_ENABLE_REMOTE_ACCESS=false` by default
- CORS uses an explicit origin allow-list — no wildcards for privileged APIs
- Remote access is a separate security milestone (Phase 11)

## Secrets handling

- Secrets live in `.env` (gitignored) or environment variables
- `.env.example` documents keys without values — never committed with real secrets
- Secrets are never logged, never placed in prompts, never stored in the vector database
- A separate Vault/Secrets abstraction is planned for Phase 3+

## Prompt injection defense

- Retrieved document content is treated as untrusted DATA, not instructions
- The RAG prompt explicitly separates SYSTEM INSTRUCTIONS / USER QUESTION / RETRIEVED CONTENT
- Tool execution cannot be triggered by content embedded in retrieved documents
- External content (web, email) will also be treated as untrusted when those features are added

## Tool permissions

Actions are classified as READ_ONLY / LOW_RISK / SENSITIVE / DANGEROUS.
- READ_ONLY actions are always permitted
- LOW_RISK actions are auto-permitted by default (`JARVIS_REQUIRE_CONFIRMATION=false`)
- SENSITIVE actions always require explicit confirmation
- DANGEROUS actions always require explicit confirmation — no exceptions
- The LLM proposes actions; deterministic PolicyEngine code decides whether they are allowed
- Confirmation tokens are bound to exact tool + exact parameters + expiry time (ConfirmationStore)
- Confirmation tokens are single-use — consumed on first validation
- The planner skips tools whose required parameters cannot be extracted, preventing cascading audit failures

## Filesystem access

- FileAccessRegistry grants/revokes named roots explicitly
- Default root: `data/` directory only
- Extra roots: `JARVIS_EXTRA_FILE_ROOTS=C:/path1,D:/path2` (comma-separated)
- No unrestricted filesystem access by default
- Path traversal attacks are prevented by normalising paths before permission checks
- Symlinks outside permitted roots are not followed
- `open_file` uses OS default application only — never interprets file content as instructions
- Allowed applications for `open_application`: built-in safe list + `JARVIS_ALLOWED_APPS`

## Audit logging

Every tool execution is logged with: timestamp, tool, sanitised parameters,
risk level, policy version, matched rule, decision, confirmation result, duration.
Secrets are never included in audit logs.
Audit records are retained for `JARVIS_TOOL_LOG_RETENTION_DAYS` (default 90).

## Supply chain

- Dependencies are pinned in `pyproject.toml`
- `pip-audit` is available for vulnerability scanning: `python -m pip_audit`
- Dependencies are reviewed before addition (see coding rules)
