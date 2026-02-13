# Shesha arXiv Explorer — Setup Guide

Shesha is a research tool that uses Recursive Language Models to help you explore and query arXiv papers. You add papers to topics, then ask natural language questions. The LLM writes code to explore the documents, runs it in a sandbox, and iterates until it finds an answer.

## Prerequisites

- **Docker** — [docker.com/get-started](https://www.docker.com/get-started/)
- An **LLM API key** — set `SHESHA_API_KEY` as an environment variable
- **Model selection** — set `SHESHA_MODEL` (recommended: `gpt-5-mini` for OpenAI)

## Quick Start

```bash
# 1. Clone the repository
git clone https://github.com/your-org/shesha.git
cd shesha/arxiv-explorer

# 2. Set your API key and model
export SHESHA_API_KEY="sk-..."
export SHESHA_MODEL="gpt-5-mini"   # recommended: inexpensive with great results

# 3. Run
docker compose up
```

Visit `http://localhost:8000` in your browser.

## First Research Session

1. **Create a topic** — Click the `+` button in the left sidebar and name it (e.g., "Abiogenesis")
2. **Search for papers** — Click the search icon in the header and search arXiv (e.g., "origin of life RNA world")
3. **Add papers** — Select papers from the results and click "Add". Papers download in the background (there's a 3-second delay between downloads to respect arXiv's rate limits)
4. **Ask a question** — Once papers appear as chips above the chat area, type a question like "What are the main theories for the origin of life?"
5. **Wait for the answer** — The status bar shows the current phase and token count. Queries typically take 1-3 minutes
6. **Inspect the trace** — Click "View trace" on any answer to see the LLM's step-by-step reasoning
7. **Check citations** — Click the checkmark icon in the header to verify the LLM's citations against the source documents

## Troubleshooting

**Docker not running**
Shesha needs Docker to run code in a sandbox. Start Docker Desktop or the Docker daemon.

**API key not set**
Set `SHESHA_API_KEY` as an environment variable before running.

**Papers fail to download**
arXiv may be temporarily unavailable. Wait a minute and try again. Some papers with non-standard formats may fail to parse.

**Context budget at 80%+**
Your documents and conversation history are approaching the model's context limit. Consider clearing the conversation history or switching to a model with a larger context window.

**Port already in use**
Use `--port 8080` (or another port) if 8000 is taken.

## Notice

This is **experimental software**. The web interface is under active development. Some features may be incomplete or change without notice.
