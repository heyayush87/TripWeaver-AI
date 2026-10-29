"""Run the evaluation suite and write evals/latest_results.json.

Usage:
    uv run python scripts/run_evals.py            # offline + LLM evals
    uv run python scripts/run_evals.py --offline  # no API calls

LLM evals call the supervisor (Claude Haiku) twice per query: once for the
guardrail and once for routing and constraint extraction.
"""

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tripweaver.services.flights import (  # noqa: E402
    parse_route,
    resolve_location_to_iata,
)

DATASET = json.loads((ROOT / "evals" / "dataset.json").read_text(encoding="utf-8"))
RESULTS_FILE = ROOT / "evals" / "latest_results.json"


def pct(passed: int, total: int) -> float:
    return round(100 * passed / total, 1) if total else 0.0


def eval_route_resolution() -> dict:
    failures = []
    for case in DATASET["route_resolution"]:
        dep, arr = parse_route(case["query"])
        got = (
            resolve_location_to_iata(str(dep or "")) or dep,
            resolve_location_to_iata(str(arr or "")) or arr,
        )
        if got != (case["dep"], case["arr"]):
            failures.append({"query": case["query"], "expected": [case["dep"], case["arr"]], "got": list(got)})
    total = len(DATASET["route_resolution"])
    return {"passed": total - len(failures), "total": total, "failures": failures}


def eval_supervisor() -> dict:
    from tripweaver.agents.supervisor import supervisor_agent

    guardrail_fail, routing_fail, extraction_fail = [], [], []
    latencies = []

    for case in DATASET["guardrail"]:
        start = time.perf_counter()
        out = supervisor_agent({"user_query": case["query"]})
        latencies.append(time.perf_counter() - start)
        if out["guardrail_allowed"] != case["allowed"]:
            guardrail_fail.append({"query": case["query"], "expected_allowed": case["allowed"]})

    for case in DATASET["routing"]:
        out = supervisor_agent({"user_query": case["query"]})
        agents = set(out["selected_agents"])
        missing = [a for a in case["include"] if a not in agents]
        unwanted = [a for a in case["exclude"] if a in agents]
        if missing or unwanted:
            routing_fail.append({"query": case["query"], "missing": missing, "unwanted": unwanted})

    for case in DATASET["extraction"]:
        out = supervisor_agent({"user_query": case["query"]})
        constraints = out["trip_constraints"]
        origin = str(constraints.get("origin", "")).lower()
        destination = str(constraints.get("destination", "")).lower()
        if case["origin"] not in origin or case["destination"] not in destination:
            extraction_fail.append({"query": case["query"], "got": [origin, destination]})

    def block(name, failures):
        total = len(DATASET[name])
        return {"passed": total - len(failures), "total": total, "failures": failures}

    return {
        "guardrail": block("guardrail", guardrail_fail),
        "routing": block("routing", routing_fail),
        "extraction": block("extraction", extraction_fail),
        "mean_supervisor_seconds": round(sum(latencies) / len(latencies), 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    results = {"date": date.today().isoformat(), "route_resolution": eval_route_resolution()}
    if not args.offline:
        results.update(eval_supervisor())

    RESULTS_FILE.write_text(json.dumps(results, indent=2), encoding="utf-8")

    for name in ("route_resolution", "guardrail", "routing", "extraction"):
        if name in results:
            r = results[name]
            print(f"{name:17} {r['passed']}/{r['total']}  ({pct(r['passed'], r['total'])}%)")
            for failure in r["failures"]:
                print("   FAIL:", json.dumps(failure, ensure_ascii=True))
    if "mean_supervisor_seconds" in results:
        print("mean supervisor time per query:", results["mean_supervisor_seconds"], "s")


if __name__ == "__main__":
    main()
