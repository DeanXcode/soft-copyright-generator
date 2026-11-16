from types import SimpleNamespace
import unittest

from backend.softcopyright.domain_profile import build_domain_profile, has_transport_domain_signal
from backend.softcopyright.generator import _is_transport_operation_context, _ui_screenshot_realism_checks
from backend.softcopyright.screenshots import _ui_transport_module
from backend.softcopyright.sourcegen import _is_transport_module


def _task(name, product_type="APP", feature_hint=""):
    return SimpleNamespace(software_name=name, product_type=product_type, feature_hint=feature_hint)


def _blueprint(industry, summary, subtype_key="", business_objects=None):
    return SimpleNamespace(
        industry=industry,
        summary=summary,
        scenario="",
        positioning="",
        business_objects=business_objects or [],
        modules=[],
        industry_subtype_key=subtype_key,
    )


class DomainProfileTests(unittest.TestCase):
    def test_download_task_scheduling_is_download_manager_not_transport(self):
        profile = build_domain_profile(
            _task("疾风下载", feature_hint="下载链接、下载任务、下载队列调度、后台下载、下载进度和断点续传"),
            _blueprint("移动文件下载", "支持已下载文件管理和下载记录复建"),
        )

        self.assertEqual(profile.key, "download_manager")
        self.assertEqual(profile.source, "download-manager-evidence")
        self.assertFalse(profile.transport_related)
        self.assertFalse(profile.requires_route_topology)
        self.assertIn("文件下载任务调度不是交通线路调度", profile.excluded_evidence)

    def test_figma_design_coordinates_do_not_trigger_survey_mapping(self):
        profile = build_domain_profile(
            _task("Figma浏览器", feature_hint="设计文件、页面画板、图层组件和画布坐标"),
            _blueprint("设计文件浏览与预览", "支持画板定位、图层检查、原型演示和设计评审"),
        )

        self.assertEqual(profile.key, "design_viewer")
        self.assertEqual(profile.source, "design-viewer-evidence")
        self.assertFalse(profile.transport_related)
        self.assertFalse(profile.requires_route_topology)

    def test_agency_accounting_signal_overrides_weak_employee_term(self):
        profile = build_domain_profile(
            _task("风灵月影代账", feature_hint="企业客户账套、代账会计员工、税务申报和财务报表"),
            _blueprint("企业代理记账与财税服务", "代账会计为企业客户编制凭证并完成申报交付"),
        )

        self.assertEqual(profile.key, "agency_accounting")
        self.assertEqual(profile.source, "agency-accounting-evidence")
        self.assertFalse(profile.requires_route_topology)

    def test_attendance_shift_does_not_enable_transport_route_gate(self):
        profile = build_domain_profile(
            _task("叮叮打卡", feature_hint="上下班打卡、考勤规则、员工排班和补卡申请"),
            _blueprint("企业人力资源与移动考勤", "员工依据今日班次和排班完成上下班定位打卡并查看考勤结果"),
        )

        self.assertEqual(profile.key, "workforce_attendance")
        self.assertFalse(profile.transport_related)
        self.assertFalse(profile.requires_route_topology)
        self.assertIn("班次", profile.weak_evidence)
        self.assertEqual(profile.enabled_gate_keys, ())
        self.assertIn("未启用交通线路拓扑门禁", profile.gate_reasons[0])
        self.assertFalse(_is_transport_operation_context("叮叮打卡 APP 企业人力资源与移动考勤 员工班次排班"))

    def test_transport_route_requires_explicit_route_evidence(self):
        profile = build_domain_profile(
            _task("公交干支线路径适配平台", product_type="智慧城市软件"),
            _blueprint(
                "智慧交通与运输线路调度",
                "维护干线支线、站点接驳、班次衔接和换乘规则",
                subtype_key="transport_route",
            ),
        )

        self.assertEqual(profile.key, "transport_route")
        self.assertTrue(profile.transport_related)
        self.assertTrue(profile.requires_route_topology)
        self.assertEqual(profile.enabled_gate_keys, ("ui_route_topology",))
        self.assertIn("干线、支线接驳和服务时窗", profile.gate_reasons[0])
        self.assertEqual(profile.to_dict()["enabled_gate_keys"], ("ui_route_topology",))
        self.assertTrue(_is_transport_operation_context("公交干线支线接驳平台"))

    def test_cold_chain_transport_is_not_route_topology_without_route_subtype(self):
        profile = build_domain_profile(
            _task("冷链温控监管系统", product_type="物联网软件", feature_hint="车辆运输轨迹、温湿度监测和超温告警"),
            _blueprint("冷链物流与环境监测", "追踪运输批次和车辆温控状态", subtype_key="cold_chain_iot"),
        )

        self.assertTrue(profile.transport_related)
        self.assertFalse(profile.requires_route_topology)

    def test_confirmed_non_route_subtype_overrides_overlapping_transport_terms(self):
        cases = [
            ("scenic_ticketing", "智慧景区票务通行", "票务订单、客流预警和闸机核验"),
            ("private_network", "5G专网运维", "基站站点、边缘节点和网络调度"),
            ("cold_chain_iot", "冷链物流监测", "运输批次、车辆轨迹和温控告警"),
        ]
        for subtype, industry, summary in cases:
            with self.subTest(subtype=subtype):
                profile = build_domain_profile(
                    _task(industry),
                    _blueprint(industry, summary, subtype_key=subtype),
                )
                self.assertEqual(profile.key, subtype)
                self.assertFalse(profile.requires_route_topology)

    def test_rail_construction_quality_is_not_transport_route(self):
        profile = build_domain_profile(
            _task("轨道交通施工质量分析系统", product_type="智慧城市软件"),
            _blueprint("轨道交通工程施工质量管理", "覆盖检验批、检验点、材料复检和整改验收"),
        )

        self.assertEqual(profile.key, "rail_construction_quality")
        self.assertFalse(profile.requires_route_topology)
        self.assertFalse(_is_transport_operation_context("轨道交通施工质量检验批整改验收"))

    def test_realism_check_uses_domain_profile_instead_of_weak_keyword(self):
        attendance = _ui_screenshot_realism_checks(
            primary_context="叮叮打卡 APP 企业人力资源与移动考勤 员工班次排班",
            html_text="今日班次 09:00 上班打卡 操作结果：已完成 操作日志 刷新统计",
            renderer="mobile_app",
        )
        transport = _ui_screenshot_realism_checks(
            primary_context="公交干支线路径适配平台 交通运输线路调度",
            html_text="线路运行看板 操作结果：已完成 操作日志 刷新统计",
            renderer="admin",
        )

        self.assertTrue(attendance["ui_route_topology_ready"])
        self.assertFalse(attendance["ui_route_topology_required"])
        self.assertFalse(transport["ui_route_topology_ready"])
        self.assertTrue(transport["ui_route_topology_required"])

    def test_weak_terms_do_not_become_transport_domain_signal(self):
        self.assertFalse(has_transport_domain_signal("员工排班、班次、流程节点和生产线路"))
        self.assertFalse(has_transport_domain_signal("医院患者转运运输和护理交接"))
        self.assertFalse(has_transport_domain_signal("道路测量运输控制点和线路断面"))
        self.assertTrue(has_transport_domain_signal("交通运输公交线路调度"))

    def test_cross_domain_weak_keyword_collision_matrix(self):
        cases = {
            "attendance_shift": "员工考勤班次、排班规则和上下班打卡",
            "medical_path": "患者诊疗路径、护理节点和班次交接",
            "manufacturing_line": "生产产线、工序节点、排程和换线调度",
            "workflow_node": "审批流程节点、处理路径和任务调度",
            "survey_route": "道路测量线路、控制点、断面和高程",
        }
        for label, text in cases.items():
            with self.subTest(label=label):
                profile = build_domain_profile(context_text=text)
                self.assertFalse(profile.requires_route_topology)

    def test_source_and_screenshot_module_helpers_share_domain_profile(self):
        attendance = SimpleNamespace(
            title="班次与员工排班",
            description="维护考勤班次、工作日、员工排班和上下班打卡窗口",
            data_fields=["班次编号", "员工姓名", "考勤日期"],
        )
        transport = SimpleNamespace(
            title="干支线路径适配",
            description="维护公交干线、支线接驳和换乘站点",
            data_fields=["干线编号", "支线编号", "接驳时窗"],
        )

        self.assertFalse(_ui_transport_module(attendance))
        self.assertFalse(_is_transport_module(attendance))
        self.assertTrue(_ui_transport_module(transport))
        self.assertTrue(_is_transport_module(transport))


if __name__ == "__main__":
    unittest.main()
