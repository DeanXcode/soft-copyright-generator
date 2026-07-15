from types import SimpleNamespace
import unittest

from backend.softcopyright.operation_coverage import (
    configured_operation_screen_count,
    module_operation_coverage,
    operation_spec,
)
from backend.softcopyright.ai_frontend_codegen import _visual_reference_cache_key


class OperationCoverageTests(unittest.TestCase):
    def test_style_reference_cache_is_independent_of_manual_page_count(self):
        task = SimpleNamespace(seed="seed-1", software_name="\u751f\u4ea7\u5e73\u53f0", product_type="\u4eba\u5de5\u667a\u80fd\u8f6f\u4ef6")
        ui_blueprint = SimpleNamespace(
            renderer="admin",
            design_brief={
                "visual_identity_spec": {"identity_signature": "factory-green"},
                "product_experience_spec": {"experience_shape": "industrial-console"},
            },
        )

        first = _visual_reference_cache_key(task, ui_blueprint, 27, "1280x720")
        expanded = _visual_reference_cache_key(task, ui_blueprint, 35, "1280x720")

        self.assertEqual(first, expanded)

    def test_admin_module_selects_three_complementary_operation_pages(self):
        module = SimpleNamespace(
            title="\u751f\u4ea7\u8d28\u91cf\u5206\u6790",
            description="\u8d28\u91cf\u770b\u677f\u4e0e\u8d8b\u52bf\u5206\u6790",
            pages=[],
            operations=[
                "\u67e5\u8be2",
                "\u6821\u9a8c",
                "\u5206\u6790",
                "\u786e\u8ba4",
                "\u5f52\u6863",
                "\u7edf\u8ba1",
            ],
        )

        specs = module_operation_coverage(module, renderer="admin", module_index=0)

        self.assertEqual(len(specs), 3)
        self.assertEqual(specs[0].category, "lookup")
        self.assertGreaterEqual(len({item.category for item in specs}), 2)
        self.assertNotIn("\u5220\u9664", {item.action for item in specs})

    def test_read_only_module_uses_detail_or_analysis_instead_of_fake_crud(self):
        module = SimpleNamespace(
            title="\u7cfb\u7edf\u76d1\u63a7\u770b\u677f",
            description="\u5b9e\u65f6\u76d1\u63a7\u9884\u8b66\u548c\u8d8b\u52bf",
            pages=[],
            operations=[],
        )

        specs = module_operation_coverage(module, renderer="admin", module_index=1)

        self.assertEqual(len(specs), configured_operation_screen_count("admin"))
        self.assertIn("\u67e5\u8be2", {item.action for item in specs})
        self.assertIn("\u67e5\u770b\u8be6\u60c5", {item.action for item in specs})
        self.assertFalse({"\u65b0\u589e", "\u7f16\u8f91", "\u5220\u9664"} & {item.action for item in specs})

    def test_only_destructive_operations_require_confirmation(self):
        delete_spec = operation_spec("\u5220\u9664")
        query_spec = operation_spec("\u67e5\u8be2")
        play_spec = operation_spec("\u64ad\u653e")

        self.assertTrue(delete_spec.requires_confirmation)
        self.assertEqual(delete_spec.mode, "confirm")
        self.assertFalse(query_spec.requires_confirmation)
        self.assertFalse(play_spec.requires_confirmation)
        self.assertEqual(play_spec.mode, "instant")

    def test_mobile_coverage_does_not_copy_unrelated_registration_action(self):
        module = SimpleNamespace(
            title="\u97f3\u4e50\u641c\u7d22",
            description="\u641c\u7d22\u6b4c\u66f2\u5e76\u67e5\u770b\u6b4c\u8bcd",
            pages=[],
            operations=["\u97f3\u4e50\u641c\u7d22\u767b\u8bb0"],
        )

        specs = module_operation_coverage(module, renderer="mobile_app", module_index=0)

        self.assertEqual(len(specs), configured_operation_screen_count("mobile_app"))
        self.assertNotIn("\u767b\u8bb0", {item.action for item in specs})
        self.assertTrue({"\u641c\u7d22\u4e0e\u7b5b\u9009", "\u67e5\u770b\u6b4c\u8bcd"} & {item.action for item in specs})


if __name__ == "__main__":
    unittest.main()
