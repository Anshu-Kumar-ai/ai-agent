# Hermes AI Agent

A general-purpose PC automation AI agent with planning, memory, tool execution, evaluation-driven improvement, and multi-provider LLM routing.

## Features

- **Multi-Provider LLM Routing**: Gemini, Groq, OpenRouter, Local (Ollama) with health-aware priority
- **Structured Planning**: LLM-based planner with JSON schema validation
- **Bounded Agent Loop**: Plan → Act → Observe → Evaluate → Retry (max 3 steps, 2 retries)
- **Sophisticated Evaluation**: 6 weighted criteria (hallucination, completeness, relevance, tool success, etc.)
- **Evaluation-Driven Retry**: Automatic retry with feedback when score < 0.7
- **Filesystem Tools**: Read, write, move, list files with sandboxed paths
- **Terminal Tool**: Execute shell commands with timeout and sandbox
- **Enhanced Memory**: Observations, skills, reflections, evaluations, attempt tracking
- **Permission System**: Risk-based (LOW/MEDIUM/HIGH/CRITICAL) with scoped permissions
- **Verifier Authority**: FileContentVerifier as sole completion authority
- **Persistence**: JSON save/load for full state recovery
- **Multi-Provider Failover**: Automatic fallback on provider failure

## Architecture

```
User Request
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                         Agent                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  SmartRouter (Gemini, Groq, OpenRouter, Local/Ollama)   │    │
│  │  - Health-aware priority with EMA scoring               │    │
│  │  - Cooldown on failures, persistent stats               │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                      │
│                           ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  LLMPlanner / Planner                                   │    │
│  │  - LLM-based with JSON schema validation                │    │
│  │  - Keyword-based fallback                               │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                      │
│                           ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  AgentLoop (max_steps=3, max_retries=2)                 │    │
│  │  - Plan → Act → Observe → Evaluate → Retry              │    │
│  │  - Evaluator integration (6 criteria)                   │    │
│  │  - PermissionManager gating                             │    │
│  │  - Automatic reflection & retry                         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                      │
│                           ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  ToolExecutor + ToolRegistry (7 tools)                  │    │
│  │  - calculator, time_tool                                │    │
│  │  - fs.read, fs.write, fs.move, fs.list                  │    │
│  │  - terminal.run                                         │    │
│  └─────────────────────────────────────────────────────────┘    │
│                           │                                      │
│                           ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  EnhancedMemory                                         │    │
│  │  - Conversation history (rolling window)                │    │
│  │  - Tool observations, skills, reflections               │    │
│  │  - Evaluations, attempt tracking, comparison            │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites
- Python 3.11+
- API keys for at least one LLM provider (set in `.env`)

### Installation
```bash
# Clone the repository
git clone <repository-url>
cd AI-Agent

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
# Or install with dev dependencies
pip install -e ".[dev]"
```

### Configuration
Create `.env` file:
```env
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=openrouter/free
HERMES_WORKSPACE=C:\path\to\workspace  # Optional
```

### Running Tests
```bash
# Run all tests
python -m pytest tests/ -v

# Run unit tests only (mocked LLM providers, no API keys needed)
python -m pytest tests/ -v -m "not integration"

# Run integration tests (requires API keys)
python -m pytest tests/ -v -m "integration"

# Run specific test file
python -m pytest tests/test_agent_enhanced_memory.py -v
```

### Code Quality Checks
```bash
# Run linting
ruff check app/ tests/

# Auto-fix linting issues
ruff check app/ tests/ --fix

# Format code
ruff format app/ tests/

# Type checking
mypy app/

# Security scan
bandit -r app/
safety check -r requirements.txt
```

### Running the Agent
```python
from app.core.agent import Agent

agent = Agent()
response = agent.run("List files in current directory")
print(response)

response = agent.run("Create a file at test.txt with content 'Hello World'")
print(response)

response = agent.run("What is 25 * 4 + 10?")
print(response)
```

### CLI/REPL Interface
```bash
# Interactive REPL
python -m app.cli

# With FULL_AUTO mode
python -m app.cli --mode FULL_AUTO

# Single message
python -m app.cli --message "What is 2+2?"

# Load previous session
python -m app.cli --load session.json
```

### CI/CD Pipeline
This project uses GitHub Actions for continuous integration:

- **CI Workflow** (`.github/workflows/ci.yml`): Runs on every push/PR
  - Unit tests on Python 3.11 & 3.12 (with mocked LLM providers)
  - Linting with ruff
  - Type checking with mypy
  - Security scanning with bandit & safety
  - Package building and verification

- **Integration Tests** (`.github/workflows/integration.yml`): Runs on demand or weekly
  - Real provider tests using GitHub Secrets
  - Smoke, full, or provider-specific test suites
  - Scheduled weekly runs for all providers

- **Release Workflow** (`.github/workflows/release.yml`): On version tags
  - Automated PyPI publishing
  - GitHub Release creation

To run integration tests locally:
```bash
# Set environment variables
export GEMINI_API_KEY=your_key
export GROQ_API_KEY=your_key
export OPENROUTER_API_KEY=your_key

# Run integration tests
MOCK_LLM_PROVIDERS=false python -m pytest tests/ -m integration -v
```

### Pre-commit Hooks
```bash
# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Run manually
pre-commit run --all-files
```

## Tools

## Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `calculator` | Safe arithmetic evaluation | `expression: string` |
| `time` | Current ISO timestamp | (none) |
| `fs.read` | Read text file | `path: string` |
| `fs.write` | Write file (creates dirs) | `path: string, content: string` |
| `fs.move` | Move/rename file | `src: string, dst: string` |
| `fs.list` | List directory | `path?: string` |
| `terminal.run` | Execute shell command | `cmd: string|array, timeout?: number` |

## Evaluation System

The agent evaluates its own responses using 6 weighted criteria:

| Criterion | Weight | Description |
|-----------|--------|-------------|
| `tool_executions_successful` | 2.0x | Tools executed without errors |
| `no_hallucination` | 2.0x | Tool results faithfully represented |
| `response_addresses_request` | 1.5x | Response addresses user query |
| `complete_response` | 1.5x | Multi-part requests fully addressed |
| `non_empty_response` | 1.0x | Response not empty |
| `appropriate_tools_used` | 1.0x | Right tools for the task |

**Threshold**: 0.7 (configurable)  
**Retries**: 2 (configurable) with feedback injection

## Permission System

Risk-based permission model:

| Risk Level | Examples | Behavior |
|------------|----------|----------|
| LOW | calculator, time, fs.read, fs.list | Auto-allowed |
| MEDIUM | fs.write (in workspace) | Approval required (BALANCED) |
| HIGH | fs.move, fs.delete, terminal.run | Always requires approval |
| CRITICAL | System operations | Always blocked |

**Approval Modes**: SAFE, BALANCED (default), AUTONOMOUS, FULL_AUTO

## Project Structure

```
AI-Agent/
├── app/
│   ├── core/              # Core agent components
│   │   ├── agent.py
│   │   ├── agent_loop.py
│   │   ├── evaluator.py
│   │   ├── planner.py
│   │   ├── llm_planner.py
│   │   ├── router.py
│   │   ├── gateway.py
│   │   ├── permissions.py
│   │   └── state/         # Action, Observation, AgentState, etc.
│   ├── memory/            # EnhancedMemory, ConversationMemory
│   ├── tools/             # Tool implementations
│   │   ├── adapters.py    # pc_agent tool adapters
│   │   ├── calculator.py
│   │   ├── time_tool.py
│   │   ├── filesystem.py
│   │   ├── terminal_tools.py
│   │   └── ...
│   ├── memory/            # EnhancedMemory
│   ├── evaluator/         # Base + Default evaluator
│   ├── planner/           # LLM + Stub planners
│   ├── reflector/         # LLM + Stub reflectors
│   ├── verifier/          # FileContentVerifier
│   ├── persistence/       # JSON persistence
│   ├── llm/               # Multi-provider LLM
│   └── goal_manager.py
├── tests/                 # 67 tests (all passing)
├── data/                  # Provider stats
├── CHECKPOINT_STAGE_*.md  # Milestone documentation
├── .env                   # API keys (not committed)
├── .gitignore
├── requirements.txt
└── README.md
``` 

## Milestones

| Stage | Description | Status |
|-------|-------------|--------|
| 1 | Generic Tool Interface | ✅ |
| 2 | Agent Loop | ✅ |
| 3 | Metadata Planning | ✅ |
| 4 | Boundary Contracts | ✅ |
| 5 | LLM Planning | ✅ |
| 6 | Memory, Skills, Reflection | ✅ |
| 7 | Enhanced Memory Wired | ✅ |
| 8 | Evaluation-Driven Retry | ✅ |
| 9 | GitHub Organization + CI/CD | ✅ |

## CI/CD Pipeline Details

### GitHub Actions Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | Push/PR to main/master | Unit tests, linting, type checking, security scan, build |
| `integration.yml` | Manual dispatch, weekly schedule, PR label | Real provider integration tests |
| `release.yml` | Version tags (v*) | Build, verify, publish to PyPI, create GitHub Release |

### Branch Protection Recommendations

These settings should be configured in GitHub repository settings (requires admin access):

```
Branch: main
- Require pull request reviews before merging
  - Require 1 approval
  - Dismiss stale reviews when new commits are pushed
- Require status checks to pass before merging
  - Required checks: test (3.11), test (3.12), lint, security, build
- Require branches to be up to date before merging
- Require linear history
- Do not allow force pushes
- Do not allow deletions
```

### Release Automation

Releases are automated via the `release.yml` workflow:

1. Push a version tag: `git tag v0.1.0 && git push origin v0.1.0`
2. Workflow automatically:
   - Builds and verifies the package
   - Creates GitHub Release with auto-generated notes
   - Publishes to PyPI (if public repo and PYPI_API_TOKEN secret configured)
   - Creates GitHub Release with artifacts

### Required GitHub Secrets

For full CI/CD functionality, configure these secrets in GitHub repository settings:

| Secret | Required For | Description |
|--------|--------------|-------------|
| `GEMINI_API_KEY` | Integration tests | Google Gemini API key |
| `GROQ_API_KEY` | Integration tests | Groq API key |
| `OPENROUTER_API_KEY` | Integration tests | OpenRouter API key |
| `OPENROUTER_MODEL` | Integration tests | OpenRouter model name (e.g., `openrouter/free`) |
| `PYPI_API_TOKEN` | Release workflow | PyPI API token for publishing |
| `GITHUB_TOKEN` | Release workflow | Automatically provided by GitHub |

## License