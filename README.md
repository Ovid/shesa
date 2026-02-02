# Shesha

**Recursive Language Models for Document Querying**

Shesha implements [Recursive Language Models (RLMs)](https://arxiv.org/abs/2512.24601) - a technique for querying document collections by having an LLM write Python code to explore them in a sandboxed REPL.

## Prerequisites

- Python 3.12+
- Docker (for sandbox execution)
- An LLM API key (Anthropic, OpenAI, or other LiteLLM-supported provider)

## Installation

### From PyPI (when published)

```bash
pip install shesha
```

### From Source

```bash
git clone https://github.com/Ovid/shesha.git
cd shesha
pip install -e ".[dev]"
```

### Build the Sandbox Container

The sandbox container is required for code execution:

```bash
docker build -t shesha-sandbox -f src/shesha/sandbox/Dockerfile src/shesha/sandbox/
```

Verify the build:

```bash
echo '{"action": "ping"}' | docker run -i --rm shesha-sandbox
# Should output: {"status": "ok", "message": "pong"}
```

## Configuration

### Environment Variables

Set your API key and optionally configure other settings:

```bash
export SHESHA_API_KEY="your-api-key-here"
export SHESHA_MODEL="claude-sonnet-4-20250514"  # Default model
export SHESHA_STORAGE_PATH="./shesha_data"      # Where projects are stored
export SHESHA_POOL_SIZE="3"                     # Warm container count
export SHESHA_MAX_ITERATIONS="20"               # Max RLM iterations
```

### Programmatic Configuration

```python
from shesha import Shesha, SheshaConfig

# Option 1: Direct arguments
shesha = Shesha(
    model="claude-sonnet-4-20250514",
    api_key="your-api-key",
    storage_path="./data",
    pool_size=3,
)

# Option 2: Config object
config = SheshaConfig(
    model="gpt-4",
    api_key="your-openai-key",
    max_iterations=30,
)
shesha = Shesha(config=config)

# Option 3: Load from file
config = SheshaConfig.from_file("config.yaml")
shesha = Shesha(config=config)
```

### Config File Format (YAML)

```yaml
model: claude-sonnet-4-20250514
storage_path: ./my_data
pool_size: 5
max_iterations: 25
container_memory_mb: 1024
execution_timeout_sec: 60
```

## Quick Start

```python
from shesha import Shesha

# Initialize (uses SHESHA_API_KEY from environment)
shesha = Shesha(model="claude-sonnet-4-20250514")

# Create a project and upload documents
project = shesha.create_project("research")
project.upload("papers/", recursive=True)
project.upload("notes.md")

# Query the documents
result = project.query("What are the main findings?")
print(result.answer)

# Inspect execution details
print(f"Completed in {result.execution_time:.2f}s")
print(f"Tokens used: {result.token_usage.total_tokens}")

# View the execution trace
for step in result.trace.steps:
    print(f"[{step.type.value}] {step.content[:100]}...")
```

## How It Works

1. **Upload**: Documents are parsed and stored in a project
2. **Query**: Your question is sent to the LLM with a sandboxed Python REPL
3. **Explore**: The LLM writes Python code to analyze documents (available as `context`)
4. **Execute**: Code runs in an isolated Docker container
5. **Iterate**: LLM sees output, writes more code, repeats until confident
6. **Answer**: LLM calls `FINAL("answer")` to return the result

For large documents, the LLM can use `llm_query(instruction, content)` to delegate analysis to a sub-LLM call.

## Supported Document Formats

| Category | Extensions |
|----------|------------|
| Text | `.txt`, `.md`, `.csv` |
| Code | `.py`, `.js`, `.ts`, `.go`, `.rs`, `.java`, `.c`, `.cpp`, `.h`, `.hpp` |
| Documents | `.pdf`, `.docx`, `.html` |

## Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=shesha

# Type checking
mypy src/shesha

# Linting
ruff check src tests

# Format code
ruff format src tests

# Run everything
make all
```

## Project Structure

```
src/shesha/
├── __init__.py          # Public API exports
├── shesha.py            # Main Shesha class
├── project.py           # Project class
├── config.py            # SheshaConfig
├── models.py            # ParsedDocument
├── exceptions.py        # Exception hierarchy
├── storage/             # Document storage backends
├── parser/              # Document parsers
├── llm/                 # LiteLLM wrapper
├── sandbox/             # Docker executor
│   ├── Dockerfile
│   ├── runner.py        # Runs inside container
│   ├── executor.py      # Host-side container management
│   └── pool.py          # Container pool
└── rlm/                 # RLM engine
    ├── engine.py        # Core loop
    ├── prompts.py       # Hardened system prompts
    └── trace.py         # Execution tracing
```

## Security

See [SECURITY.md](SECURITY.md) for details on:
- Threat model
- Prompt injection defenses
- Docker sandbox isolation
- Network policies

## License

MIT - see [LICENSE](LICENSE)

## Author

Curtis "Ovid" Poe
