# Security Policy

Note that your author is *not* a security expert. I have tried to implement some basic sanity in this project, but you should probably review this carefully.

## Threat Model

Shesha executes LLM-generated code in Docker containers. The primary threats are:

1. **Prompt Injection**: Malicious content in documents attempting to manipulate the LLM
2. **Sandbox Escape**: Code attempting to break out of the container
3. **Data Exfiltration**: Attempts to send document data to external servers
4. **Resource Exhaustion**: Code consuming excessive CPU/memory

## Defense Layers

### 1. Prompt Injection Mitigation

- **Untrusted Content Tags**: Two patterns used:
  - `<untrusted_document_content>` wraps content in sub-LLM calls via `llm_query()`
  - `<repl_output type="untrusted_document_content">` wraps REPL execution output shown to the main LLM
- **Hardened System Prompt**: Explicit warnings about adversarial content
- **Instruction/Content Separation**: `llm_query(instruction, content)` keeps trusted instructions separate from untrusted document data
- **Adversarial Testing**: Test suite covers tag injection, instruction override attempts, nested tags, and special character handling

### 2. Docker Sandbox

- **Network Isolation**: Containers have no network access by default
- **Resource Limits**: Memory (512MB) and CPU (1 core) limits enforced
- **Execution Timeout**: 30-second timeout per code execution
- **Non-root User**: Code runs as unprivileged `sandbox` user
- **Read-only Filesystem**: No persistent writes allowed
- **Capabilities Dropped**: All Linux capabilities dropped (`--cap-drop=ALL`)
- **No Privilege Escalation**: `no-new-privileges` security option prevents setuid binaries

### 3. Network Policy (When Enabled)

If network access is required for sub-LLM calls:
- **Egress Whitelist**: Only allowed to LLM API endpoints
- **No Inbound**: No incoming connections allowed

### 4. Path Traversal Protection

- **Safe Path Resolution**: All user-provided paths are resolved and validated against base directories using `safe_path()`
- **Nested Paths Allowed**: Document names like "src/main.py" are permitted and create nested directories
- **Escape Detection**: Raises `PathTraversalError` if resolved path escapes the allowed directory (e.g., "../" attempts)
- **Covers All Storage Operations**: Projects, documents, raw files, and repository directories
- **Optional Flattening**: `sanitize_filename()` is available for cases requiring flat filenames (replaces separators with underscores)

### 5. Secret Redaction

- **Trace Redaction**: Execution traces can be redacted before logging or display via `trace.redacted()`
- **Pattern Matching**: Detects common secret patterns (API keys, bearer tokens, AWS credentials, private keys)
- **Configurable**: Custom patterns can be added via `RedactionConfig`

### 6. Protocol Limits

The container communication protocol enforces limits to prevent resource exhaustion:

| Limit | Value | Purpose |
|-------|-------|---------|
| Max buffer size | 10 MB | Prevents memory exhaustion from large outputs |
| Max line length | 1 MB | Prevents oversized JSON messages |
| Max read duration | 5 min | Overall deadline prevents hanging |

When limits are exceeded, the container is terminated and an error is returned.

## Configuration

Security-relevant settings in `SheshaConfig`:

| Setting | Default | Description |
|---------|---------|-------------|
| `container_memory_mb` | 512 | Memory limit per container |
| `execution_timeout_sec` | 30 | Max execution time per code block |
| `max_output_chars` | 50000 | Truncate large outputs |
| `allowed_hosts` | LLM APIs only | Network egress whitelist |
| `cap_drop` | `["ALL"]` | Linux capabilities to drop |
| `security_opt` | `["no-new-privileges:true"]` | Docker security options |

## Disclaimer

Shesha provides defense-in-depth but cannot guarantee perfect isolation. Do not process highly sensitive documents without additional security review.
