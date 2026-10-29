"""Offline unit tests: no API keys, database or network needed."""

import unittest

from tripweaver.services.flights import parse_route, resolve_location_to_iata
from tripweaver.utils import cached, content_text, json_from_llm


class ContentTextTests(unittest.TestCase):
    def test_string_is_returned_unchanged(self):
        self.assertEqual(content_text("hello"), "hello")

    def test_content_blocks_are_flattened(self):
        blocks = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
        self.assertEqual(content_text(blocks), "ab")


class JsonFromLlmTests(unittest.TestCase):
    def test_extracts_object_from_wrapped_text(self):
        self.assertEqual(json_from_llm('Sure: {"a": 1} done'), {"a": 1})

    def test_raises_without_object(self):
        with self.assertRaises(ValueError):
            json_from_llm("no json here")


class CacheTests(unittest.TestCase):
    def test_second_call_uses_cache(self):
        calls = []

        def compute():
            calls.append(1)
            return "value"

        key = ("unit-test", "cache")
        self.assertEqual(cached(key, 60, compute), "value")
        self.assertEqual(cached(key, 60, compute), "value")
        self.assertEqual(len(calls), 1)

    def test_rejected_values_are_not_stored(self):
        calls = []

        def compute():
            calls.append(1)
            return None

        key = ("unit-test", "no-store")
        cached(key, 60, compute, store_if=lambda v: v is not None)
        cached(key, 60, compute, store_if=lambda v: v is not None)
        self.assertEqual(len(calls), 2)


class RouteTests(unittest.TestCase):
    def test_city_to_city(self):
        self.assertEqual(
            parse_route("Plan a trip from Dubai to San Francisco"),
            ("DXB", "SFO"),
        )

    def test_country_aliases_win_over_iata_codes(self):
        self.assertEqual(resolve_location_to_iata("USA"), "JFK")


if __name__ == "__main__":
    unittest.main()
