import unittest
import base64
from pathlib import Path
from tempfile import TemporaryDirectory

from docx import Document

from backend.softcopyright.blueprint import FeatureModule, ProductBlueprint
from backend.softcopyright.docgen import (
    _add_ui_figure,
    _actual_screenshot_action_labels,
    _actual_screenshot_operation_notes,
    _manual_semantic_term_covered,
    _manual_ui_button_label_match,
    _visible_content_caption,
    _visible_content_intro_paragraphs,
    analyze_manual_ui_consistency,
)
from backend.softcopyright.screenshots import UiScreenshot


class ManualUiConsistencyTests(unittest.TestCase):
    def test_industry_login_fields_generate_consistent_notes_without_captcha_value(self):
        for account in ("医护账号", "教师账户", "企业邮箱"):
            with self.subTest(account=account), TemporaryDirectory() as temporary_directory:
                root = Path(temporary_directory)
                item = UiScreenshot(
                    "login", "登录界面", "", "login.html", page_kind="login",
                    image_path=str(root / "login.png"),
                    visible_content_summary={
                        "ready": True,
                        "visible_text": f"用户登录 {account} 密码 验证码 7K4P 记住账号 登录系统",
                        "headings": ["用户登录"],
                        "fields": [account, "密码", "验证码 7K4P", "记住账号"],
                        "actions": ["登录系统"],
                    },
                )
                caption = _visible_content_caption(item)
                notes = _actual_screenshot_operation_notes(item, self._blueprint().modules[0])
                self.assertIn(account, caption)
                self.assertIn(account, " ".join(notes))
                self.assertNotIn("7K4P", caption + " ".join(notes))
                self.assertNotIn("记住账号", caption)
                document = Document()
                document.add_paragraph("图：登录界面，" + caption)
                for index, note in enumerate(notes, 1):
                    document.add_paragraph(f"{index}. {note}")
                path = root / "manual.docx"
                document.save(path)
                result = analyze_manual_ui_consistency(path, self._blueprint(), {"login": item})
                self.assertTrue(result["manual_ui_consistency_ready"], result)

    def test_semantic_aliases_cover_equivalent_visible_field_labels(self):
        self.assertTrue(_manual_semantic_term_covered("来源计划版本", "来源版本计划版本"))
        self.assertTrue(_manual_semantic_term_covered("预测范围", "影响范围预测周期"))
        self.assertTrue(_manual_semantic_term_covered("生产工单进度", "订单完工进度生产进度"))
        self.assertTrue(_manual_semantic_term_covered("状态条件", "会话状态网络类型"))
        self.assertFalse(_manual_semantic_term_covered("生产工单进度", "物料齐套日期"))

    def test_symbol_only_button_labels_match_exact_screenshot_actions(self):
        self.assertTrue(_manual_ui_button_label_match("↻", ["查询计划", "↻"]))
        self.assertTrue(_manual_ui_button_label_match(" ◉ ", ["◉"]))
        self.assertTrue(_manual_ui_button_label_match("登录按钮", ["登录系统"]))
        self.assertTrue(_manual_ui_button_label_match("复核", ["审核"]))
        self.assertFalse(_manual_ui_button_label_match("!", ["确认"]))

    def test_login_action_is_recovered_from_visible_text(self):
        screenshot = UiScreenshot(
            "login",
            "登录界面",
            "登录说明。",
            "login.html",
            visible_content_summary={
                "ready": True,
                "visible_text": "账号 密码 验证码 登录系统",
                "actions": [],
            },
        )

        self.assertEqual(_actual_screenshot_action_labels(screenshot), ["登录系统"])

        screenshot.visible_content_summary["visible_text"] = "手机号 短信验证码 登录并进入应用"
        self.assertEqual(_actual_screenshot_action_labels(screenshot), ["登录并进入应用"])

    def test_admin_operation_notes_rewrite_mobile_role_from_blueprint_contract(self):
        screenshot = UiScreenshot(
            "order_operation_1",
            "订单支付筛选界面",
            "筛选订单支付信息。",
            "order_operation_1.html",
            page_kind="operation",
            interaction_action="筛选订单支付",
            interaction_role="移动端用户",
            interaction_trigger="需要筛选订单支付",
            visible_content_summary={
                "ready": True,
                "visible_text": "订单支付 筛选条件 查询",
                "headings": ["订单支付"],
                "fields": ["订单编号"],
                "actions": ["查询"],
            },
        )
        module = FeatureModule(
            key="order",
            title="订单支付管理",
            description="管理订单支付。",
            entities=["PaymentOrder"],
        )

        notes = _actual_screenshot_operation_notes(
            screenshot,
            module,
            design_brief={"expected_renderer": "admin"},
        )
        text = " ".join(notes)

        self.assertNotIn("移动端", text)
        self.assertIn("终端用户", text)

    def test_ui_figure_does_not_restore_mobile_role_after_notes_are_sanitized(self):
        screenshot = UiScreenshot(
            "service_operation_1",
            "服务预约筛选界面",
            "筛选服务预约信息。",
            "service_operation_1.html",
            page_kind="operation",
            interaction_action="筛选服务预约",
            interaction_role="移动端用户",
            interaction_trigger="需要筛选服务预约",
            visible_content_summary={
                "ready": True,
                "visible_text": "服务预约 筛选条件 查询",
                "headings": ["服务预约"],
                "fields": ["预约编号"],
                "actions": ["查询"],
            },
        )
        document = Document()

        _add_ui_figure(
            document,
            {screenshot.key: screenshot},
            screenshot.key,
            screenshot.title,
            screenshot.caption,
            design_brief={"expected_renderer": "admin"},
        )
        text = " ".join(paragraph.text for paragraph in document.paragraphs)

        self.assertNotIn("移动端", text)
        self.assertIn("终端用户", text)

    def _blueprint(self):
        return ProductBlueprint(
            software_name="质量管理系统",
            version="V1.0",
            language="JavaScript",
            product_type="应用软件",
            industry="工程质量管理",
            purpose="质量管理",
            summary="质量管理",
            modules=[
                FeatureModule(
                    "quality_plan",
                    "质量策划",
                    "维护质量策划。",
                    ["QualityPlan"],
                    data_fields=["策划编号", "策划名称", "策划状态"],
                )
            ],
            roles=["质量员"],
            pages=["质量策划"],
            dev_environment={},
            runtime_environment={},
        )

    def test_titles_and_buttons_match_actual_screenshot_metadata(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = root / "page.png"
            image.write_bytes(b"png")
            screenshots = {
                "quality_plan": UiScreenshot(
                    "quality_plan",
                    "质量策划",
                    "质量策划页面。",
                    str(root / "main.html"),
                    page_kind="module",
                    module_key="quality_plan",
                    image_path=str(image),
                    action_crops={"保存策划": str(root / "save.png")},
                ),
                "quality_plan_operation_2_2": UiScreenshot(
                    "quality_plan_operation_2_2",
                    "质量策划导出界面",
                    "导出质量策划。",
                    str(root / "export.html"),
                    page_kind="operation",
                    module_key="quality_plan",
                    image_path=str(image),
                    action_crops={"导出当前视图": str(root / "export.png")},
                ),
            }
            document = Document()
            document.add_paragraph("图：质量策划，质量策划页面。")
            document.add_paragraph("1. 页面提供【保存策划】入口。")
            document.add_paragraph("图：质量策划导出界面，导出质量策划。")
            document.add_paragraph("1. 页面提供【导出当前视图】入口。")
            path = root / "manual.docx"
            document.save(path)

            result = analyze_manual_ui_consistency(path, self._blueprint(), screenshots)

            self.assertTrue(result["manual_ui_consistency_ready"])
            self.assertEqual(result["manual_ui_title_mismatch_count"], 0)
            self.assertEqual(result["manual_ui_button_mismatch_count"], 0)

    def test_plain_numbered_action_text_counts_when_action_is_visible(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = root / "page.png"
            image.write_bytes(b"png")
            screenshots = {
                "quality_plan": UiScreenshot(
                    "quality_plan",
                    "质量策划",
                    "质量策划页面。",
                    str(root / "main.html"),
                    page_kind="module",
                    module_key="quality_plan",
                    image_path=str(image),
                    visible_content_summary={"ready": False, "visible_text": "质量策划 审核", "actions": ["审核"]},
                )
            }
            document = Document()
            document.add_paragraph("图：质量策划，质量策划页面。")
            document.add_paragraph("1. 质量策划界面提供审核等当前截图可见操作，点击后按页面反馈继续处理。")
            path = root / "manual.docx"
            document.save(path)

            result = analyze_manual_ui_consistency(path, self._blueprint(), screenshots)

            self.assertTrue(result["manual_ui_consistency_ready"])
            self.assertEqual(result["manual_ui_missing_button_coverage_count"], 0)

    def test_mismatched_title_and_button_fail_delivery_gate(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = root / "page.png"
            image.write_bytes(b"png")
            screenshots = {
                "quality_plan": UiScreenshot(
                    "quality_plan",
                    "质量策划",
                    "质量策划页面。",
                    str(root / "main.html"),
                    page_kind="module",
                    module_key="quality_plan",
                    image_path=str(image),
                    action_crops={"保存策划": str(root / "save.png")},
                )
            }
            document = Document()
            document.add_paragraph("图：质量策划统计界面，展示统计结果。")
            document.add_paragraph("1. 点击【删除记录】完成处理。")
            path = root / "manual.docx"
            document.save(path)

            result = analyze_manual_ui_consistency(path, self._blueprint(), screenshots)

            self.assertFalse(result["manual_ui_consistency_ready"])
            self.assertEqual(result["manual_ui_title_mismatch_count"], 1)
            self.assertEqual(result["manual_ui_button_mismatch_count"], 1)

    def test_button_image_alt_text_counts_as_button_coverage(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = root / "page.png"
            image.write_bytes(b"png")
            button = root / "save.png"
            button.write_bytes(
                base64.b64decode(
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
                )
            )
            screenshots = {
                "quality_plan": UiScreenshot(
                    "quality_plan",
                    "质量策划",
                    "质量策划页面。",
                    str(root / "main.html"),
                    page_kind="module",
                    module_key="quality_plan",
                    image_path=str(image),
                    action_crops={"保存策划": str(button)},
                )
            }
            document = Document()
            document.add_paragraph("图：质量策划，质量策划页面。")
            paragraph = document.add_paragraph("1. 页面提供")
            shape = paragraph.add_run().add_picture(str(button))
            shape._inline.docPr.set("descr", "保存策划")
            shape._inline.docPr.set("title", "保存策划")
            paragraph.add_run("入口。")
            path = root / "manual.docx"
            document.save(path)

            result = analyze_manual_ui_consistency(path, self._blueprint(), screenshots)

            self.assertTrue(result["manual_ui_consistency_ready"])
            self.assertEqual(result["manual_ui_missing_button_coverage_count"], 0)

    def test_action_notes_prioritize_real_actions_and_skip_record_badges(self):
        screenshot = UiScreenshot(
            "measurement_warning",
            "施工测量记录预警界面",
            "预警处理。",
            "warning.html",
            page_kind="operation",
            module_key="measurement",
            action_crops={
                "施工测量记录记录01": "record-1.png",
                "施工测量记录记录02": "record-2.png",
                "控制点复测": "tab.png",
                "下发复测指令": "issue.png",
                "打开原始成果": "open.png",
                "下载测量包": "download.png",
                "追加复核说明": "append.png",
            },
        )

        labels = _actual_screenshot_action_labels(screenshot)

        self.assertEqual(labels, ["下发复测指令", "打开原始成果", "下载测量包", "追加复核说明"])

    def test_login_notes_skip_captcha_codes_and_symbol_only_controls(self):
        screenshot = UiScreenshot(
            "login",
            "登录界面",
            "用户输入账号、密码和验证码后进入系统。",
            "login.html",
            page_kind="login",
            action_crops={"7K4M": "captcha.png", "◉": "password.png"},
            visible_content_summary={
                "ready": True,
                "visible_text": "生产运营安全登录 登录密码 图形验证码 7 K 4 M 进入生产指挥台",
                "headings": ["生产运营安全登录"],
                "metrics": [],
                "fields": ["生产运营账号", "登录密码", "图形验证码"],
                "statuses": [],
                "filters": [],
                "actions": ["7 K 4 M", "进入生产指挥台 →", "7K4M", "◉"],
            },
        )

        labels = _actual_screenshot_action_labels(screenshot)
        notes = _actual_screenshot_operation_notes(screenshot, self._blueprint().modules[0])
        text = "\n".join(notes)

        self.assertEqual(labels, ["进入生产指挥台"])
        self.assertIn("【进入生产指挥台】", text)
        self.assertNotIn("【7K4M】", text)
        self.assertNotIn("【◉】", text)

    def test_login_notes_explain_semantic_auxiliary_controls(self):
        screenshot = UiScreenshot(
            "login",
            "登录界面",
            "用户输入账号、密码和验证码后进入系统。",
            "login.html",
            page_kind="login",
            action_crops={"刷新验证码": "captcha.png", "显示密码": "password.png"},
            visible_content_summary={
                "ready": True,
                "visible_text": "生产运营安全登录 登录密码 图形验证码 进入生产指挥台",
                "headings": ["生产运营安全登录"],
                "metrics": [],
                "fields": ["生产运营账号", "登录密码", "图形验证码"],
                "statuses": [],
                "filters": [],
                "actions": ["刷新验证码", "进入生产指挥台", "显示密码"],
            },
        )

        labels = _actual_screenshot_action_labels(screenshot)
        notes = _actual_screenshot_operation_notes(screenshot, self._blueprint().modules[0])
        text = "\n".join(notes)

        self.assertEqual(labels, ["进入生产指挥台", "刷新验证码", "显示密码"])
        self.assertIn("点击【进入生产指挥台】完成登录校验", text)
        self.assertIn("验证码不清晰时使用【刷新验证码】重新获取", text)
        self.assertIn("核对密码输入时使用【显示密码】", text)

    def test_login_intro_does_not_treat_captcha_placeholder_as_filter(self):
        screenshot = UiScreenshot(
            "login",
            "登录界面",
            "",
            "login.html",
            page_kind="login",
            visible_content_summary={
                "ready": True,
                "visible_text": "生产运营安全登录 生产运营账号 登录密码 图形验证码 输入右侧字符 工厂运行环境 岗位身份 进入生产指挥台",
                "headings": ["生产运营安全登录", "岗位身份", "运行与访问状态"],
                "metrics": ["当前工单"],
                "fields": ["生产运营账号", "登录密码", "图形验证码"],
                "statuses": [],
                "filters": ["输入右侧字符", "华东二厂 · 生产环境"],
                "actions": ["进入生产指挥台", "刷新验证码", "显示密码"],
            },
        )

        paragraphs = _visible_content_intro_paragraphs(screenshot, "登录界面")
        caption = _visible_content_caption(screenshot)
        notes = _actual_screenshot_operation_notes(screenshot, self._blueprint().modules[0])
        text = "\n".join(paragraphs)
        note_text = "\n".join(notes)

        self.assertIn("生产运营账号、登录密码、图形验证码", text)
        self.assertIn("通过【进入生产指挥台】完成登录校验", text)
        self.assertNotIn("调整查看范围", text)
        self.assertNotIn("通过输入右侧字符", text)
        self.assertIn("生产运营账号、登录密码、图形验证码、工厂运行环境、岗位身份", caption)
        self.assertNotIn("当前工单", caption)
        self.assertIn("依次填写生产运营账号、登录密码、图形验证码，再选择工厂运行环境、岗位身份", note_text)
        self.assertNotIn("调整当前查看范围", note_text)
        self.assertNotIn("当前可见的指标", note_text)

    def test_operation_notes_use_page_visible_content_instead_of_module_blueprint_fields(self):
        module = self._blueprint().modules[0]
        screenshot = UiScreenshot(
            "quality_plan",
            "质量策划",
            "泛化说明。",
            "quality-plan.html",
            page_kind="module",
            module_key="quality_plan",
            action_crops={"保存策划": "save.png"},
            visible_content_summary={
                "ready": True,
                "visible_text": "质量策划结果详情 关联完整性与执行条件 计划执行率 检验点完成率 保存策划",
                "headings": ["质量策划结果详情", "关联完整性与执行条件"],
                "metrics": ["计划执行率", "检验点完成率"],
                "fields": ["工程结构树编号"],
                "statuses": ["当前状态：可执行"],
                "filters": [],
                "actions": ["保存策划"],
            },
        )

        notes = _actual_screenshot_operation_notes(screenshot, module, main_page=True)
        text = "\n".join(notes)

        self.assertIn("质量策划结果详情", text)
        self.assertIn("计划执行率", text)
        self.assertNotIn("策划状态", text)

    def test_operation_notes_explain_each_visible_action(self):
        module = self._blueprint().modules[0]
        screenshot = UiScreenshot(
            "quality_plan_query",
            "质量策划查询界面",
            "查询质量策划。",
            "quality-plan-query.html",
            page_kind="operation",
            module_key="quality_plan",
            action_crops={"查询": "query.png", "导出清单": "export.png", "查看": "view.png"},
            visible_content_summary={
                "ready": True,
                "visible_text": "策划状态 责任岗位 查询 导出清单 查看",
                "headings": ["质量策划查询结果"],
                "metrics": [],
                "fields": ["策划编号", "策划状态"],
                "statuses": ["待复核"],
                "filters": ["策划状态", "责任岗位"],
                "actions": ["查询", "导出清单", "查看"],
            },
        )

        notes = _actual_screenshot_operation_notes(screenshot, module)
        text = "\n".join(notes)

        self.assertIn("【查询】用于应用当前筛选条件并刷新结果列表", text)
        self.assertIn("【导出清单】用于将当前页面结果生成清单或报表", text)
        self.assertIn("【查看】用于打开所选记录的详细内容", text)
        self.assertIn("策划编号、策划状态", text)
        self.assertNotIn("点击后按页面反馈继续处理", text)

    def test_operation_notes_cover_all_visible_actions_without_summary_report_copy(self):
        module = self._blueprint().modules[0]
        screenshot = UiScreenshot(
            "quality_plan_actions",
            "质量策划查询界面",
            "查询质量策划。",
            "quality-plan-actions.html",
            page_kind="operation",
            module_key="quality_plan",
            visible_content_summary={
                "ready": True,
                "visible_text": "策划状态 责任岗位 查询 重置 导出清单 查看 刷新",
                "headings": ["质量策划查询结果"],
                "metrics": ["命中策划数"],
                "fields": ["策划编号", "策划状态"],
                "statuses": ["待复核"],
                "filters": ["策划状态", "责任岗位"],
                "actions": ["查询", "重置", "导出清单", "查看", "刷新"],
            },
        )

        text = "\n".join(_actual_screenshot_operation_notes(screenshot, module))

        for label in ["查询", "重置", "导出清单", "查看", "刷新"]:
            self.assertIn(f"【{label}】", text)
        self.assertIn("本页用于集中查看质量策划查询结果", text)
        self.assertNotIn("当前截图的主要业务区域包括", text)
        self.assertNotIn("当前可见的指标包括", text)

    def test_operation_notes_include_contract_trigger_inputs_state_and_evidence(self):
        module = self._blueprint().modules[0]
        screenshot = UiScreenshot(
            "quality_plan_approval",
            "质量策划审批界面",
            "审批质量策划。",
            "quality-plan-approval.html",
            page_kind="operation",
            module_key="quality_plan",
            interaction_action="批准质量策划",
            interaction_role="质量主管",
            interaction_trigger="约束校验全部通过",
            interaction_input_fields=["策划编号", "审批意见"],
            interaction_pre_state="待审批",
            interaction_post_state="已批准并进入执行准备",
            interaction_result_evidence="审批记录、状态轨迹、执行准备清单",
            requires_confirmation=True,
            visible_content_summary={
                "ready": True,
                "visible_text": "批准质量策划 策划编号 审批意见 确认批准 取消",
                "headings": ["批准质量策划"],
                "metrics": [],
                "fields": ["策划编号", "审批意见"],
                "statuses": ["待审批"],
                "filters": [],
                "actions": ["确认批准", "取消"],
            },
        )

        text = "\n".join(_actual_screenshot_operation_notes(screenshot, module))

        self.assertIn("本页用于批准质量策划，由质量主管在约束校验全部通过时发起", text)
        self.assertIn("策划编号、审批意见用于在提交前核对", text)
        self.assertIn("处理前状态为待审批", text)
        self.assertIn("审批记录、状态轨迹、执行准备清单", text)
        self.assertIn("业务状态将更新为已批准并进入执行准备", text)

    def test_operation_notes_hide_internal_fields_and_legacy_truncated_contract_text(self):
        module = self._blueprint().modules[0]
        screenshot = UiScreenshot(
            "quality_plan_legacy_contract",
            "质量策划处置界面",
            "处置质量策划。",
            "quality-plan-legacy.html",
            page_kind="operation",
            module_key="quality_plan",
            interaction_action="建立质量处置",
            interaction_role="生产管理人员、车间主管、生产计划",
            interaction_trigger="质量风险达到高等级",
            interaction_input_fields=["quality_plan_id", "action_type", "responsible_role"],
            interaction_pre_state="延期风险处于待关注或处理中，当前风险来源尚无有效处置任务，或已有",
            interaction_post_state="生成状态为待处理的交付处置任务，关联风险订单、预测快照、计划版本",
            interaction_result_evidence="处置任务编号、状态轨迹",
            visible_content_summary={
                "ready": True,
                "visible_text": "建立质量处置 策划编号 处置类型 责任岗位 保存草稿 提交处置",
                "headings": ["建立质量处置"],
                "metrics": [],
                "fields": ["策划编号", "处置类型", "责任岗位"],
                "statuses": ["待处理"],
                "filters": [],
                "actions": ["保存草稿", "提交处置"],
            },
        )

        text = "\n".join(_actual_screenshot_operation_notes(screenshot, module))

        self.assertIn("由生产管理人员、车间主管在质量风险达到高等级时发起", text)
        self.assertIn("操作前需填写或核对策划编号、处置类型、责任岗位", text)
        self.assertNotIn("quality_plan_id", text)
        self.assertNotIn("生产计划在", text)
        self.assertNotIn("或已有", text)
        self.assertNotIn("关联风险订单、预测快照、计划版本", text)

    def test_confirmation_notes_explain_review_fields_before_actions(self):
        module = self._blueprint().modules[0]
        screenshot = UiScreenshot(
            "quality_plan_confirm",
            "确认质量策划界面",
            "确认质量策划。",
            "quality-plan-confirm.html",
            page_kind="operation",
            module_key="quality_plan",
            requires_confirmation=True,
            interaction_post_state="质量策划转为待执行",
            action_crops={"确认质量策划": "confirm.png", "取消": "cancel.png"},
            visible_content_summary={
                "ready": True,
                "visible_text": "确认质量策划 策划编号 责任岗位 确认质量策划 取消",
                "headings": ["确认质量策划"],
                "metrics": [],
                "fields": ["策划编号", "责任岗位"],
                "statuses": [],
                "filters": [],
                "actions": ["确认质量策划", "取消"],
            },
        )

        notes = _actual_screenshot_operation_notes(screenshot, module)
        text = "\n".join(notes)

        self.assertIn("策划编号、责任岗位用于在提交前核对", text)
        self.assertIn("【确认质量策划】用于提交当前处理结论", text)
        self.assertIn("【取消】用于关闭当前弹窗", text)

    def test_confirmation_notes_prefer_full_cropped_button_label_over_nested_summary_action(self):
        module = self._blueprint().modules[0]
        screenshot = UiScreenshot(
            "quality_plan_submit_confirm",
            "提交质量策划结论界面",
            "提交质量策划结论。",
            "quality-plan-submit-confirm.html",
            page_kind="operation",
            module_key="quality_plan",
            requires_confirmation=True,
            interaction_action="提交结论",
            action_crops={"确认提交结论": "confirm.png", "取消": "cancel.png"},
            visible_content_summary={
                "ready": True,
                "visible_text": "确认提交结论 当前策划 状态变化 取消",
                "headings": ["确认提交结论"],
                "metrics": [],
                "fields": ["当前策划", "状态变化"],
                "statuses": [],
                "filters": [],
                "actions": ["取消", "确认提交结论", "提交结论"],
            },
        )

        notes = _actual_screenshot_operation_notes(screenshot, module)
        text = "\n".join(notes)

        self.assertEqual(text.count("【确认提交结论】"), 1)
        self.assertNotIn("【提交结论】", text)

    def test_confirmation_notes_prefer_visible_dialog_fields_over_hidden_contract_inputs(self):
        module = self._blueprint().modules[0]
        screenshot = UiScreenshot(
            "quality_plan_confirm_visible",
            "确认质量策划界面",
            "确认质量策划。",
            "quality-plan-confirm-visible.html",
            page_kind="operation",
            module_key="quality_plan",
            requires_confirmation=True,
            interaction_role="质量主管",
            interaction_input_fields=["质量策划单编号", "审批意见", "签名标识"],
            visible_content_summary={
                "ready": True,
                "visible_text": "确认质量策划 当前策划 状态变化 影响范围 确认质量策划 取消",
                "headings": ["确认质量策划"],
                "metrics": [],
                "fields": ["当前策划", "状态变化", "影响范围"],
                "statuses": [],
                "filters": [],
                "actions": ["确认质量策划", "取消"],
            },
        )

        text = "\n".join(_actual_screenshot_operation_notes(screenshot, module))

        self.assertIn("当前策划、状态变化、影响范围用于在提交前核对", text)
        self.assertNotIn("质量策划单编号、审批意见、签名标识用于在提交前核对", text)

    def test_semantic_gate_rejects_blueprint_field_missing_from_visible_page(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = root / "page.png"
            image.write_bytes(b"png")
            screenshots = {
                "quality_plan": UiScreenshot(
                    "quality_plan",
                    "质量策划",
                    "质量策划页面。",
                    str(root / "main.html"),
                    page_kind="module",
                    module_key="quality_plan",
                    image_path=str(image),
                    action_crops={"保存策划": str(root / "save.png")},
                    visible_content_summary={
                        "ready": True,
                        "visible_text": "质量策划结果详情 计划执行率 保存策划",
                        "headings": ["质量策划结果详情"],
                        "metrics": ["计划执行率"],
                        "fields": [],
                        "statuses": [],
                        "filters": [],
                        "actions": ["保存策划"],
                    },
                )
            }
            document = Document()
            document.add_paragraph("图：质量策划，页面展示质量策划结果详情和计划执行率。")
            document.add_paragraph("1. 页面可查看策划状态，并提供【保存策划】入口。")
            path = root / "manual.docx"
            document.save(path)

            result = analyze_manual_ui_consistency(path, self._blueprint(), screenshots)

            self.assertFalse(result["manual_ui_consistency_ready"])
            self.assertEqual(result["manual_ui_semantic_mismatch_count"], 1)
            self.assertIn("策划状态", result["manual_ui_semantic_mismatches"][0]["references"])

    def test_semantic_gate_accepts_visible_page_terms(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = root / "page.png"
            image.write_bytes(b"png")
            screenshots = {
                "quality_plan": UiScreenshot(
                    "quality_plan",
                    "质量策划",
                    "质量策划页面。",
                    str(root / "main.html"),
                    page_kind="module",
                    module_key="quality_plan",
                    image_path=str(image),
                    action_crops={"保存策划": str(root / "save.png")},
                    visible_content_summary={
                        "ready": True,
                        "visible_text": "质量策划结果详情 计划执行率 保存策划",
                        "headings": ["质量策划结果详情"],
                        "metrics": ["计划执行率"],
                        "fields": [],
                        "statuses": [],
                        "filters": [],
                        "actions": ["保存策划"],
                    },
                )
            }
            document = Document()
            document.add_paragraph("图：质量策划，页面展示质量策划结果详情和计划执行率。")
            document.add_paragraph("1. 页面可查看质量策划结果详情和计划执行率，并提供【保存策划】入口。")
            path = root / "manual.docx"
            document.save(path)

            result = analyze_manual_ui_consistency(path, self._blueprint(), screenshots)

            self.assertTrue(result["manual_ui_consistency_ready"])
            self.assertTrue(result["manual_ui_semantic_ready"])

    def test_semantic_gate_allows_archived_state_in_workflow_precondition(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = root / "page.png"
            image.write_bytes(b"png")
            screenshots = {
                "quality_plan_operation_2_2": UiScreenshot(
                    "quality_plan_operation_2_2",
                    "质量策划",
                    "质量策划页面。",
                    str(root / "main.html"),
                    page_kind="operation",
                    module_key="quality_plan",
                    image_path=str(image),
                    action_crops={"生成留存结果": str(root / "save.png")},
                    visible_content_summary={
                        "ready": True,
                        "visible_text": "质量策划 留存范围 生成留存结果",
                        "headings": ["留存范围", "生成后结果"],
                        "metrics": [],
                        "fields": ["留存用途"],
                        "statuses": [],
                        "filters": [],
                        "actions": ["生成留存结果"],
                    },
                )
            }
            document = Document()
            document.add_paragraph("图：质量策划，页面展示留存范围和生成后结果。")
            document.add_paragraph("1. 操作前状态为目标记录已归档，填写留存用途后点击【生成留存结果】。")
            path = root / "manual.docx"
            document.save(path)

            result = analyze_manual_ui_consistency(path, self._blueprint(), screenshots)

            self.assertTrue(result["manual_ui_consistency_ready"])
            self.assertEqual(result["manual_ui_semantic_mismatch_count"], 0)

    def test_semantic_gate_still_rejects_explicit_archive_control_when_not_visible(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = root / "page.png"
            image.write_bytes(b"png")
            screenshots = {
                "quality_plan_operation_2_2": UiScreenshot(
                    "quality_plan_operation_2_2",
                    "质量策划",
                    "质量策划页面。",
                    str(root / "main.html"),
                    page_kind="operation",
                    module_key="quality_plan",
                    image_path=str(image),
                    visible_content_summary={
                        "ready": True,
                        "visible_text": "质量策划 留存范围 生成留存结果",
                        "headings": ["留存范围", "生成后结果"],
                        "metrics": [],
                        "fields": ["留存用途"],
                        "statuses": [],
                        "filters": [],
                        "actions": ["生成留存结果"],
                    },
                )
            }
            document = Document()
            document.add_paragraph("图：质量策划，页面展示留存范围和生成后结果。")
            document.add_paragraph("1. 点击归档按钮完成处理。")
            path = root / "manual.docx"
            document.save(path)

            result = analyze_manual_ui_consistency(path, self._blueprint(), screenshots)

            self.assertFalse(result["manual_ui_consistency_ready"])
            self.assertIn("归档", result["manual_ui_semantic_mismatches"][0]["references"])

    def test_semantic_gate_accepts_input_placeholder_captured_as_filter(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = root / "page.png"
            image.write_bytes(b"png")
            screenshots = {
                "quality_plan": UiScreenshot(
                    "quality_plan",
                    "质量策划",
                    "质量策划页面。",
                    str(root / "main.html"),
                    page_kind="module",
                    module_key="quality_plan",
                    image_path=str(image),
                    action_crops={"保存策划": str(root / "save.png")},
                    visible_content_summary={
                        "ready": True,
                        "visible_text": "质量策划结果详情 保存策划",
                        "headings": ["质量策划结果详情"],
                        "metrics": [],
                        "fields": [],
                        "statuses": [],
                        "filters": ["输入策划状态"],
                        "actions": ["保存策划"],
                    },
                )
            }
            document = Document()
            document.add_paragraph("图：质量策划，页面展示质量策划结果详情。")
            document.add_paragraph("1. 可通过输入策划状态限定范围，并提供【保存策划】入口。")
            path = root / "manual.docx"
            document.save(path)

            result = analyze_manual_ui_consistency(path, self._blueprint(), screenshots)

            self.assertTrue(result["manual_ui_consistency_ready"])
            self.assertTrue(result["manual_ui_semantic_ready"])

    def test_semantic_gate_accepts_field_labels_from_label_help_text_summaries(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = root / "login.png"
            image.write_bytes(b"png")
            screenshots = {
                "login": UiScreenshot(
                    "login",
                    "登录界面",
                    "登录说明。",
                    str(root / "login.html"),
                    page_kind="login",
                    image_path=str(image),
                    visible_content_summary={
                        "ready": True,
                        "visible_text": "登录账号 登录密码 图形验证码 登录并进入服务运营控制台",
                        "headings": ["服务运营工作台登录"],
                        "metrics": [],
                        "fields": [
                            "登录账号 支持客服坐席和客服主管账号",
                            "登录密码 密码需包含大小写字母和数字",
                            "图形验证码",
                        ],
                        "statuses": [],
                        "filters": [],
                        "actions": ["登录并进入服务运营控制台"],
                    },
                )
            }
            document = Document()
            document.add_paragraph("图：登录界面，页面展示登录账号、登录密码和图形验证码。")
            document.add_paragraph("1. 填写登录账号和登录密码后完成身份校验。")
            path = root / "manual.docx"
            document.save(path)

            result = analyze_manual_ui_consistency(path, self._blueprint(), screenshots)

            self.assertTrue(result["manual_ui_consistency_ready"])
            self.assertEqual(result["manual_ui_semantic_coverage_missing_count"], 0)

    def test_desktop_screenshots_reject_mobile_terminal_description_anywhere_in_manual(self):
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            image = root / "page.png"
            image.write_bytes(b"png")
            screenshots = {
                "quality_plan": UiScreenshot(
                    "quality_plan",
                    "质量策划",
                    "质量策划页面。",
                    str(root / "main.html"),
                    page_kind="module",
                    module_key="quality_plan",
                    image_path=str(image),
                    width=1280,
                    height=720,
                )
            }
            document = Document()
            document.add_paragraph("本软件提供移动端质量工作入口。")
            document.add_paragraph("图：质量策划，质量策划页面。")
            path = root / "manual.docx"
            document.save(path)

            result = analyze_manual_ui_consistency(path, self._blueprint(), screenshots)

            self.assertFalse(result["manual_ui_consistency_ready"])
            self.assertEqual(result["manual_ui_expected_renderer"], "admin")
            self.assertIn("移动端", result["manual_ui_renderer_mismatches"])


if __name__ == "__main__":
    unittest.main()
