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
| ⚡ **Parallel agents** | Flights, hotels and weather run at the same time |
| 🛫 **Real flight options** | Airline, flight number and departure/arrival times from AviationStack |
| 🏨 **Hotels** | Web search through Tavily (MCP) |
| 🌦️ **Weather** | Custom OpenWeather MCP server (current + forecast) |
| 💰 **Budget check** | Flags feasibility and money-saving options |
| ✅ **Human-in-the-loop** | Approve the draft, or request changes with feedback |
| 💾 **Persistent chats** | LangGraph checkpoints stored in PostgreSQL, one `thread_id` per chat |
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
    BU --> I[Itinerary draft]
    I --> A{{Human approval}}
    A -- approve / request changes --> FN[Final plan]
    FN --> R([Response])
```

1. The **supervisor** (Claude Haiku) checks that the request is about travel, extracts origin, destination, duration and budget, and chooses the agents.
2. **Flight, hotel and weather** agents run in parallel (LangGraph fan-out).
3. The **budget** agent reviews their results, then the **itinerary** agent (Claude Sonnet) writes a draft.
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
| Unit tests | Helpers, cache, route parsing | 8 / 8 pass |
| Route resolution | "from X to Y" turned into the right airport codes | 6 / 6 |
| Guardrail | 12 travel requests allowed, 8 unrelated or harmful ones blocked | 20 / 20 |
| Routing | Right agents chosen (and wrong ones left out) | 5 / 5 |
| Constraint extraction | Origin and destination read correctly | 5 / 5 |

Mean supervisor time per request (guardrail + routing, two Haiku calls): **3.3 s**.

### Performance

Measured on one request, "Plan a 7 days Thailand trip from Bangladesh with budget hotels and sightseeing", time until the draft is ready for approval:

| Version | Time to draft |
|---|---|
| Agents run one after another, Sonnet everywhere | ~137 s |
| Parallel agents + Haiku for cheap steps + direct flight API | ~74 s |

The itinerary writer (~42 s) is now the largest single cost. Caching and the faster final-polish model were added afterwards and have not been timed yet.

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
- The in-memory cache is per process and resets on restart.

## 🛣️ Roadmap

- [ ] Let users pick a flight and carry the choice into the plan
- [ ] Stream the draft to the browser as it is written
- [ ] Real fare data (for example Amadeus)
- [ ] CI pipeline running tests and evals
