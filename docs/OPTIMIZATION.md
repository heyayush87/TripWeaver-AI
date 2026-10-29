# Optimization notes

How TripWeaver went from about 137 s to about 41 s to produce a draft, why each change was made, and what was
considered instead. The headline numbers are in the [README](../README.md#-evaluation). Times here are single runs
of one request ("Plan a 7 days Thailand trip from Bangladesh with budget hotels and sightseeing"), so expect variation.

## Method

1. **Measure** each graph node (`stream_mode="updates"` gives timestamps) instead of guessing.
2. **Find the critical path**: only the slowest chain of steps decides total time.
3. **Pick a lever**: run in parallel, do less work, use a cheaper model, start earlier, or reuse earlier work.
4. **Re-measure and re-run the evals**, so speed never hides a quality drop.

LLM latency is roughly network + time to first token + output tokens x time per token. Output tokens dominate,
so shortening or splitting the output and removing calls from the critical path save the most time. Trimming
input mainly saves cost.

## Optimization log

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

## Alternatives considered

| Choice | Alternative | Why not |
|---|---|---|
| Parallel agents in LangGraph | Keep sequential | Same cost, much longer wall-clock time |
| Haiku for short steps | One large model everywhere | Slower and dearer; quality on short tasks is the same (checked by the evals) |
| Direct flight HTTP call | Persistent MCP session | More moving parts for one fixed call; MCP is kept where reuse matters (weather, search) |
| Postgres cache | Redis | No new service and it survives restarts; Redis is the next step at higher traffic (a hit costs about 0.5 s against sub-millisecond) |
| Map-reduce itinerary | Shorter prompt or a smaller model | Cutting output loses detail; a smaller model risks quality (not A/B tested yet) |
| Streaming over SSE | WebSocket or polling | SSE is one-way and simple for text; polling wastes requests |
| Trimming context | Not done yet | Prompts are small (about 1.5k to 3k tokens) and output length dominates time, so it would mainly save cost. Next step: log tokens per node, then trim repeated context and measure |

Not changed on purpose: the weather MCP server (about 6 s cold, not on the critical path and a useful showcase) and merging the two supervisor calls (they already run together).

### What did not work the first time

- **Parallel itinerary, first try:** blocks of 3 days saved only about 5 s because each day came out longer. Fix: 2-day blocks (at most 4) and a cap of about 120 words per day.
- **Silent slow path:** worker threads could not reach LangGraph's stream writer, so the parallel draft raised an error and fell back to one long call (about 40 s slower). Found by checking event counts; fixed with `contextvars.copy_context()`.
- **Repeated sights:** without a shared outline two blocks planned the same day trip. Fix: outline first, each sight on one day only.
- **Tavily rate limit (429):** repeated test runs made the whole request fail. Fix: fallback text plus caching.

## Next steps

- LLM-as-judge scoring of itineraries (does the plan respect days, budget and weather?)
- A check that every listed flight number appears in the AviationStack data (hallucination check)
- Latency and cost tracking per node through LangSmith
- Regression run in CI on every pull request

### Context trimming (planned, not done)

Measured on one request: flight guidance about 300 tokens, raw hotel search text about 1,050 tokens, draft itinerary
about 1,650 tokens. The itinerary prompt is therefore about 1.5k tokens and the final prompt about 3k, against 1.5k to
2.5k tokens of output. Plan: log tokens in and out per node, trim repeated context (the four parallel day blocks
repeat the same data), keep only the fields each step needs, then compare eval scores and plan quality before and
after. Expected gain: lower cost and a small latency gain.
