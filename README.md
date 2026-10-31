# ✈️ TripWeaver AI

> A multi-agent AI travel planner. Describe a trip in plain English and get real flight options, hotels, weather, a budget check and a day-by-day itinerary, with a human approval step before the final plan.

![Python](https://img.shields.io/badge/python-3.12-blue)
![LangGraph](https://img.shields.io/badge/LangGraph-multi--agent-green)
![Claude](https://img.shields.io/badge/LLM-Claude-orange)
![FastAPI](https://img.shields.io/badge/API-FastAPI-009688)
![Postgres](https://img.shields.io/badge/state-PostgreSQL-336791)

**Try asking:**

- `Plan a 7 day Japan trip from Delhi under 2 lakhs`
- `Find flights from Dubai to San Francisco`
- `Best budget hotels in Bangkok near the BTS`
- `What's the weather like in Paris in March?`

---

## ✨ Features

| | |
|---|---|
| 🧭 **Supervisor + guardrail** | Blocks non-travel requests and picks only the agents a request needs |
| ⚡ **Parallel agents** | Flights, hotels and weather run together; budget and itinerary run together; long itineraries are written in parallel day blocks |
| 🛫 **Real flight options** | Airline, flight number and departure/arrival times from AviationStack |
| 🏨 **Hotels** | Web search through Tavily (MCP) |
| 🌦️ **Weather** | Custom OpenWeather MCP server (current + forecast) |
| 💰 **Budget check** | Flags feasibility and money-saving options |
| ✅ **Human-in-the-loop** | Approve the draft, or request changes with feedback |
| 💾 **Persistent chats** | LangGraph checkpoints stored in PostgreSQL, one `thread_id` per chat |
| 📡 **Streaming** | The flight table, the itinerary (block by block) and the final plan appear while they are written (Server-Sent Events) |
| 🛟 **Graceful fallbacks** | Every external step degrades instead of failing the request: hotels, weather and flights fall back to general suggestions, budget to a short note, the final answer to the approved draft, and parallel itinerary drafting to a single call. Claude calls retry up to 4 times on overload or timeouts |
| 🚦 **Limit fallback** | If an API runs out of quota the page shows a "Token limit exceeded" popup naming the API. Claude limits stop the request; search, flight and weather limits still give a plan with general suggestions |
| ✂️ **Context stripping** | Each model call receives only the data it needs (top hotel results, no URLs, per-step length limits), about half the prompt tokens |
| 📄 **Export** | Copy the plan or download it as a PDF |

---

## 🏗️ How it works

```mermaid
flowchart LR
    U([User request]) --> S{Supervisor<br/>+ guardrail}
    S -- not travel --> B([Blocked])
    S --> F[Flight agent]
    S --> H[Hotel agent]
    S --> W[Weather agent]
    F --> BU[Budget agent]
    H --> BU
    W --> BU
    F --> I[Itinerary draft<br/>parallel day blocks]
    H --> I
    W --> I
    BU --> A{{Human approval}}
    I --> A
    A -- approve / request changes --> FN[Final plan]
    FN --> R([Response])
```

1. The **supervisor** (Claude Haiku) checks that the request is about travel and, at the same time, extracts origin, destination, duration and budget and chooses the agents.
2. **Flight, hotel and weather** agents run in parallel (LangGraph fan-out).
3. The **budget** agent and the **itinerary** agent run in parallel. For trips longer than 4 days the itinerary is written map-reduce style: a quick outline, then blocks of days written at the same time by Claude Sonnet and joined.
4. The graph **pauses** at `interrupt()` so you can approve the draft or send feedback.
5. The **final** agent produces the formatted plan.

<details>
<summary><b>Models used</b></summary>

| Step | Model | Why |
|---|---|---|
| Guardrail, supervisor, flight guidance, budget | `claude-haiku-5-5` | Short outputs, speed matters |
| Itinerary draft | `claude-sonnet-5-5` | Longest, most creative step |
| Final formatting | `claude-haiku-5-5` | Reformats an approved draft |

</details>

---

## 🚀 Quick start

```bash
# 1. Install uv (https://docs.astral.sh/uv/) and clone the repo
uv sync

# 2. Create .env (see below)

# 3. Run
uv run app.py
```

Open <http://localhost:8000>.

<details>
<summary><b>.env settings</b></summary>

```
ANTHROPIC_API_KEY=
TAVILY_API_KEY=
AVIATION_API_KEY=
OPENWEATHER_API_KEY=
DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
DEFAULT_ORIGIN_IATA=DEL        # used when the request names no departure city

# optional, for LangSmith tracing
LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=Trip
```

Never commit this file. Restart the app after changing it.

</details>

<details>
<summary><b>Docker</b></summary>

```bash
docker build -t tripweaver .
docker run --env-file .env -p 8000:8000 tripweaver
```

</details>

### API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Web interface |
| `POST` | `/api/travel` | Start a plan (`message`, optional `thread_id`) |
| `POST` | `/api/travel/approve` | Approve or request changes (`thread_id`, `approved`, `feedback`) |
| `POST` | `/api/travel/stream` | Same as `/api/travel`, streamed as Server-Sent Events |
| `POST` | `/api/travel/approve/stream` | Same as `/api/travel/approve`, streamed |
| `GET` | `/health` | Health check |

---

## 📊 Evaluation

The project has three layers of checks. Run them yourself:

```bash
uv run python -m unittest discover -s tests -t .   # unit tests, offline
uv run python scripts/run_evals.py --offline        # route resolution, no API calls
uv run python scripts/run_evals.py                  # full suite, ~60 Haiku calls
```

The test set lives in [`evals/dataset.json`](evals/dataset.json) and the latest run is saved to `evals/latest_results.json`.

### Results

| Check | What it measures | Score |
|---|---|---|
| Unit tests | Helpers, cache, route parsing, limit detection, context stripping | 31 / 31 pass |
| Route resolution | "from X to Y" turned into the right airport codes | 6 / 6 |
| Guardrail | 12 travel requests allowed, 8 unrelated or harmful ones blocked | 20 / 20 |
| Routing | Right agents chosen (and wrong ones left out) | 5 / 5 |
| Constraint extraction | Origin and destination read correctly | 5 / 5 |

Mean supervisor time per request (guardrail and routing run concurrently, thinking off): **1.6 s**.

### Performance

Measured on one request, "Plan a 7 days Thailand trip from Bangladesh with budget hotels and sightseeing", time until the draft is ready for approval:

| Version | Time to draft |
|---|---|
| Agents run one after another, Sonnet everywhere | ~137 s |
| Parallel data agents + Haiku for cheap steps + direct flight API | ~74 s |
| + guardrail and routing in parallel, budget and itinerary in parallel | ~69 s |
| + itinerary written in parallel day blocks (outline, then blocks) | ~41 s |
| + Haiku thinking off, context stripping | ~30 s |

Each row is a single run, so expect some variation. With streaming, the flight table appears after about 6 s, the first draft text after about 26 s, and the final plan starts appearing about 9 s after you approve. Caching and the faster final-polish model were added along the way and have not been timed separately. The step after approval (final answer) still takes extra time.

### Optimization log

Every change made for speed or robustness, in the order it was done. Times are single runs on one request.

| # | Change | Why | Effect |
|---|---|---|---|
| 1 | Profile each graph node with `stream_mode="updates"` | Find the real bottleneck instead of guessing | Baseline ~137 s to draft |
| 2 | Flight, hotel and weather agents run in parallel (list returned from the routing function, `Annotated[int, operator.add]` on `llm_calls`) | They do not depend on each other | ~137 s to ~100 s |
| 3 | Claude Haiku for the supervisor, flight guidance, budget and final formatting; Sonnet only for the itinerary | Short tasks do not need the larger model | ~74 s |
| 4 | Flights through a direct HTTP call instead of a stdio MCP subprocess; removed the failing airport and airline list calls | Subprocess start-up cost and blocked endpoints | Flight step no longer fails or waits on tools |
| 5 | Current weather and forecast fetched together with `asyncio.gather` | Two sequential MCP sessions | Faster weather step |
| 6 | Guardrail and routing calls run at the same time | Routing does not need the guardrail verdict | Supervisor ~7 s to ~5 s (evals: 3.3 s to 2.2 s) |
| 7 | Budget and itinerary run in parallel | The itinerary no longer waits for the budget text | ~69 s |
| 8 | Itinerary written as map-reduce: Haiku outline, then up to 4 blocks of days written in parallel | One long Sonnet call is limited by output tokens | Itinerary ~47 s to ~23 s; ~41 s to draft |
| 9 | Streaming over Server-Sent Events (flight table, draft blocks, final text) | Show results while they are written | Flight table at ~6 s, first draft text at ~26 s |
| 10 | Shared cache in PostgreSQL with an in-memory layer in front (flights and hotels 6 h, weather 30 min) | Survive restarts, share between workers, save API quota | Flight lookup 3.7 s to 0.5 s on a hit |
| 11 | Connection pool with health check instead of one shared connection | A single connection is a bottleneck and breaks when it drops | More robust |
| 12 | Endpoints are plain `def` so FastAPI runs them in worker threads; removed `nest_asyncio` | Blocking graph calls must not freeze the event loop | One slow plan no longer blocks others |
| 13 | Fallbacks when hotel or weather lookups fail | A search outage or rate limit must not fail the whole plan | Plan still completes with general suggestions |
| 14 | Haiku thinking switched off (`thinking={"type": "disabled"}`) | Adaptive thinking is on by default: hundreds of hidden output tokens per call, and it used up `max_tokens` so the budget answer came back empty | Budget answer works again (0 to ~4.7k characters); one call 9.3 s to 3.6 s in a small test; supervisor 2.2 s to 1.6 s |
| 15 | Context stripping (`tripweaver/context.py`): per-step field lists and length limits, top 3 search results without URLs, junk snippets and empty sections dropped | Send each call only what it needs | Prompt input about 16.6k to 8.0k tokens (character estimate); one real draft run 19.8k to 13.0k input and 12.2k to 9.1k output tokens |
| 16 | Limit fallback: detect quota and rate-limit failures per API and show a popup naming the API | A limit must be visible, and must not fail the whole plan when the API only adds data | Claude limit: clear message, request stops. Tavily, AviationStack or OpenWeather limit: plan still completes |
| 17 | Graceful fallbacks for the Claude steps (budget note, final answer falls back to the approved draft) and `max_retries=4` on all models | A transient Claude failure (overload, timeout, 5xx) should not throw away a nearly finished plan; quota errors still stop the run | Plan completes through partial failures; 3 new unit tests |

### Alternatives considered

| Choice | Alternative | Why not |
|---|---|---|
| Parallel agents in LangGraph | Keep sequential | Same cost, much longer wall-clock time |
| Haiku for short steps | One large model everywhere | Slower and dearer; quality on short tasks is the same (checked by the evals) |
| Direct flight HTTP call | Persistent MCP session | More moving parts for one fixed call; MCP is kept where reuse matters (weather, search) |
| Postgres cache | Redis | No new service and it survives restarts; Redis is the next step at higher traffic (a hit costs about 0.5 s against sub-millisecond) |
| Map-reduce itinerary | Shorter prompt or a smaller model | Cutting output loses detail; a smaller model risks quality (not A/B tested yet) |
| Streaming over SSE | WebSocket or polling | SSE is one-way and simple for text; polling wastes requests |
| Trimming context | Leave prompts as they are | Done. The prompts were small, so the gain is mostly cost (about half the input tokens). Quality was checked by reading a plan before and after, because the evals do not score itineraries |

Not changed on purpose: the weather MCP server (about 6 s cold, not on the critical path and a useful showcase) and merging the two supervisor calls (they already run together).

### What this does not prove

- The test set is small (36 cases), so a perfect score means "no failures found here", not "always correct". Add a case for every bug you find.
- It checks routing and guardrails, **not the quality of itineraries**. Reading the output is still the only check for that.
- Flight times come from the airline's recent daily schedule, not a chosen date, and there are **no real fares** (AviationStack does not provide prices). Fare ranges in the answer are model estimates.
- LLM answers vary between runs, so rerun the suite before trusting a number.

### Ideas to extend it

- LLM-as-judge scoring of itineraries (does the plan respect days, budget and weather?)
- A check that every listed flight number appears in the AviationStack data (hallucination check)
- Latency and cost tracking per node through LangSmith
- Regression run in CI on every pull request

---

## 🗂️ Project structure

```
app.py                       Local dev launcher
tripweaver/
  config.py                  .env loading, SSL certs, database URL
  llm.py                     Claude model instances (Sonnet + Haiku)
  utils.py                   Cache, async runner, JSON/text helpers
  db.py                      Postgres pool + LangGraph checkpointer
  service.py                 run_travel_agent / resume_travel_agent
  agents/                    state, supervisor, flight, hotel, weather,
                             budget, itinerary, approval, final, graph
  services/                  flights.py (AviationStack), mcp_client.py
  mcp_servers/               weather_server.py (OpenWeather, stdio MCP)
  api/                       FastAPI app factory, routes, schemas
  web/                       templates/ and static/ (frontend)
evals/                       dataset.json, latest_results.json
tests/                       Offline unit tests
scripts/                     run_evals.py, list_mcp_tools.py
```

## ⚠️ Known limitations

- Flight data needs an AviationStack plan that includes the live-flights endpoint. Date-specific schedules need a higher plan.
- Hotel and fare information is a guide: always confirm before booking.
- Flight, hotel and weather lookups are cached in PostgreSQL (flights and hotels 6 h, weather 30 min), so they survive restarts. Run `uv run python scripts/prewarm_cache.py` after a deploy to fill the cache for the example prompts; it makes real API calls, so do not run it often.

## 🛣️ Roadmap

- [ ] Let users pick a flight and carry the choice into the plan
- [ ] Real fare data (for example Amadeus)
- [ ] CI pipeline running tests and evals
