# py-web-testing

[![Python](https://img.shields.io/badge/Python-3.13+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![uv](https://img.shields.io/badge/uv-package%20manager-DE5FE9?logo=uv&logoColor=white)](https://docs.astral.sh/uv/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![browser-use](https://img.shields.io/badge/browser--use-0.13.10-blue)](https://github.com/browser-use/browser-use)

An LLM-driven **web UI testing framework** built on [browser-use](https://github.com/browser-use/browser-use). It turns plain-language test steps into automated browser sessions, and — most importantly — **learns from every successful run** so the same controls are located correctly on the first try, without LLM trial-and-error.

> Designed for large enterprise admin consoles (dozens of top-level menus, hundreds of pages, 10k+ elements) that are painful to automate with hand-written selectors.

---

## Why this project

Traditional UI automation hard-codes selectors that break the moment the frontend changes. LLM agents can adapt, but they waste tokens re-discovering the same controls on every run.

`py-web-testing` sits in the middle: the LLM explores **once**, the framework **remembers** how each control was operated (as an *element memory*), and subsequent runs **replay** the proven steps directly — faster, cheaper, and deterministic.

---

## Features

- **Element operation memory** — records the successful interaction sequence for every control it touches. On later runs, matching controls are operated via a single `follow_memory` tool call instead of step-by-step exploration.
  - No filtering: even login inputs and simple clicks are remembered.
  - Clean-success runs **skip rewriting** (no churn); a run that hit an error **overwrites** the stale memory with the corrected steps.
- **Deterministic auto-apply** — for tricky framework controls (e.g. Element UI `el-date-range-picker`) that the LLM cannot set reliably, the framework injects the proven JavaScript directly (native value setter + `input` + `Enter`), bypassing the LLM entirely. Date ranges are computed dynamically (e.g. "last 10 days, excluding today"), so memories stay date-agnostic.
- **Popup watchdog** — auto-dismisses custom DOM popups/dialogs/modals (Element UI, Ant Design, …) that browser-use's built-in watchdog ignores.
- **Multi-platform support** — one codebase drives multiple admin consoles (different domains). Memory is sharded per platform, so platforms never cross-contaminate.
- **YAML-driven test cases** — write tests as structured steps (`action` / `target` / `locator` / `params`); no Python needed.
- **Pluggable LLM providers** — DeepSeek and Alibaba Qwen (via DashScope's OpenAI-compatible endpoint) behind a single registry.

---

## How it works

```
                          ┌────────────────────────────────────────────┐
                          │              app.runner                    │
                          │  config → llm → case → task → agent → run   │
                          └──────────────────┬─────────────────────────┘
                                             │
                    ┌────────────────────────┼──────────────────────────┐
                    │                        │                          │
             ┌──────▼──────┐         ┌───────▼────────┐         ┌──────▼──────┐
             │  Element    │         │  Popup         │         │  LLM        │
             │  Memory     │         │  Watchdog      │         │  (DeepSeek/ │
             │  (learn/    │◄───────►│  (auto-dismiss)│         │   Qwen)     │
             │   replay)   │         └────────────────┘         └─────────────┘
             └──────┬──────┘
                    │  sharded by platform + URL path segment
                    ▼
             memory/<platform>/{_common,order,station,...}.json
```

1. **Write** a YAML case describing *what* to do, not *how* to locate elements.
2. **Run** — the runner loads config, builds the LLM, converts the case into a natural-language task, and drives the browser.
3. **Learn** — after a successful run, the history is distilled into element memories.
4. **Replay** — the next run matches the current DOM against memories and executes proven steps directly, with the LLM only filling gaps.

---

## Requirements

- Python **3.13+**
- [uv](https://docs.astral.sh/uv/) for dependency management
- A DeepSeek or Qwen (DashScope) API key
- Playwright browsers (installed by browser-use)

---

## Quick start

```bash
# 1. Clone and install
git clone <your-repo-url>
cd py-web-testing
uv sync

# 2. Configure credentials
cp .env.example .env
#    edit .env and fill in DEEPSEEK_API_KEY (and/or DASHSCOPE_API_KEY)

# 3. Register your platform in config.yaml (host + login_url)

# 4. Run a test case
uv run python -m app.runner cases/manhattan/login_and_query.yaml

# 5. Run unit tests
uv sync --extra dev
uv run pytest
```

---

## Configuration

All settings live in `config.yaml` at the project root.

```yaml
llm:
  provider: deepseek            # deepseek | qwen
  deepseek:
    api_key_env: DEEPSEEK_API_KEY
    base_url: https://api.deepseek.com
    model: deepseek-v4-pro
    temperature: 0.0
  qwen:
    api_key_env: DASHSCOPE_API_KEY
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    model: qwen3-max
    temperature: 0.0

platforms:                       # one entry per admin console
  manhattan:
    host: ${MANHATTAN_HOST}       # injected from .env (see .env.example)
    login_url: ${MANHATTAN_LOGIN_URL}

element_memory:
  enabled: true
  key_mode: flat
  max_memories: 50000
  auto_learn: true
  auto_apply_enabled: true
  date_range_days_back: 10       # "last N days, excluding today" window
  sharding_enabled: true         # split memory per platform + URL segment
  shard_dir: ./memory

popup_watchdog:
  enabled: true
  strategy: aggressive
```

| Key | Meaning |
|-----|---------|
| `llm.provider` | Which provider is active (also controls the API key env var used). |
| `platforms.<alias>.host` | Domain used to **route memory shards** (exact match). |
| `platforms.<alias>.login_url` | Login URL injected into `goto` steps for that platform. |
| `element_memory.sharding_enabled` | Split memory into `memory/<platform>/<segment>.json` (login → `_common.json`). |

### Secrets & environment variables

Sensitive values (domains, accounts, passwords, API keys) are **never hard-coded** in committed files. Both `config.yaml` and `cases/*.yaml` support `${VAR_NAME}` placeholders that are expanded from environment variables at load time.

```bash
cp .env.example .env   # then fill in real values — .env is git-ignored
```

Anything not set stays as a literal `${VAR_NAME}` (no crash), which is a handy way to spot missing configuration.

---

## Writing test cases

Cases are YAML files under `cases/<platform>/<case>.yaml` — one directory per platform (a *case group*).

```yaml
name: Charge order & station list query
description: Query charge orders (last 10 days) and station list (Nanjing)
steps:
  - action: goto
    target: 登录页

  - action: input
    target: 请输入您的账号
    params: { value: "${TEST_ACCOUNT}" }   # injected from .env

  - action: click
    target: 登录按钮
    locator: { id: login }        # locator is optional — memory takes priority

  - action: verify
    target: 登录成功
    params: { expect: "已跳转到后台首页" }

  - action: click
    target: 订单管理

  - action: select_option
    target: 单据时间
    params: { option: "订单创建时间" }

  - action: click
    target: 查询

  - action: conclude
    params:
      text: "用一句话输出本用例是否成功。"
```

### Supported actions

`goto` · `input` · `click` · `select_option` · `hover` · `check` · `verify` · `conclude`

### Element location priority

For every step, the runtime resolves the element in this order:

1. **Memory hit** — a previously learned control matching the current DOM.
2. **Explicit `locator`** — fallback hints in the YAML (placeholder / id / role / class).
3. **LLM on-site location** — final fallback when nothing is known yet.

This means you can write cases with **no selectors at all** — the first run teaches the framework, later runs fly.

---

## Project structure

```
py-web-testing/
├── app/                      # application layer
│   ├── config.py             #   config loading + platform registry
│   ├── llm_factory.py        #   pluggable LLM providers (registry)
│   ├── case_loader.py        #   YAML case loading & validation
│   ├── task_builder.py       #   structured steps → NL task text
│   └── runner.py             #   single entrypoint: python -m app.runner
├── browser_use_ext/          # framework extensions
│   ├── integration.py        #   agent assembly + memory wiring
│   ├── memory/               #   element memory subsystem
│   │   ├── store.py          #     MemoryStore + ShardedMemoryStore
│   │   ├── matcher.py        #     DOM ↔ memory matching
│   │   ├── learner.py        #     distill history → memories
│   │   ├── auto_apply.py     #     deterministic JS injection
│   │   ├── follow_memory.py  #     custom LLM tool
│   │   └── models.py         #     pydantic models
│   └── watchdogs/            #   popup auto-dismissal
├── cases/<platform>/         # YAML test cases (one dir per platform)
├── memory/                   # element memory data (sharded JSON)
├── tests/                    # pytest unit tests (no browser needed)
├── docs/lesson-learned/      # debugging write-ups for tricky controls
├── config.yaml               # global configuration
└── pyproject.toml            # deps + pytest config
```

---

## Testing

Unit tests cover the memory subsystem (store, matcher, learner, shard routing) and require no browser or API key.

```bash
uv sync --extra dev      # first time
uv run pytest            # full run
uv run pytest -v         # verbose
uv run pytest -k sharded # filter by name
```

---

## Design docs & lessons learned

- **OpenSpec changes** under `openspec/changes/` contain proposal / design / specs / tasks for each feature — including the rationale for choosing URL-driven memory sharding over menu-name or single-file approaches.
- **Lessons learned** under `docs/lesson-learned/` document hard-won debugging sessions, e.g. [setting Element UI date-range pickers](docs/lesson-learned/el-date-range-picker-input-enter.md).

---

## License

[MIT](LICENSE)
