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

# Run specific test file
python -m pytest tests/test_agent_enhanced_memory.py -v
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
| 9 | GitHub Organization + CI/CD | 🔄 Next |

## License

MIT