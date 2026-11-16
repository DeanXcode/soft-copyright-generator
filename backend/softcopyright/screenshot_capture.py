from __future__ import annotations

from pathlib import Path
import re
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .screenshots import UiScreenshot


def _unique_texts(values) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _render_url(item: UiScreenshot, base_url: str) -> str:
    if base_url:
        return f"{base_url.rstrip('/')}/{Path(item.html_path).name}"
    return Path(item.html_path).resolve().as_uri()


def _navigate_for_screenshot(page, url: str, *, project_server: bool) -> None:
    """Load a screenshot page without treating unrelated network quiet as readiness.

    Project pages expose ``window.__runtimeApiReady`` and are validated separately by
    ``_wait_for_page_runtime_api``. Waiting for Playwright's ``networkidle`` here can
    stall on harmless 404 probes, redirects, or long-lived connections even though
    the business API has already completed.
    """
    page.goto(url, wait_until="domcontentloaded" if project_server else "load")


def _wait_for_page_runtime_api(page, item: UiScreenshot) -> None:
    try:
        page.wait_for_function(
            "() => window.__runtimeApiReady === true || window.__runtimeApiError",
            timeout=12000,
        )
        fetches = page.evaluate("() => window.__runtimeApiFetches || []")
        visible_match = page.evaluate("() => Boolean(window.__runtimeApiVisibleMatch)")
        error = page.evaluate("() => window.__runtimeApiError || ''")
    except Exception as exc:
        raise RuntimeError(f"{item.key} 页面未完成生成项目接口加载：{exc}") from exc
    if error:
        raise RuntimeError(f"{item.key} 页面生成项目接口加载失败：{error}")
    if not isinstance(fetches, list) or not any(fetch.get("ok") for fetch in fetches if isinstance(fetch, dict)):
        raise RuntimeError(f"{item.key} 页面未命中生成项目业务接口")
    if item.page_kind not in {"login"} and not visible_match:
        raise RuntimeError(f"{item.key} 页面接口数据未写入可见业务区域")
    item.runtime_fetches = [
        {
            "url": str(fetch.get("url") or ""),
            "ok": bool(fetch.get("ok")),
            "status": int(fetch.get("status") or 0),
            "record_count": int(fetch.get("recordCount") or 0),
            "source": str(fetch.get("source") or ""),
            "visible_match": bool(fetch.get("visibleMatch")),
        }
        for fetch in fetches
        if isinstance(fetch, dict) and fetch.get("ok")
    ]

def _normalize_visible_action_label(value: Any) -> str:
    label = re.sub(r"\s+", " ", str(value or "")).strip(" ·|｜:：-—")
    label = re.sub(r"\s*[→←›»>]+\s*$", "", label).strip()
    if not label or not re.search(r"[0-9A-Za-z\u4e00-\u9fff]", label):
        return ""
    compact = re.sub(r"\s+", "", label)
    if (
        4 <= len(compact) <= 8
        and re.fullmatch(r"[0-9A-Za-z]+", compact)
        and re.search(r"[A-Za-z]", compact)
        and re.search(r"\d", compact)
    ):
        return ""
    return label


def _normalize_visible_content_summary(payload: dict[str, Any] | None, item: UiScreenshot | None = None) -> dict[str, Any]:
    raw = payload if isinstance(payload, dict) else {}

    def is_device_chrome(text: str) -> bool:
        compact = re.sub(r"\s+", " ", str(text or "")).strip()
        return bool(
            re.fullmatch(
                r"(?:\d{1,2}:\d{2}\s*)?(?:(?:4G|5G|LTE|Wi-?Fi)\s*)?(?:\d{1,3}%?)?",
                compact,
                flags=re.I,
            )
            and (":" in compact or re.search(r"(?:4G|5G|LTE|Wi-?Fi|%)", compact, flags=re.I))
        )

    def clean(value: Any, *, max_length: int = 40) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip(" ·|｜:：-—")
        if not text or len(text) > max_length or re.fullmatch(r"[\d\s.,%+\-/:]+", text):
            return ""
        if re.search(r"(?:soft-runtime|runtime-generated|source-ui-evidence|generated_source|ui-prototype)", text, flags=re.I):
            return ""
        return text

    def values(name: str, *, limit: int, max_length: int = 40) -> list[str]:
        result: list[str] = []
        for value in raw.get(name) or []:
            label = clean(value, max_length=max_length)
            if name in {"actions", "filter_actions"}:
                label = _normalize_visible_action_label(label)
            if name == "statuses" and is_device_chrome(label):
                continue
            if not label:
                continue
            if name == "filters" and not re.search(r"[\u4e00-\u9fff]", label):
                continue
            if any(label == existing or (len(label) >= 4 and label in existing) for existing in result):
                continue
            result.append(label)
            if len(result) >= limit:
                break
        return result

    visible_text = re.sub(r"\s+", " ", str(raw.get("visible_text") or "")).strip()
    if len(visible_text) > 16000:
        visible_text = visible_text[:16000]
    actions = values("actions", limit=12, max_length=24)
    if item is not None:
        title = clean(item.title, max_length=72)
        if visible_text and title and not any(str(value).strip() for value in raw.get("headings", [])):
            raw["headings"] = [title]
        if visible_text and item.interaction_input_fields and not item.requires_confirmation:
            raw_fields = list(raw.get("fields") or [])
            raw_fields.extend(str(value) for value in item.interaction_input_fields if str(value).strip())
            raw["fields"] = raw_fields
        interaction_action = _normalize_visible_action_label(clean(item.interaction_action, max_length=24))
        if visible_text and interaction_action and interaction_action not in actions:
            actions.append(interaction_action)
        if item.key == "login":
            for login_action in ("登录并进入应用", "登录系统", "进入系统", "提交登录"):
                if login_action in visible_text and login_action not in actions:
                    actions.append(login_action)
        for label in (item.action_crops or {}):
            normalized = _normalize_visible_action_label(clean(label, max_length=24))
            if normalized and normalized not in actions:
                actions.append(normalized)
            if len(actions) >= 12:
                break
    raw_navigation = raw.get("navigation") if isinstance(raw.get("navigation"), dict) else {}

    def navigation_items(name: str, *, limit: int) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for value in raw_navigation.get(name) or []:
            if not isinstance(value, dict):
                continue
            key = clean(value.get("key"), max_length=64)
            label = clean(value.get("label"), max_length=40)
            page_key = clean(value.get("page_key"), max_length=64)
            if not key and not label:
                continue
            result.append({
                "key": key,
                "label": label,
                "page_key": page_key,
            })
            if len(result) >= limit:
                break
        return result

    navigation = {
        "schema_version": clean(raw_navigation.get("schema_version"), max_length=48),
        "ready": bool(raw_navigation.get("ready")),
        "level": clean(raw_navigation.get("level"), max_length=24),
        "hierarchy_signature": clean(raw_navigation.get("hierarchy_signature"), max_length=64),
        "active_primary_key": clean(raw_navigation.get("active_primary_key"), max_length=64),
        "active_secondary_key": clean(raw_navigation.get("active_secondary_key"), max_length=64),
        "back_target": clean(raw_navigation.get("back_target"), max_length=64),
        "primary_items": navigation_items("primary_items", limit=10),
        "secondary_items": navigation_items("secondary_items", limit=8),
        "breadcrumb": navigation_items("breadcrumb", limit=5),
    }
    navigation["ready"] = bool(
        navigation["ready"]
        and navigation["schema_version"]
        and navigation["level"]
        and len(navigation["primary_items"]) >= 2
        and len(navigation["breadcrumb"]) >= 2
    )
    summary = {
        "headings": values("headings", limit=10, max_length=72),
        "metrics": values("metrics", limit=10),
        "fields": values("fields", limit=14),
        "statuses": values("statuses", limit=10),
        "filters": values("filters", limit=10),
        "filter_actions": values("filter_actions", limit=10, max_length=24),
        "actions": actions,
        "visible_text": visible_text,
        "navigation": navigation,
    }
    summary["semantic_terms"] = _unique_texts(
        value
        for name in ("headings", "metrics", "fields", "statuses", "filters", "actions")
        for value in summary[name]
    )[:48]
    summary["ready"] = bool(visible_text and (summary["headings"] or summary["metrics"] or summary["fields"] or actions))
    return summary


def _capture_visible_content_summary(page, item: UiScreenshot) -> dict[str, Any]:
    root_selector = (
        '[data-shared-confirm-dialog="true"][data-shared-confirm-ready="true"][role="dialog"]'
        if item.requires_confirmation
        else "body"
    )
    payload = page.evaluate(
        r"""
        (rootSelector) => {
          const clean = (value) => String(value || '').replace(/\s+/g, ' ').trim();
          const root = document.querySelector(rootSelector) || document.body;
          const visible = (element) => {
            if (!element) return false;
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden' && Number(style.opacity || 1) > 0
              && rect.width > 1 && rect.height > 1 && rect.bottom > 0 && rect.right > 0
              && rect.top < innerHeight && rect.left < innerWidth;
          };
          const unique = (values, limit = 30) => {
            const result = [];
            for (const value of values) {
              const text = clean(value);
              if (!text || result.includes(text)) continue;
              result.push(text);
              if (result.length >= limit) break;
            }
            return result;
          };
          const texts = (selector, limit = 40) => unique(
            Array.from(root.querySelectorAll(selector))
              .filter(visible)
              .map((element) => clean(element.innerText || element.value || element.getAttribute('aria-label') || ''))
              .filter((text) => text.length >= 2 && text.length <= 48),
            limit,
          );
          const headings = texts('h1,h2,h3,h4,[role="heading"],legend,[class*="panel-title"],[class*="card-title"],[class*="section-title"],[class*="block-title"],[class*="widget-title"]', 36);
          const fields = texts('th,label,dt,[data-field-label],[class*="field-label"],[class*="form-label"],[class*="meta-label"],[class*="item-label"],[class*="table-head"],.mobile-detail-list span,.mobile-result-list small,.shared-confirm-summary span,.shared-confirm-evidence>span,.shared-confirm-note strong', 48);
          const statuses = texts('[class*="status"]:not(.mobile-status),[class*="badge"],[class*="tag"],[class*="pill"],[class*="chip"],[class*="state"]', 36);
          const actions = unique(
            Array.from(root.querySelectorAll('button,a,[role="button"],input[type="button"],input[type="submit"],[onclick]'))
              .filter(visible)
              .map((element) => clean(
                element.getAttribute('aria-label')
                || element.getAttribute('title')
                || element.value
                || element.innerText
                || ''
              ))
              .filter((text) => text.length >= 2 && text.length <= 48),
            48,
          );
          const filterContainers = Array.from(root.querySelectorAll('[class~="filter-block"],[class*="filter-item"],[class*="filter-chip"],[class*="filter-option"],[class*="tab-item"],[class*="tab-button"],[class*="segment-item"],[class*="range-label"]')).filter(visible);
          const filters = unique(filterContainers.map((element) => clean(element.innerText)).filter((text) => text.length >= 2 && text.length <= 64), 36);
          const filterActions = unique(filterContainers.flatMap((element) => Array.from(element.querySelectorAll('button,[role="button"]')).filter(visible).map((button) => clean(button.innerText || button.getAttribute('aria-label') || ''))), 36);
          for (const input of Array.from(root.querySelectorAll('input,select,textarea')).filter(visible)) {
            const value = clean(input.getAttribute('placeholder') || input.value || input.getAttribute('aria-label') || '');
            if (value && value.length <= 48) filters.push(value);
          }
          const metrics = [];
          for (const card of Array.from(root.querySelectorAll('[class~="metric"],[class*="metric-"],[class*="_metric"],[class~="kpi"],[class*="kpi-"],[class*="_kpi"],[class~="stat"],[class*="stat-"],[class*="_stat"],[class~="indicator"],[class*="indicator-"],[class*="summary-card"]')).filter(visible)) {
            const labelNode = card.querySelector('[class*="label"],[class*="name"],[class*="title"],h1,h2,h3,h4,dt');
            const label = clean((labelNode && labelNode.innerText) || (card.innerText || '').split(/\n/)[0]);
            if (label && label.length >= 2 && label.length <= 48) metrics.push(label);
          }
          const navRoot = document.querySelector('[data-navigation-contract]');
          const navigationItems = (selector, limit = 12) => navRoot ? Array.from(navRoot.querySelectorAll(selector)).slice(0, limit).map((element) => ({
            key: clean(element.getAttribute(selector.includes('primary') ? 'data-navigation-primary-item' : selector.includes('secondary') ? 'data-navigation-secondary-item' : 'data-navigation-breadcrumb-item')),
            label: clean(element.innerText || element.textContent || ''),
            page_key: clean(element.getAttribute('data-navigation-page-key') || ''),
          })) : [];
          const navigation = navRoot ? {
            schema_version: clean(navRoot.getAttribute('data-navigation-contract') || ''),
            ready: navRoot.getAttribute('data-navigation-ready') === 'true',
            level: clean(navRoot.getAttribute('data-navigation-level') || ''),
            hierarchy_signature: clean(navRoot.getAttribute('data-navigation-signature') || ''),
            active_primary_key: clean(navRoot.getAttribute('data-navigation-active-primary') || ''),
            active_secondary_key: clean(navRoot.getAttribute('data-navigation-active-secondary') || ''),
            back_target: clean(navRoot.getAttribute('data-navigation-back-target') || navRoot.querySelector('[data-navigation-back-target]')?.getAttribute('data-navigation-back-target') || ''),
            primary_items: navigationItems('[data-navigation-primary-item]', 10),
            secondary_items: navigationItems('[data-navigation-secondary-item]', 8),
            breadcrumb: navigationItems('[data-navigation-breadcrumb-item]', 5),
          } : {};
          return {
            visible_text: clean(root && root.innerText),
            headings: unique(headings, 36),
            metrics: unique(metrics, 36),
            fields: unique(fields, 48),
            statuses: unique(statuses, 36),
            filters: unique(filters, 36),
            filter_actions: unique(filterActions, 36),
            actions: unique(actions, 48),
            navigation,
          };
        }
        """,
        root_selector,
    )
    return _normalize_visible_content_summary(payload, item)


def _capture_visible_action_crops(page, item: UiScreenshot, ui_dir: Path) -> dict[str, str]:
    crop_dir = ui_dir / "button-crops"
    crop_dir.mkdir(parents=True, exist_ok=True)
    scope = (
        page.locator('[data-shared-confirm-dialog="true"][data-shared-confirm-ready="true"][role="dialog"]')
        if item.requires_confirmation
        else page.locator("body")
    )
    candidate_groups = [
        scope.locator('button, a, [role="button"], input[type="button"], input[type="submit"]'),
        scope.locator('[onclick], [class*="btn"], [class*="button"], [class*="action"], [class*="primary"], [class*="submit"]'),
    ]
    result: dict[str, str] = {}
    for group_index, candidates in enumerate(candidate_groups):
        try:
            count = min(candidates.count(), 200)
        except Exception:
            continue
        for index in range(count):
            locator = candidates.nth(index)
            try:
                if not locator.is_visible():
                    continue
                interactive = locator.evaluate(
                    "element => ['BUTTON','A','INPUT'].includes(element.tagName) || "
                    "element.getAttribute('role') === 'button' || element.hasAttribute('onclick')"
                )
                if not interactive:
                    continue
                label = (
                    locator.get_attribute("aria-label")
                    or locator.get_attribute("title")
                    or locator.get_attribute("value")
                    or locator.inner_text()
                    or ""
                )
                label = _normalize_visible_action_label(label)
                box = locator.bounding_box()
                if not label or len(label) > 16 or label in result or not box or not _is_action_crop_label(label):
                    continue
                if box["width"] < 18 or box["height"] < 14 or box["width"] > 720 or box["height"] > 100:
                    continue
                safe_label = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", label).strip("-") or f"action-{group_index + 1}-{index + 1}"
                crop_path = crop_dir / f"{item.key}-{safe_label[:24]}.png"
                locator.screenshot(path=str(crop_path))
                if not _action_crop_has_visible_content(crop_path):
                    crop_path.unlink(missing_ok=True)
                    continue
                _normalize_action_crop_image(crop_path)
                result[label] = str(crop_path)
            except Exception:
                continue
    return result


def _normalize_action_crop_image(path: Path, *, canvas_height: int = 40, content_height: int = 32) -> None:
    try:
        from PIL import Image

        with Image.open(path) as source:
            image = source.convert("RGBA")
        if image.width <= 0 or image.height <= 0:
            return
        scale = min(content_height / image.height, 340 / image.width)
        width = max(1, round(image.width * scale))
        height = max(1, round(image.height * scale))
        resized = image.resize((width, height), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", (width + 8, canvas_height), (255, 255, 255, 0))
        canvas.alpha_composite(resized, (4, max(0, (canvas_height - height) // 2)))
        canvas.save(path)
    except Exception:
        return


def _is_action_crop_label(label: str) -> bool:
    text = re.sub(r"\s+", "", str(label or ""))
    if not text or text in {
        "操作", "状态", "已启用", "待启用", "待评估", "有冲突", "已适配", "处理中", "已完成",
        "已归档", "正常", "异常", "在线", "离线", "成功", "失败",
    }:
        return False
    return bool(
        re.search(
            r"登录|进入|查询|搜索|筛选|重置|保存|新增|添加|登记|录入|创建|编辑|修改|配置|"
            r"导入|上传|导出|下载|打印|校验|核验|检验|评定|审核|复核|确认|发布|下发|提交|"
            r"处置|整改|调度|排程|预警|追踪|跟踪|统计|分析|归档|删除|失效|打开|查看|"
            r"详情|关闭|取消|返回|刷新|同步|定位|分派|流转|研判|留痕|更新|重试|播放|收藏",
            text,
        )
    )


def _action_crop_has_visible_content(path: Path) -> bool:
    try:
        from PIL import Image, ImageStat
    except ImportError:
        return True
    try:
        with Image.open(path) as source:
            image = source.convert("RGB")
            width, height = image.size
            if width < 18 or height < 14:
                return False
            inset_x = max(2, min(width // 8, 12))
            inset_y = max(2, min(height // 8, 8))
            interior = image.crop((inset_x, inset_y, width - inset_x, height - inset_y))
            quantized = interior.quantize(colors=16)
            colors = quantized.getcolors(maxcolors=16) or []
            if not colors:
                return False
            _, dominant_index = max(colors)
            palette = quantized.getpalette() or []
            offset = dominant_index * 3
            dominant = tuple(palette[offset : offset + 3])
            pixel_map = interior.load()
            pixels = [pixel_map[x, y] for y in range(interior.height) for x in range(interior.width)]
            informative = sum(
                1 for pixel in pixels if max(abs(int(pixel[channel]) - int(dominant[channel])) for channel in range(3)) >= 18
            )
            informative_ratio = informative / max(len(pixels), 1)
            luminance_stddev = float(ImageStat.Stat(interior.convert("L")).stddev[0])
            return informative_ratio >= 0.008 and luminance_stddev >= 2.5
    except Exception:
        return False
