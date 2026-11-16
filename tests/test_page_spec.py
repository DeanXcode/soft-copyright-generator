import json
from types import SimpleNamespace
import unittest

from backend.softcopyright.frontend_codegen.legacy_fallback import requires_legacy_fallback
from backend.softcopyright.frontend_codegen.page_spec import (
    COMPONENT_LIBRARY_VERSION,
    FRONTEND_ENGINE_VERSION,
    PAGE_SPEC_SCHEMA_VERSION,
    PageSpecValidationError,
    normalize_page_spec,
    page_spec_cache_key,
    repair_cached_page_spec_columns,
)
from backend.softcopyright.frontend_codegen.page_spec_renderer import render_page_spec
from backend.softcopyright.frontend_codegen.page_spec_request import request_page_spec
from backend.softcopyright.frontend_codegen.page_spec_semantics import (
    sanitize_page_spec_semantics,
    unauthorized_page_spec_terms,
)


def _valid_spec(page_key="quality_task", page_kind="operation"):
    return {
        "schema_version": PAGE_SPEC_SCHEMA_VERSION,
        "page_key": page_key,
        "page_kind": page_kind,
        "layout": "table_workspace",
        "theme": {"density": "comfortable", "accent_variant": "primary"},
        "regions": [
            {"id": "filters", "component": "filter_bar", "title": "质量任务筛选", "fields": [{"label": "任务编号"}]},
            {"id": "metrics", "component": "metric_group", "title": "质量指标", "metrics": [{"label": "合格率", "value": "98.6%"}]},
            {
                "id": "table",
                "component": "data_table",
                "title": "质量任务清单",
                "columns": ["任务编号", "构件名称", "责任岗位", "任务状态"],
                "items": [{"label": "QT-001", "title": "预制墙板", "owner": "质量工程师", "status": "待复核"}],
            },
            {"id": "workflow", "component": "workflow", "title": "复核流程", "steps": ["接收任务", "核验数据", "提交结论"]},
            {"id": "result", "component": "operation_result", "title": "复核结果"},
        ],
        "actions": [{"action_key": "confirm_quality_task", "label": "确认复核", "variant": "primary", "requires_confirmation": True}],
        "interaction_contract": {
            "mode": "workflow",
            "action_key": "confirm_quality_task",
            "role": "质量工程师",
            "trigger": "检测数据和现场记录核验完成",
            "input_fields": ["任务编号", "复核结论"],
            "pre_state": "待复核",
            "post_state": "已复核",
            "result_evidence": "复核结论和审计日志",
            "requires_confirmation": True,
        },
    }


def _valid_login_spec(page_key="login"):
    return {
        "schema_version": PAGE_SPEC_SCHEMA_VERSION,
        "page_key": page_key,
        "page_kind": "login",
        "layout": "login_workspace",
        "theme": {"density": "comfortable", "accent_variant": "primary"},
        "regions": [
            {
                "id": "brand",
                "component": "detail",
                "title": "质量管理平台",
                "items": [
                    {"label": "平台名称", "value": "装配式建筑构件安装质量智能校验与管理平台"},
                    {"label": "当前版本", "value": "V1.0"},
                    {"label": "核心链路", "value": "采集、校验、复核和追溯"},
                ],
            },
            {
                "id": "login_form",
                "component": "form",
                "title": "登录质量校验工作台",
                "fields": [
                    {"label": "账号", "value": ""},
                    {"label": "密码", "value": "不应回显"},
                    {"label": "图形验证码", "value": "7K4P"},
                    {"label": "进入角色", "value": "质量检查人员"},
                    {"label": "项目环境", "value": "华东示范项目"},
                    {"label": "记住账号", "value": "True"},
                ],
            },
            {
                "id": "result",
                "component": "operation_result",
                "title": "安全与环境提示",
                "items": [{"label": "登录状态", "value": "未建立会话"}],
            },
        ],
        "actions": [
            {
                "action_key": "submit_login",
                "label": "登录质量校验工作台",
                "variant": "secondary",
                "requires_confirmation": True,
            }
        ],
        "interaction_contract": {
            "mode": "submit",
            "action_key": "submit_login",
            "role": "质量检查人员",
            "trigger": "用户输入有效账号、密码和验证码",
            "input_fields": ["账号", "密码", "图形验证码", "进入角色"],
            "pre_state": "未登录",
            "post_state": "进入质量管理工作台",
            "result_evidence": "登录会话和授权范围",
            "requires_confirmation": False,
        },
    }


class _SpecProvider:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append((messages, kwargs))
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload, ensure_ascii=False)


class PageSpecTests(unittest.TestCase):
    def test_request_scopes_other_modules_and_keeps_current_contract(self):
        module = {"key": "quality", "title": "质量任务", "operation_specs": [{"role": "质量工程师", "trigger": "检测完成"}]}
        context = {"renderer": "admin", "feature_hint": "需求" * 4000,
                   "modules": [module, {"key": "other", "title": "其他模块", "description": "无关详情" * 5000}]}
        original = json.dumps(context, ensure_ascii=False)
        provider = _SpecProvider(_valid_spec(page_kind="module"))
        request_page_spec(provider=provider, software_context=context,
                          screen={"key": "quality_task", "page_kind": "module"},
                          module=module, visual_identity={}, color_contract={})
        prompt = provider.calls[0][0][-1]["content"]
        payload, _ = json.JSONDecoder().raw_decode(prompt[prompt.index("{"):])
        self.assertEqual(payload["module"], module)
        self.assertEqual(payload["software_context"]["modules"][1], {"key": "other", "title": "其他模块"})
        self.assertLess(len(prompt), len(original) / 2)
        self.assertEqual(json.dumps(context, ensure_ascii=False), original)

    def test_confirmed_interaction_is_injected_without_model_echo_or_repair(self):
        spec = _valid_spec()
        spec.pop("interaction_contract")
        spec.pop("actions")
        provider = _SpecProvider(spec)
        result = request_page_spec(
            provider=provider, software_context={}, module={"title": "质量任务"},
            screen={"key": "quality_task", "page_kind": "operation",
                    "interaction_action_key": "confirm_quality_task", "interaction_action": "确认复核",
                    "interaction_mode": "workflow", "interaction_role": "质量工程师",
                    "interaction_trigger": "检测完成", "interaction_input_fields": ["复核结论"],
                    "interaction_pre_state": "待复核", "interaction_post_state": "已复核",
                    "interaction_result_evidence": "复核结论", "requires_confirmation": True},
            visual_identity={}, color_contract={},
        )
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(result["interaction_contract"]["trigger"], "检测完成")
        self.assertEqual(result["interaction_contract"]["result_evidence"], "复核结论")
        self.assertEqual(result["actions"][0]["action_key"], "confirm_quality_task")
        self.assertTrue(result["actions"][0]["requires_confirmation"])

    def test_unlicensed_review_ledger_terms_are_replaced_with_module_semantics(self):
        spec = _valid_spec(page_kind="module")
        module = {
            "key": "attendance",
            "title": "员工考勤",
            "data_fields": ["员工编号", "打卡时间", "打卡位置"],
            "operations": ["上班打卡", "下班打卡", "查看考勤"],
            "operation_specs": [
                {
                    "label": "上班打卡",
                    "role": "员工",
                    "pre_state": "未打卡",
                    "post_state": "已打卡",
                    "result_evidence": "打卡时间和位置",
                }
            ],
        }
        screen = {"title": "上班打卡", "interaction_action": "上班打卡"}

        self.assertTrue(unauthorized_page_spec_terms(spec, module=module, screen=screen))
        sanitized, replaced = sanitize_page_spec_semantics(spec, module=module, screen=screen)
        text = json.dumps(sanitized, ensure_ascii=False)

        self.assertIn("复核", replaced)
        self.assertNotIn("待复核", text)
        self.assertNotIn("台账", text)
        self.assertNotIn("操作日志", text)
        self.assertIn("打卡", text)
        self.assertIn("未打卡", text)

    def test_explicit_review_contract_keeps_review_vocabulary(self):
        spec = _valid_spec()
        spec["interaction_contract"]["result_evidence"] = "复核结论和操作日志"
        module = {
            "title": "质量任务",
            "operation_specs": [
                {
                    "label": "确认复核",
                    "role": "质量工程师",
                    "pre_state": "待复核",
                    "post_state": "已复核",
                    "result_evidence": "复核结论和操作日志",
                }
            ],
        }
        sanitized, replaced = sanitize_page_spec_semantics(spec, module=module, screen={"interaction_action": "确认复核"})
        text = json.dumps(sanitized, ensure_ascii=False)

        self.assertNotIn("复核", replaced)
        self.assertIn("待复核", text)
        self.assertIn("复核结果", text)
        self.assertIn("操作日志", text)

    def test_cached_pagespec_renders_without_unlicensed_backoffice_terms(self):
        spec = _valid_spec(page_kind="module")
        module = {
            "key": "music",
            "title": "音乐播放",
            "data_fields": ["歌曲名称", "歌手", "播放状态"],
            "operations": ["播放歌曲", "收藏歌曲"],
            "operation_specs": [
                {
                    "label": "播放歌曲",
                    "role": "听众",
                    "pre_state": "未播放",
                    "post_state": "播放中",
                    "result_evidence": "播放进度和歌曲信息",
                }
            ],
        }
        normalized = normalize_page_spec(
            spec,
            expected_page_key="quality_task",
            expected_page_kind="module",
            expected_interaction={},
        )
        rendered = render_page_spec(
            normalized,
            css_scope="screen-music",
            creative_key="music-cache",
            renderer="admin",
            module=module,
            screen={"title": "歌曲播放", "interaction_action": "播放歌曲"},
            visual_identity={},
            color_contract={},
        )

        self.assertIn("播放歌曲", rendered["jsx"])
        for term in ("待复核", "台账", "操作日志", "系统管理员"):
            self.assertNotIn(term, rendered["jsx"])

    def test_column_objects_use_labels_instead_of_python_dict_text(self):
        spec = _valid_spec(page_kind="module")
        spec["actions"] = []
        spec["interaction_contract"] = {"mode": "browse"}
        spec["regions"][2]["columns"] = [
            {"key": "resident", "label": "住户编号"},
            {"key": "space", "label": "关联房屋"},
            {"key": "verify", "label": "认证状态"},
        ]

        normalized = normalize_page_spec(
            spec,
            expected_page_key="quality_task",
            expected_page_kind="module",
            expected_interaction={},
        )

        self.assertEqual(normalized["regions"][2]["columns"], ["住户编号", "关联房屋", "认证状态"])
        self.assertNotIn("{'key':", json.dumps(normalized, ensure_ascii=False))

    def test_structured_table_values_render_as_business_text(self):
        spec = _valid_spec(page_kind="module")
        spec["actions"] = []
        spec["interaction_contract"] = {"mode": "browse"}
        spec["regions"][2]["columns"] = ["任务编号", "责任岗位", "处置状态"]
        spec["regions"][2]["items"] = [
            {
                "任务编号": {"key": "task_code", "label": "QT-2026-018"},
                "责任岗位": {"name": "质量工程师", "code": "QE"},
                "处置状态": [
                    {"status": "待确认"},
                    {"status": "资料齐全"},
                ],
            }
        ]
        normalized = normalize_page_spec(
            spec,
            expected_page_key="quality_task",
            expected_page_kind="module",
            expected_interaction={},
        )
        rendered = render_page_spec(
            normalized,
            css_scope="screen-structured-values",
            creative_key="structured-values",
            renderer="admin",
            module={"title": "质量任务"},
            screen={"title": "质量任务清单"},
            visual_identity={},
            color_contract={},
        )

        self.assertIn("QT-2026-018", rendered["jsx"])
        self.assertIn("质量工程师", rendered["jsx"])
        self.assertIn("待确认、资料齐全", rendered["jsx"])
        for leaked in ("{'key':", '"key":', "[object Object]"):
            self.assertNotIn(leaked, rendered["jsx"])

    def test_corrupted_cached_column_strings_are_replaced_from_region_semantics(self):
        cached = _valid_spec(page_kind="module")
        cached["regions"][2]["title"] = "通行凭证与申领记录"
        cached["regions"][2]["columns"] = [
            "{'key': 'applicati",
            "{'key': 'holder', ",
            "{'key': 'credentia",
        ]

        changed = repair_cached_page_spec_columns(cached)

        self.assertEqual(changed, 1)
        self.assertEqual(
            cached["regions"][2]["columns"],
            ["申领编号", "持有人", "凭证类型", "生命周期状态", "适用门禁点", "有效期"],
        )
        self.assertNotIn("{'key':", json.dumps(cached, ensure_ascii=False))

    def test_backend_operation_spec_normalizes_and_renders_controlled_components(self):
        spec = normalize_page_spec(
            _valid_spec(),
            expected_page_key="quality_task",
            expected_page_kind="operation",
            expected_interaction={"action_key": "confirm_quality_task"},
        )
        rendered = render_page_spec(
            spec,
            css_scope="screen-quality-task",
            creative_key="quality-task-seed",
            renderer="admin",
            module={"title": "构件质量复核", "data_fields": ["任务编号", "构件名称", "复核结论"]},
            screen={"title": "构件质量任务复核", "requires_confirmation": True, "interaction_action": "确认复核"},
            visual_identity={"accent": "#0f766e"},
            color_contract={"dominant_colors": ["#173f48", "#168779", "#f3f7f7"]},
        )

        self.assertIn('data-page-spec="page-spec-v1"', rendered["jsx"])
        for class_name in ("filter-bar", "metric-grid", "table-frame", "workflow-board", "operation-result"):
            self.assertIn(class_name, rendered["jsx"])
        self.assertIn('data-shared-confirm-source="true"', rendered["jsx"])
        self.assertIn(".screen-quality-task", rendered["css"])
        self.assertNotIn("http://", rendered["css"])
        self.assertNotIn("style=", rendered["jsx"])

    def test_mobile_map_chart_relationship_and_list_components_render_without_legacy_css(self):
        spec = _valid_spec(page_key="mobile_map", page_kind="module")
        spec["layout"] = "mobile_feed"
        spec["actions"] = []
        spec["interaction_contract"] = {"mode": "browse"}
        spec["regions"] = [
            {"id": "map", "component": "map_panel", "title": "服务点位", "points": ["东区服务点", "西区服务点"]},
            {"id": "chart", "component": "chart", "title": "服务趋势", "series": [{"label": "周一", "value": "72"}]},
            {"id": "graph", "component": "relationship_graph", "title": "对象关系", "items": ["服务订单", "服务人员"]},
            {"id": "list", "component": "mobile_list", "title": "移动任务", "items": [{"label": "上门服务", "status": "进行中"}]},
        ]
        normalized = normalize_page_spec(
            spec,
            expected_page_key="mobile_map",
            expected_page_kind="module",
            expected_interaction={},
        )
        rendered = render_page_spec(
            normalized,
            css_scope="screen-mobile-map",
            creative_key="mobile-map-seed",
            renderer="mobile_app",
            module={},
            screen={"title": "移动服务地图"},
            visual_identity={},
            color_contract={},
        )

        for class_name in ("map-workspace", "chart-panel", "relationship-graph", "mobile-list"):
            self.assertIn(class_name, rendered["jsx"])
        self.assertIn("page-spec-mobile", rendered["jsx"])

    def test_pagespec_palette_uses_visual_identity_roles_instead_of_dominant_color_order(self):
        normalized = normalize_page_spec(
            _valid_login_spec(page_key="rose_login"),
            expected_page_key="rose_login",
            expected_page_kind="login",
            expected_interaction={},
        )
        rendered = render_page_spec(
            normalized,
            css_scope="screen-rose-login",
            creative_key="rose-login-seed",
            renderer="admin",
            module={},
            screen={"title": "登录界面"},
            visual_identity={
                "palette": {
                    "accent": "#be123c",
                    "accent_soft": "#fff1f2",
                    "sidebar": "#4c1d2f",
                    "canvas": "#fff6f7",
                }
            },
            color_contract={
                "dominant_colors": ["#925155", "#e7e0df", "#fefefe", "#f4f0ec", "#ffffff"]
            },
        )

        self.assertIn("--ps-accent:#be123c", rendered["css"])
        self.assertIn("--ps-ink:#4c1d2f", rendered["css"])
        self.assertIn("--ps-canvas:#fff6f7", rendered["css"])
        self.assertNotIn("--ps-accent:#e7e0df", rendered["css"])

    def test_login_spec_is_canonicalized_to_brand_and_compact_login_card(self):
        normalized = normalize_page_spec(
            _valid_login_spec(),
            expected_page_key="login",
            expected_page_kind="login",
            expected_interaction={"action_key": "submit_login"},
        )

        self.assertEqual(normalized["layout"], "login_workspace")
        self.assertEqual([region["component"] for region in normalized["regions"]], ["detail", "form"])
        self.assertEqual(
            [field["label"] for field in normalized["regions"][1]["fields"]],
            ["账号", "密码", "图形验证码", "进入角色"],
        )
        self.assertEqual(normalized["regions"][1]["fields"][1]["value"], "")
        self.assertEqual(normalized["actions"][0]["variant"], "primary")
        self.assertFalse(normalized["actions"][0]["requires_confirmation"])

        rendered = render_page_spec(
            normalized,
            css_scope="screen-login",
            creative_key="login-seed",
            renderer="admin",
            module={},
            screen={"title": "登录界面", "caption": "输入账号、密码和验证码后进入授权工作台。"},
            visual_identity={"palette": {"accent": "#be123c", "sidebar": "#4c1d2f", "canvas": "#fff6f7"}},
            color_contract={},
        )

        self.assertIn("login-shell", rendered["jsx"])
        self.assertIn("login-card", rendered["jsx"])
        self.assertIn("登录系统", rendered["jsx"])
        self.assertIn('type="password"', rendered["jsx"])
        self.assertIn("记住账号", rendered["jsx"])
        self.assertNotIn("page-spec-heading", rendered["jsx"])
        self.assertNotIn("operation-result", rendered["jsx"])
        self.assertNotIn("操作结果已记录", rendered["jsx"])
        self.assertNotIn("核心链路", rendered["jsx"])
        self.assertIn(".screen-login.page-spec-login", rendered["css"])

    def test_pagespec_palette_darkens_unreadable_accent_without_identity(self):
        normalized = normalize_page_spec(
            _valid_spec(page_key="pale_page", page_kind="module"),
            expected_page_key="pale_page",
            expected_page_kind="module",
            expected_interaction={},
        )
        rendered = render_page_spec(
            normalized,
            css_scope="screen-pale-page",
            creative_key="pale-page-seed",
            renderer="admin",
            module={},
            screen={"title": "浅色页面"},
            visual_identity={},
            color_contract={"dominant_colors": ["#fafafa", "#e7e0df", "#ffffff"]},
        )

        self.assertIn("--ps-accent:#168779", rendered["css"])
        self.assertIn("--ps-ink:#173f48", rendered["css"])

    def test_unknown_component_and_missing_interaction_contract_are_rejected(self):
        spec = _valid_spec(page_kind="module")
        spec["regions"] = [{"id": "custom", "component": "freeform_canvas", "title": "未知画布"}]
        spec.pop("interaction_contract")

        with self.assertRaises(PageSpecValidationError) as raised:
            normalize_page_spec(
                spec,
                expected_page_key="quality_task",
                expected_page_kind="module",
                expected_interaction={},
            )

        self.assertIn("未知组件", str(raised.exception))
        self.assertIn("interaction_contract", str(raised.exception))

    def test_page_spec_request_keeps_completion_headroom_and_rejects_oversized_content(self):
        provider = _SpecProvider(_valid_spec())
        result = request_page_spec(
            provider=provider,
            software_context={"renderer": "admin"},
            screen={"key": "quality_task", "page_kind": "operation", "interaction_action_key": "confirm_quality_task"},
            module={"title": "质量任务"},
            visual_identity={},
            color_contract={},
        )

        self.assertEqual(result["schema_version"], PAGE_SPEC_SCHEMA_VERSION)
        self.assertEqual(provider.calls[0][1]["max_tokens"], 2400)
        self.assertIn("不要生成 JSX、CSS、HTML", provider.calls[0][0][-1]["content"])

        oversized = _SpecProvider("{" + '"padding":"' + ("x" * 6100) + '"}')
        with self.assertRaises(PageSpecValidationError):
            request_page_spec(
                provider=oversized,
                software_context={},
                screen={"key": "quality_task", "page_kind": "module"},
                module={},
                visual_identity={},
                color_contract={},
            )

    def test_page_spec_repair_keeps_completion_headroom_and_demands_compact_output(self):
        provider = _SpecProvider(_valid_spec(page_kind="module"))

        request_page_spec(
            provider=provider,
            software_context={"renderer": "admin"},
            screen={"key": "quality_task", "page_kind": "module"},
            module={"title": "质量任务"},
            visual_identity={},
            color_contract={},
            validation_feedback="模型返回超过 6000 字符",
        )

        self.assertEqual(provider.calls[0][1]["max_tokens"], 2400)
        self.assertIn("最多保留 4 个 regions", provider.calls[0][0][-1]["content"])
        self.assertIn("唯一修复轮", provider.calls[0][0][-1]["content"])

    def test_formatting_whitespace_does_not_count_as_business_content(self):
        spec = _valid_spec(page_kind="module")
        padded = json.dumps(spec, ensure_ascii=False, indent=40)
        self.assertGreater(len(padded), 6000)
        provider = _SpecProvider(padded)
        result = request_page_spec(
            provider=provider, software_context={},
            screen={"key": "quality_task", "page_kind": "module"},
            module={"title": "质量任务"}, visual_identity={}, color_contract={},
        )
        self.assertEqual(result["page_key"], "quality_task")

    def test_login_page_spec_request_demands_login_only_components(self):
        provider = _SpecProvider(_valid_login_spec())

        result = request_page_spec(
            provider=provider,
            software_context={"renderer": "admin"},
            screen={"key": "login", "page_kind": "login", "interaction_action_key": "submit_login"},
            module={},
            visual_identity={},
            color_contract={},
        )

        prompt = provider.calls[0][0][-1]["content"]
        self.assertEqual([region["component"] for region in result["regions"]], ["detail", "form"])
        self.assertIn("regions 只能包含一个可选 detail 品牌区和一个必需 form 登录卡", prompt)
        self.assertIn("禁止 operation_result", prompt)
        self.assertIn('"allowed_region_components": [', prompt)
        self.assertNotIn('"data_table"', prompt.split('"allowed_region_components": [', 1)[1].split("]", 1)[0])

    def test_cache_key_includes_schema_component_library_and_engine_versions(self):
        key = page_spec_cache_key("creative-key")

        self.assertEqual(len(key), 64)
        self.assertEqual(PAGE_SPEC_SCHEMA_VERSION, "page-spec-v1")
        self.assertEqual(COMPONENT_LIBRARY_VERSION, "page-components-v3")
        self.assertEqual(FRONTEND_ENGINE_VERSION, "pagespec-hybrid-v6")

    def test_design_viewer_uses_desktop_browser_workspace_without_decorative_copy(self):
        spec = _valid_spec(page_kind="operation")
        spec["actions"] = [
            {
                "action_key": "open_design_file",
                "label": "打开当前团队中名称非常长的设计文件并进入评审",
                "variant": "primary",
            }
        ]
        spec["regions"][0]["subtitle"] = "这段装饰性说明不应显示"
        spec["regions"].append(
            {
                "id": "metrics",
                "component": "metric_group",
                "title": "文件状态",
                "metrics": [{"label": "访问状态", "value": "名称非常长的文件访问状态值"}],
            }
        )

        rendered = render_page_spec(
            spec,
            css_scope="screen-figma-browser",
            creative_key="figma-browser-key",
            renderer="admin",
            module={
                "title": "设计资源导航",
                "description": "浏览设计文件、页面画板和图层组件",
                "pages": ["移动端设计系统升级", "会员中心设计评审"],
            },
            screen={
                "title": "Figma文件接入-查询文件访问状态",
                "caption": "这段页面说明不应显示",
                "page_kind": "operation",
                "software_name": "Figma浏览器",
                "industry_subtype_key": "design_viewer",
                "interaction_action": "查询文件访问状态",
            },
            visual_identity={},
            color_contract={},
        )

        self.assertIn('data-design-viewer-workspace="true"', rendered["jsx"])
        for class_name in (
            "design-resource-panel",
            "design-canvas-panel",
            "design-canvas-stage",
            "design-inspector-panel",
        ):
            self.assertIn(class_name, rendered["jsx"])
        for decorative in (
            "page-spec-eyebrow",
            "模块工作台",
            "业务操作",
            "较上一周期保持稳定",
            "按计划完成现场处理",
            "这段页面说明不应显示",
            "这段装饰性说明不应显示",
        ):
            self.assertNotIn(decorative, rendered["jsx"])
        self.assertIn("overflow-wrap:anywhere", rendered["css"])
        self.assertIn("max-width:150px", rendered["css"])
        self.assertNotIn("page-spec-eyebrow", rendered["css"])

    def test_actions_use_shared_icon_markup_and_short_visible_labels(self):
        spec = _valid_spec(page_kind="operation")
        spec["actions"] = [
            {
                "action_key": "create_download_task",
                "label": "确认创建单个或批量任务",
                "variant": "primary",
            }
        ]
        normalized = normalize_page_spec(
            spec,
            expected_page_key="quality_task",
            expected_page_kind="operation",
            expected_interaction={},
        )
        rendered = render_page_spec(
            normalized,
            css_scope="screen-action-icons",
            creative_key="action-icons",
            renderer="admin",
            module={"title": "下载任务"},
            screen={"title": "创建任务", "interaction_action": "创建任务"},
            visual_identity={},
            color_contract={},
        )

        self.assertIn('className="page-action-icon" data-icon="＋"', rendered["jsx"])
        self.assertIn('title="确认创建单个或批量任务"', rendered["jsx"])
        self.assertIn('className="page-action-label">创建任务</span>', rendered["jsx"])
        self.assertIn("page-action-icon::before", rendered["css"])

    def test_pagespec_business_text_uses_wrapping_instead_of_ellipsis(self):
        rendered = render_page_spec(
            normalize_page_spec(
                _valid_spec(),
                expected_page_key="quality_task",
                expected_page_kind="operation",
                expected_interaction={},
            ),
            css_scope="screen-wrap",
            creative_key="wrap",
            renderer="admin",
            module={"title": "质量任务"},
            screen={"title": "质量任务复核", "interaction_action": "确认复核"},
            visual_identity={},
            color_contract={},
        )

        css = rendered["css"]
        self.assertIn("white-space:normal;overflow-wrap:anywhere;word-break:break-word", css)
        self.assertIn("td{min-height:38px;padding:8px", css)
        self.assertIn("overflow-wrap:anywhere", css)

    def test_game_and_three_dimensional_pages_use_legacy_fallback_but_maps_do_not(self):
        self.assertTrue(requires_legacy_fallback("game", SimpleNamespace(title="关卡大厅", caption="", interaction_action="")))
        self.assertTrue(requires_legacy_fallback("admin", SimpleNamespace(title="三维装配仿真", caption="", interaction_action="")))
        self.assertFalse(requires_legacy_fallback("admin", SimpleNamespace(title="区域地图监控", caption="地图点位", interaction_action="")))


if __name__ == "__main__":
    unittest.main()
