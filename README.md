# TripWeaver AI

An AI travel planner. Give it a request such as "Plan a 7-day trip from India to Sweden under 10 lakh" and it searches flights and hotels, then writes a day-by-day itinerary and a final travel plan.

## How it works

A LangGraph pipeline runs four steps in order:

```
START -> flight_agent -> hotel_agent -> itinerary_agent -> final_agent -> END
```

- **flight_agent**: looks up live flights with the AviationStack API.
- **hotel_agent**: searches the web for hotels with Tavily.
- **itinerary_agent**: Claude drafts the itinerary from the search results.
- **final_agent**: Claude writes the final formatted answer.

After every step the state is saved to PostgreSQL by a LangGraph checkpointer, so a chat keeps its history (one `thread_id` per chat). Runs can be traced in LangSmith.

## Tech stack

- Python 3.12, managed with [uv](https://docs.astral.sh/uv/)
- LangGraph and LangChain
- Claude (via `langchain-anthropic`)
- FastAPI, Jinja2 templates, plain JS frontend
- PostgreSQL (`psycopg`) for the checkpointer
- Tavily (web search) and AviationStack (flights)

## Project structure

```
app.py            FastAPI app and routes
backend.py        LangGraph state, nodes, graph and run_travel_agent()
tools/            flight_tool.py (AviationStack), tavily_tool.py (Tavily)
templates/        index.html
static/           script.js, style.css
```

## Setup

1. Install [uv](https://docs.astral.sh/uv/) and clone the repo.
2. Install dependencies:
   ```
   uv sync
   ```
3. Create a `.env` file in the project root:
   ```
   ANTHROPIC_API_KEY=
   TAVILY_API_KEY=
   AVIATION_API_KEY=
   DATABASE_URL=postgresql://user:password@host/dbname?sslmode=require
   DEFAULT_ORIGIN_IATA=

   # optional, for LangSmith tracing
   LANGSMITH_TRACING=true
   LANGSMITH_ENDPOINT=https://api.smith.langchain.com
   LANGSMITH_API_KEY=
   LANGSMITH_PROJECT=Trip
   ```
   Never commit this file.

## Run

```
uv run uvicorn app:app --reload
```

Open http://localhost:8000.

### Endpoints

- `GET /` web interface
- `POST /api/travel` run the travel agent
- `GET /health` health check

## Notes

- The flight API returns live flight status, not ticket prices, so fares in the answer are estimates.
- Flight lookup works best with a clear route such as "Delhi to Stockholm".
