"""Offline tests for API limit detection and context stripping."""

import unittest
from unittest import mock

import anthropic
import httpx

from tripweaver.context import build_context, clip, prepare, trim_search_results
from tripweaver.limits import (
    ANTHROPIC,
    AVIATIONSTACK,
    TAVILY,
    ApiLimitError,
    classify_exception,
    classify_text,
    raise_if_limit,
    unique,
)


def _anthropic_error(cls, status, message):
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status, request=request)
    return cls(message, response=response, body=None)


class ClassifyTests(unittest.TestCase):
    def test_aviationstack_usage_limit_is_a_quota_failure(self):
        found = classify_text(AVIATIONSTACK, "usage_limit_reached: monthly limit")
        self.assertEqual((found.api, found.kind), (AVIATIONSTACK, "quota"))

    def test_rate_limit_is_marked_as_wait_and_retry(self):
        found = classify_text(TAVILY, "blocked due to excessive requests (429)")
        self.assertEqual(found.kind, "rate_limit")

    def test_plan_restriction_is_not_a_limit(self):
        self.assertIsNone(
            classify_text(AVIATIONSTACK, "function_access_restricted: plan")
        )

    def test_tool_exception_with_api_hint(self):
        exc = RuntimeError("Tavily error 429: excessive requests")
        self.assertEqual(classify_exception(exc, TAVILY).api, TAVILY)

    def test_unrelated_error_is_not_a_limit(self):
        self.assertIsNone(classify_exception(ValueError("bad json"), TAVILY))

    def test_anthropic_rate_limit_error(self):
        exc = _anthropic_error(anthropic.RateLimitError, 429, "slow down")
        found = classify_exception(exc)
        self.assertEqual((found.api, found.kind), (ANTHROPIC, "rate_limit"))

    def test_anthropic_empty_credit_balance(self):
        exc = _anthropic_error(
            anthropic.BadRequestError, 400, "Your credit balance is too low"
        )
        found = classify_exception(exc)
        self.assertEqual((found.api, found.kind), (ANTHROPIC, "quota"))

    def test_other_anthropic_errors_are_not_limits(self):
        exc = _anthropic_error(anthropic.BadRequestError, 400, "invalid request")
        self.assertIsNone(classify_exception(exc))

    def test_raise_if_limit_raises_only_for_limits(self):
        with self.assertRaises(ApiLimitError):
            raise_if_limit(RuntimeError("429 too many requests"), ANTHROPIC)
        raise_if_limit(RuntimeError("something else"), ANTHROPIC)

    def test_unique_keeps_one_entry_per_api(self):
        items = [{"api": "A", "message": "1"}, {"api": "A", "message": "2"}]
        self.assertEqual(unique(items), [{"api": "A", "message": "1"}])


class AgentFallbackTests(unittest.TestCase):
    def test_hotel_limit_still_returns_a_plan_input_and_names_the_api(self):
        from tripweaver.agents.hotel import hotel_agent

        boom = RuntimeError("Tavily error 429: excessive requests")
        with mock.patch("tripweaver.agents.hotel.cached", side_effect=boom):
            out = hotel_agent({"user_query": "trip to Paris"})

        self.assertIn("unavailable", out["hotel_results"])
        self.assertEqual(out["api_limits"][0]["api"], TAVILY)

    def test_hotel_other_failure_has_no_limit_entry(self):
        from tripweaver.agents.hotel import hotel_agent

        with mock.patch(
            "tripweaver.agents.hotel.cached", side_effect=RuntimeError("dns")
        ):
            out = hotel_agent({"user_query": "trip to Paris"})

        self.assertNotIn("api_limits", out)


class ClaudeFailureFallbackTests(unittest.TestCase):
    def test_budget_failure_gives_a_note_not_a_crash(self):
        from tripweaver.agents.budget import budget_agent

        with mock.patch(
            "tripweaver.agents.budget.fast_llm",
            mock.Mock(invoke=mock.Mock(side_effect=RuntimeError("overloaded"))),
        ):
            out = budget_agent({"user_query": "trip"})

        self.assertIn("could not be generated", out["budget_results"])

    def test_budget_quota_error_still_stops_the_run(self):
        from tripweaver.agents.budget import budget_agent

        with mock.patch(
            "tripweaver.agents.budget.fast_llm",
            mock.Mock(invoke=mock.Mock(side_effect=RuntimeError("429 too many requests"))),
        ):
            with self.assertRaises(ApiLimitError):
                budget_agent({"user_query": "trip"})

    def test_final_failure_falls_back_to_the_approved_draft(self):
        from tripweaver.agents.final import final_agent

        with mock.patch(
            "tripweaver.agents.final.final_llm",
            mock.Mock(stream=mock.Mock(side_effect=RuntimeError("boom"))),
        ):
            out = final_agent({"approved": True, "itinerary": "Day 1: Paris"})

        self.assertEqual(out["final_response"], "Day 1: Paris")


class ContextTests(unittest.TestCase):
    def test_clip_cuts_at_a_word_and_marks_it(self):
        self.assertEqual(clip("alpha beta gamma", 12), "alpha beta ...")
        self.assertEqual(clip("short", 50), "short")

    def test_search_results_keep_top_three_without_urls(self):
        text = "\n\n".join(
            f"{i}. Hotel {i}\nhttps://example.com/{i}\nGood place number {i}."
            for i in range(1, 6)
        )
        trimmed = trim_search_results(text)
        self.assertNotIn("http", trimmed)
        self.assertIn("3. Hotel 3", trimmed)
        self.assertNotIn("4. Hotel 4", trimmed)

    def test_error_json_snippets_are_dropped(self):
        text = (
            "1. Real hotel\nhttps://a.com\nNice rooms.\n\n"
            "2. Weather page\nhttps://b.com\n{'error': {'code': 2007}}\n\n"
            "3. Another hotel\nhttps://c.com\nGood location."
        )
        trimmed = trim_search_results(text)
        self.assertNotIn("error", trimmed)
        self.assertIn("Another hotel", trimmed)

    def test_empty_sections_are_skipped(self):
        state = {"user_query": "trip", "weather_results": "", "budget_results": "  "}
        spec = [
            ("user_query", "Request", 100),
            ("weather_results", "Weather", 100),
            ("budget_results", "Budget", 100),
        ]
        self.assertEqual(build_context(state, spec), "Request:\ntrip")

    def test_prepare_does_not_change_the_original_state(self):
        state = {"hotel_results": "1. A\nhttps://x.com\nsnippet"}
        self.assertNotIn("http", prepare(state)["hotel_results"])
        self.assertIn("http", state["hotel_results"])


if __name__ == "__main__":
    unittest.main()
