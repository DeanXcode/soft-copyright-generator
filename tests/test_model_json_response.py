import json
import unittest
from unittest.mock import patch

from backend.softcopyright.llm.json_response import parse_json_object
from backend.softcopyright.llm_blueprint import _parse_json
from backend.softcopyright.frontend_codegen.page_spec_request import _parse_json_object
from backend.softcopyright.frontend_codegen.page_spec import PageSpecValidationError
from backend.softcopyright.llm_architecture import _parse_json as parse_architecture
from backend.softcopyright.llm_manual import _parse_json as parse_manual
from backend.softcopyright.ui_blueprint import _parse_json as parse_ui
from backend.softcopyright.feature_inference import _parse_json as parse_features
from backend.softcopyright.ai_frontend_codegen import _parse_json as parse_frontend

PARSERS = (parse_json_object, _parse_json, _parse_json_object, parse_architecture,
           parse_manual, parse_ui, parse_features, parse_frontend)


class ModelJsonResponseTests(unittest.TestCase):
    def test_complete_nested_values_and_escaped_braces_are_preserved(self):
        data = {"modules": [{"title": 'a } { \\" b'}], "pages": ["login", "home"]}
        for parser in PARSERS:
            self.assertEqual(parser("```json\n" + json.dumps(data) + "\n```"), data)

    def test_only_missing_outer_terminator_is_repaired_without_losing_pages(self):
        data = {"scenario": "clinic", "modules": [{"title": "visits"}], "pages": ["home"]}
        raw = json.dumps(data)[:-1]
        for tail in ("", ",\n  "):
            with patch("backend.softcopyright.llm.json_response.trace_event") as trace:
                self.assertEqual(parse_json_object(raw + tail), data)
            self.assertEqual(trace.call_args.kwargs["repair"], "outer_object_terminator")
            for parser in PARSERS:
                self.assertEqual(parser(raw + tail), data)

    def test_incomplete_values_nested_containers_and_extra_documents_are_rejected(self):
        for raw in (
            '{"a":[{"x":1}', '{"a":[1,', '{"a":"cut',
            '{"a":', '{"a":12', '{"a":true', '{"a":[1],"b":',
            '{"a":[1],"b":"cut', '{"a":[1], bad', '{"a":[1]} {"b":2}',
            'prefix {"a":[1]}', '{"a":[1]} trailing', '{"a":[1}}',
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(ValueError):
                    parse_json_object(raw)

    def test_parser_does_not_cut_at_last_nested_object(self):
        raw = '{"modules":[{"title":"course"}],"pages":["home"'
        with self.assertRaises(PageSpecValidationError) as raised:
            _parse_json_object(raw)
        self.assertIn("第 1 行", str(raised.exception))
        self.assertIsInstance(raised.exception.__cause__, json.JSONDecodeError)
        self.assertEqual(raised.exception.__cause__.pos, len(raw))

    def test_repaired_json_still_runs_page_schema_validation(self):
        from backend.softcopyright.frontend_codegen.page_spec_request import request_page_spec
        from types import SimpleNamespace
        provider = SimpleNamespace(chat=lambda *a, **kw: '{"regions":[],')
        with self.assertRaises(PageSpecValidationError) as raised:
            request_page_spec(provider=provider, software_context={}, screen={"key": "home"},
                              module={}, visual_identity={}, color_contract={})
        self.assertIn("schema_version", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
