# JARVIS Security Model

## Threat model (v0.1)

v0.1 protects against:
- accidental network exposure (loopback-only binding)
- hostile web-origin calls (explicit CORS allow-list)
- prompt injection from retrieved document content
- unsafe file access (FileAccessRegistry — Phase 4)
- application mistakes and misconfiguration

v0.1 does **not** claim to protect against malware already executing as the same OS user.

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

## Tool permissions (Phase 4+)

Actions are classified as READ_ONLY / LOW_RISK / SENSITIVE / DANGEROUS.
- SENSITIVE actions require explicit confirmation
- DANGEROUS actions always require explicit confirmation
- The LLM proposes actions; deterministic PolicyEngine code decides whether they are allowed
- Confirmation is bound to exact tool + exact parameters + expiry time

## Filesystem access (Phase 4+)

- FileAccessRegistry grants/revokes named roots explicitly
- No unrestricted filesystem access by default
- Path traversal attacks are prevented by normalising paths before permission checks
- Symlinks outside permitted roots are not followed

## Audit logging (Phase 4+)

Every tool execution will be logged with: timestamp, tool, sanitised parameters,
risk level, policy version, matched rule, decision, confirmation result, duration.
Secrets are never included in audit logs.

## Supply chain

- Dependencies are pinned in `pyproject.toml`
- `pip-audit` is available for vulnerability scanning: `python -m pip_audit`
- Dependencies are reviewed before addition (see coding rules)
