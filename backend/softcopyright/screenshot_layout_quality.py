from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .screenshots import UiScreenshot


def _assert_screenshot_content_geometry(image_path: Path, renderer: str, item: UiScreenshot) -> None:
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return
    try:
        with Image.open(image_path) as image:
            rgb = image.convert("RGB")
            width, height = rgb.size
            corner = rgb.crop((max(0, width - 10), max(0, height - 10), width, height)).resize((width, height))
            diff = ImageChops.difference(rgb, corner)
            bbox = diff.getbbox()
    except Exception as exc:
        raise RuntimeError(f"{item.key} 截图几何质量检查失败：{exc}") from exc
    if not bbox:
        raise RuntimeError(f"{item.key} 截图为空白，已停止生成。")
    left, top, right, bottom = bbox
    content_width_ratio = (right - left) / max(width, 1)
    content_height_ratio = (bottom - top) / max(height, 1)
    if renderer == "admin":
        if content_width_ratio < 0.74 or right < int(width * 0.78):
            raise RuntimeError(
                f"{item.key} 截图有效内容宽度不足，疑似界面被压缩或右侧大面积空白："
                f"content_width_ratio={content_width_ratio:.2f}, right={right}/{width}"
            )
        if content_height_ratio < 0.68:
            raise RuntimeError(
                f"{item.key} 截图有效内容高度不足，疑似页面未正常铺满：content_height_ratio={content_height_ratio:.2f}"
            )
    else:
        if content_width_ratio < 0.62 or content_height_ratio < 0.62:
            raise RuntimeError(
                f"{item.key} 移动/游戏截图有效内容区域不足："
                f"{content_width_ratio:.2f}x{content_height_ratio:.2f}"
            )


def _auto_repair_page_text_layout(page, renderer: str) -> None:
    if renderer in {"mobile_app", "game"}:
        return
    page.evaluate(
        """() => {
          if (document.getElementById("soft-auto-layout-repair")) return;
          const style = document.createElement("style");
          style.id = "soft-auto-layout-repair";
          style.textContent = `
body[data-renderer="admin"],body[data-ai-frontend="true"][data-renderer="admin"]{width:1280px!important;height:720px!important;min-height:720px!important;overflow:hidden!important;}
body[data-renderer="admin"] *{box-sizing:border-box!important;min-width:0;}
body[data-renderer="admin"] :is(button,.btn,.mini-btn,.tab,.nav-item,.tag,.badge,th,td,.metric,.mcell,.rec,.meta,.source-list div,.runtime-record-panel b,.code,.num,.val,.operation-result){max-width:100%!important;overflow:hidden!important;text-overflow:ellipsis!important;}
body[data-renderer="admin"] :is(button,.btn,.mini-btn,.tab,.nav-item,.tag,.badge,th,td,.runtime-record-panel b,.code,.num,.val){white-space:nowrap!important;}
body[data-renderer="admin"] :is(button,.btn,.mini-btn,.opbtn){height:20px!important;min-height:20px!important;max-height:20px!important;font-size:11px!important;line-height:1!important;padding-top:0!important;padding-bottom:0!important;}
body[data-renderer="admin"] :is(.tag,.badge){height:18px!important;min-height:18px!important;max-height:18px!important;font-size:10px!important;line-height:1!important;padding-top:0!important;padding-bottom:0!important;}
body[data-renderer="admin"] :is(th,td){height:26px!important;max-height:26px!important;line-height:1.05!important;padding-top:0!important;padding-bottom:0!important;}
body[data-renderer="admin"] :is(table){table-layout:fixed!important;border-collapse:collapse!important;}
body[data-renderer="admin"] :is(.stable-card,.panel,.dialog,.table-frame,.stable-workspace,.main,.workspace,.content){overflow:hidden!important;}
body[data-renderer="admin"] .work-area{min-height:0!important;grid-template-rows:minmax(0,1fr)!important;overflow:hidden!important;}
body[data-renderer="admin"] .screen-root>.metric-strip{flex:0 0 auto!important;height:auto!important;min-height:0!important;max-height:86px!important;overflow:hidden!important;}
body[data-renderer="admin"] .workspace{grid-template-rows:minmax(0,1fr)!important;}
body[data-renderer="admin"] :is(.work-area,.workspace,.content)>.detail-panel.operation-result{height:100%!important;min-height:0!important;max-height:100%!important;overflow:hidden!important;}
body[data-renderer="admin"] .detail-panel.operation-result>.detail-grid{flex:1 1 0%!important;min-height:0!important;grid-template-rows:minmax(0,1.03fr) minmax(0,.97fr)!important;overflow:hidden!important;}
body[data-renderer="admin"] .comparison-main:has(>.table-panel.operation-result){height:100%!important;min-height:0!important;grid-template-rows:minmax(0,1fr) minmax(0,170px)!important;overflow:hidden!important;}
body[data-renderer="admin"] .comparison-main>.table-panel.operation-result{height:100%!important;min-height:0!important;max-height:170px!important;overflow:hidden!important;}
body[data-renderer="admin"] .workspace>.execution-rail{height:100%!important;min-height:0!important;max-height:100%!important;overflow:hidden!important;}
body[data-renderer="admin"] .operation-result:not(:has(> *)){white-space:normal!important;display:-webkit-box!important;-webkit-line-clamp:2;-webkit-box-orient:vertical;line-height:1.22!important;max-height:42px!important;}
body[data-renderer="admin"] :is(.map-pin,.map-node,.relation-node,.flow-node) :is(b,strong,span,em){display:block!important;min-width:0!important;max-width:100%!important;white-space:nowrap!important;word-break:keep-all!important;overflow:hidden!important;text-overflow:ellipsis!important;}
body[data-renderer="admin"][data-page-kind="login"] :is(.left-console,.login-hero,.login-brand) h1{max-width:none!important;font-size:31px!important;line-height:1.15!important;white-space:nowrap!important;word-break:keep-all!important;overflow:hidden!important;text-overflow:ellipsis!important;}
          `;
          document.head.appendChild(style);
        }"""
    )
    for _ in range(5):
        issues = _collect_page_text_layout_issues(page, include_overlaps=True)
        if not issues:
            return
        page.evaluate(
            """(issues) => {
              const selector = [
                "button", ".btn", ".mini-btn", ".tab", ".nav-item", ".tag", ".badge",
                "th", "td", ".metric", ".mcell", ".rec", ".meta", ".source-list div",
                ".runtime-record-panel b", ".code", ".num", ".val", ".operation-result"
              ].join(",");
              const nodes = Array.from(document.querySelectorAll(selector));
              const allNodes = Array.from(document.querySelectorAll("*"));
              const issueIndexes = new Set();
              for (const issue of issues || []) {
                if (Number.isInteger(issue.index)) issueIndexes.add(issue.index);
                if (Number.isInteger(issue.a)) issueIndexes.add(issue.a);
                if (Number.isInteger(issue.b)) issueIndexes.add(issue.b);
              }
              for (const index of issueIndexes) {
                const node = nodes[index];
                if (!node) continue;
                node.dataset.layoutRepaired = "true";
                node.style.minWidth = "0";
                node.style.maxWidth = "100%";
                node.style.overflow = "hidden";
                node.style.textOverflow = "ellipsis";
                node.style.boxSizing = "border-box";
                const style = getComputedStyle(node);
                const size = Number.parseFloat(style.fontSize || "12");
                if (size > 10) node.style.fontSize = `${Math.max(10, size - 1)}px`;
                node.style.lineHeight = "1.05";
                if (node.matches("button,.btn,.mini-btn,.opbtn")) {
                  node.style.height = "18px";
                  node.style.minHeight = "18px";
                  node.style.maxHeight = "18px";
                  node.style.paddingTop = "0";
                  node.style.paddingBottom = "0";
                }
                if (node.matches(".tag,.badge")) {
                  node.style.height = "17px";
                  node.style.minHeight = "17px";
                  node.style.maxHeight = "17px";
                  node.style.paddingLeft = "5px";
                  node.style.paddingRight = "5px";
                }
                if (node.matches("th,td")) {
                  node.style.height = "24px";
                  node.style.maxHeight = "24px";
                  node.style.paddingTop = "0";
                  node.style.paddingBottom = "0";
                }
                const container = node.closest(".stable-card,.panel,.dialog,.table-frame,.stable-workspace,.main,.workspace,.content");
                if (container) {
                  container.style.minHeight = "0";
                  container.style.overflow = "hidden";
                }
              }
              for (const issue of issues || []) {
                if (issue.kind !== "occlusion" || !Number.isInteger(issue.occluderIndex)) continue;
                const occluder = allNodes[issue.occluderIndex];
                if (!occluder) continue;
                occluder.dataset.layoutOccluderHidden = "true";
                occluder.style.setProperty("visibility", "hidden", "important");
              }
              for (const issue of issues || []) {
                if (issue.kind !== "overlap" || !Number.isInteger(issue.b)) continue;
                const node = nodes[issue.b];
                if (!node) continue;
                const overlap = Array.isArray(issue.overlap) ? issue.overlap : [0, 0, 0, 0];
                const push = Math.max(6, Number(overlap[3] || 0) - Number(overlap[1] || 0) + 4);
                const style = getComputedStyle(node);
                if (style.position === "absolute" || style.position === "fixed") {
                  const currentTop = Number.parseFloat(style.top);
                  node.style.top = `${(Number.isFinite(currentTop) ? currentTop : node.offsetTop) + push}px`;
                }
              }
              const outsideRects = (issues || [])
                .filter((issue) => issue.kind === "outsideViewport" && Array.isArray(issue.rect))
                .map((issue) => issue.rect);
              if (outsideRects.length) {
                const maxRight = Math.max(window.innerWidth, ...outsideRects.map((rect) => Number(rect[2] || 0)));
                const maxBottom = Math.max(window.innerHeight, ...outsideRects.map((rect) => Number(rect[3] || 0)));
                const fitScale = Math.max(
                  0.92,
                  Math.min(1, (window.innerWidth - 2) / maxRight, (window.innerHeight - 2) / maxBottom)
                );
                if (fitScale < 0.999) {
                  const app = document.querySelector(".generated-product") || document.querySelector(".screen-root") || document.body.firstElementChild;
                  if (app) {
                    const currentScale = Number.parseFloat(app.dataset.viewportFitScale || "1") || 1;
                    const nextScale = Math.max(0.88, Math.min(currentScale, currentScale * fitScale));
                    app.dataset.viewportFitScale = nextScale.toFixed(4);
                    app.style.transformOrigin = "top left";
                    app.style.transform = `scale(${nextScale})`;
                  }
                }
              }
              const html = document.documentElement;
              const body = document.body;
              const overflowX = Math.max(html.scrollWidth, body.scrollWidth) - window.innerWidth;
              const overflowY = Math.max(html.scrollHeight, body.scrollHeight) - window.innerHeight;
              if (overflowX > 4 || overflowY > 4) {
                const scale = Math.max(0.94, Math.min(1, window.innerWidth / Math.max(html.scrollWidth, body.scrollWidth), window.innerHeight / Math.max(html.scrollHeight, body.scrollHeight)));
                body.style.transformOrigin = "top left";
                body.style.transform = `scale(${scale})`;
                body.style.width = `${Math.ceil(window.innerWidth / scale)}px`;
                body.style.height = `${Math.ceil(window.innerHeight / scale)}px`;
              }
            }""",
            issues,
        )


def _assert_page_text_layout_quality(page, item: UiScreenshot, renderer: str) -> None:
    if renderer in {"mobile_app", "game"}:
        metrics = _mobile_canvas_metrics(page)
        if not _mobile_canvas_width_ready(metrics):
            raise RuntimeError(
                f"{item.key} 手机页面内容壳未铺满 720px 画布："
                f"{metrics.get('className') or metrics.get('selector') or 'unknown'} "
                f"width={metrics.get('width', 0)} left={metrics.get('left', 0)} right={metrics.get('right', 0)}；"
                "禁止使用 375/390/430px 窄手机模拟框。"
            )
        return
    issues = _collect_page_text_layout_issues(page, include_overlaps=True)
    if issues:
        summary = "; ".join(
            f"{issue.get('tag')}.{issue.get('className')}: {issue.get('text') or issue.get('kind')}"
            for issue in issues[:4]
            if isinstance(issue, dict)
        )
        raise RuntimeError(f"{item.key} 页面存在文字溢出、越界或重叠：{summary}")


def _mobile_canvas_metrics(page) -> dict:
    return page.evaluate(
        """() => {
          const viewportWidth = window.innerWidth || 720;
          const viewportHeight = window.innerHeight || 1280;
          const selectors = [".phone", ".phone-shell", ".mobile-shell", ".app-shell", ".mobile-screen", ".game-frame"];
          const candidates = selectors.flatMap((selector) => Array.from(document.querySelectorAll(selector)).map((node) => ({selector, node})))
            .map(({selector, node}) => ({selector, node, rect: node.getBoundingClientRect()}))
            .filter(({rect}) => rect.width > 40 && rect.height >= viewportHeight * 0.6 && rect.bottom > 0 && rect.top < viewportHeight)
            .sort((a, b) => (b.rect.width * b.rect.height) - (a.rect.width * a.rect.height));
          const selected = candidates[0] || (() => {
            const node = document.querySelector(".screen-root") || document.querySelector("#root") || document.body.firstElementChild || document.body;
            return {selector: ".screen-root", node, rect: node.getBoundingClientRect()};
          })();
          return {
            selector: selected.selector,
            className: String(selected.node.className || "").slice(0, 120),
            width: Math.round(selected.rect.width),
            height: Math.round(selected.rect.height),
            left: Math.round(selected.rect.left),
            right: Math.round(selected.rect.right),
            viewportWidth,
            viewportHeight
          };
        }"""
    )


def _mobile_canvas_width_ready(metrics: dict | None) -> bool:
    values = metrics if isinstance(metrics, dict) else {}
    width = float(values.get("width") or 0)
    left = float(values.get("left") or 0)
    right = float(values.get("right") or 0)
    viewport_width = float(values.get("viewportWidth") or 720)
    return width >= min(680, viewport_width - 40) and left <= 20 and right >= viewport_width - 20


def _collect_page_text_layout_issues(page, *, include_overlaps: bool = False) -> list[dict]:
    return page.evaluate(
        """(includeOverlaps) => {
          const viewportWidth = window.innerWidth || 1280;
          const viewportHeight = window.innerHeight || 720;
          const selector = [
            "button", ".btn", ".mini-btn", ".tab", ".nav-item", ".tag", ".badge",
            "th", "td", ".metric", ".mcell", ".rec", ".meta", ".source-list div",
            ".runtime-record-panel b", ".code", ".num", ".val", ".operation-result"
          ].join(",");
          const items = [];
          const viewportTolerance = 4;
          const directText = (node) => Array.from(node.childNodes || [])
            .filter((child) => child.nodeType === Node.TEXT_NODE)
            .map((child) => child.textContent || "")
            .join("")
            .trim();
          const paintedRect = (node, sourceRect) => {
            const rect = {
              left: sourceRect.left,
              top: sourceRect.top,
              right: sourceRect.right,
              bottom: sourceRect.bottom
            };
            for (let ancestor = node.parentElement; ancestor && ancestor !== document.body && ancestor !== document.documentElement; ancestor = ancestor.parentElement) {
              const style = getComputedStyle(ancestor);
              const ancestorRect = ancestor.getBoundingClientRect();
              if (["hidden", "clip", "auto", "scroll"].includes(style.overflowX)) {
                rect.left = Math.max(rect.left, ancestorRect.left);
                rect.right = Math.min(rect.right, ancestorRect.right);
              }
              if (["hidden", "clip", "auto", "scroll"].includes(style.overflowY)) {
                rect.top = Math.max(rect.top, ancestorRect.top);
                rect.bottom = Math.min(rect.bottom, ancestorRect.bottom);
              }
            }
            return {
              ...rect,
              width: Math.max(0, rect.right - rect.left),
              height: Math.max(0, rect.bottom - rect.top)
            };
          };
          const nodes = Array.from(document.querySelectorAll(selector));
          const visible = [];
          for (let index = 0; index < nodes.length; index += 1) {
            const node = nodes[index];
            const sourceRect = node.getBoundingClientRect();
            const rect = paintedRect(node, sourceRect);
            if (rect.width < 3 || rect.height < 3) continue;
            if (rect.bottom <= 0 || rect.right <= 0 || rect.top >= viewportHeight || rect.left >= viewportWidth) continue;
            const text = (directText(node) || node.innerText || "").replace(/\\s+/g, " ").trim();
            if (!text || text.length < 2) continue;
            const style = getComputedStyle(node);
            const visibleOverflowX = style.overflowX === "visible" && node.scrollWidth > node.clientWidth + 2;
            const visibleOverflowY = style.overflowY === "visible" && node.scrollHeight > node.clientHeight + 2;
            const outsideViewport = (
              rect.left < -viewportTolerance ||
              rect.top < -viewportTolerance ||
              rect.right > viewportWidth + viewportTolerance ||
              rect.bottom > viewportHeight + viewportTolerance
            );
            if (visibleOverflowX || visibleOverflowY || outsideViewport) {
              items.push({
                tag: node.tagName.toLowerCase(),
                className: String(node.className || "").slice(0, 80),
                text: text.slice(0, 40),
                index,
                kind: visibleOverflowX || visibleOverflowY ? "overflow" : "outsideViewport",
                overflowX: visibleOverflowX,
                overflowY: visibleOverflowY,
                outsideViewport,
                rect: [Math.round(rect.left), Math.round(rect.top), Math.round(rect.right), Math.round(rect.bottom)],
                scroll: [node.scrollWidth, node.scrollHeight],
                client: [node.clientWidth, node.clientHeight]
              });
            }
            visible.push({node, index, rect, text});
            if (items.length >= 8) break;
          }
          if (includeOverlaps && items.length < 8) {
            const modalBoundarySelector = [
              ".confirm-drawer", ".detail-drawer", ".confirm-panel",
              "[class*='modal']", "[class*='dialog']", "[role='dialog']"
            ].join(",");
            for (let i = 0; i < visible.length; i += 1) {
              for (let j = i + 1; j < visible.length; j += 1) {
                const a = visible[i];
                const b = visible[j];
                if (a.node.contains(b.node) || b.node.contains(a.node)) continue;
                const aModal = a.node.closest(modalBoundarySelector);
                const bModal = b.node.closest(modalBoundarySelector);
                if (aModal !== bModal && (aModal || bModal)) continue;
                const aPosition = getComputedStyle(a.node).position;
                const bPosition = getComputedStyle(b.node).position;
                if (![aPosition, bPosition].some((value) => value === "absolute" || value === "fixed")) continue;
                const left = Math.max(a.rect.left, b.rect.left);
                const right = Math.min(a.rect.right, b.rect.right);
                const top = Math.max(a.rect.top, b.rect.top);
                const bottom = Math.min(a.rect.bottom, b.rect.bottom);
                const width = right - left;
                const height = bottom - top;
                if (width <= 2 || height <= 2) continue;
                const area = width * height;
                const minArea = Math.min(a.rect.width * a.rect.height, b.rect.width * b.rect.height);
                if (area < 28 || area / Math.max(minArea, 1) < 0.18) continue;
                items.push({
                  tag: a.node.tagName.toLowerCase(),
                  className: String(a.node.className || "").slice(0, 80),
                  text: `${a.text.slice(0, 18)} / ${b.text.slice(0, 18)}`,
                  kind: "overlap",
                  a: a.index,
                  b: b.index,
                  overlap: [Math.round(left), Math.round(top), Math.round(right), Math.round(bottom)]
                });
                if (items.length >= 8) return items;
              }
            }
          }
          if (includeOverlaps && items.length < 8) {
            const allNodes = Array.from(document.querySelectorAll("*"));
            const colorIsVisible = (value) => {
              const text = String(value || "").trim().toLowerCase();
              if (!text || text === "transparent") return false;
              const rgba = text.match(/^rgba?\\(([^)]+)\\)$/);
              if (!rgba) return true;
              const parts = rgba[1].split(",").map((part) => Number.parseFloat(part.trim()));
              return parts.length < 4 || !Number.isFinite(parts[3]) || parts[3] > 0.08;
            };
            const textLeaves = [];
            for (const node of allNodes) {
              if (["SCRIPT", "STYLE", "NOSCRIPT", "BR", "HR"].includes(node.tagName)) continue;
              const style = getComputedStyle(node);
              if (style.display === "none" || style.visibility === "hidden" || Number.parseFloat(style.opacity || "1") < 0.08) continue;
              const text = directText(node).replace(/\\s+/g, " ").trim();
              if (!text) continue;
              const rect = paintedRect(node, node.getBoundingClientRect());
              if (rect.width < 3 || rect.height < 3 || rect.bottom <= 0 || rect.right <= 0 || rect.top >= viewportHeight || rect.left >= viewportWidth) continue;
              textLeaves.push({node, rect, text});
            }
            for (let occluderIndex = 0; occluderIndex < allNodes.length; occluderIndex += 1) {
              const occluder = allNodes[occluderIndex];
              if (["HTML", "BODY", "SCRIPT", "STYLE", "NOSCRIPT"].includes(occluder.tagName)) continue;
              if ((occluder.innerText || "").trim() || occluder.getAttribute("aria-label") || occluder.getAttribute("title")) continue;
              const style = getComputedStyle(occluder);
              if (style.display === "none" || style.visibility === "hidden" || Number.parseFloat(style.opacity || "1") < 0.08) continue;
              if (style.position !== "absolute" && style.position !== "fixed") continue;
              const hasVisibleBorder = (
                Number.parseFloat(style.borderTopWidth || "0") > 0 &&
                style.borderTopStyle !== "none" &&
                colorIsVisible(style.borderTopColor)
              );
              const hasVisualFill = (
                style.backgroundImage !== "none" ||
                colorIsVisible(style.backgroundColor) ||
                hasVisibleBorder ||
                ["CANVAS", "SVG", "IMG"].includes(occluder.tagName)
              );
              if (!hasVisualFill) continue;
              const rect = occluder.getBoundingClientRect();
              if (rect.width < 4 || rect.height < 4 || rect.width * rect.height < 24) continue;
              if (rect.bottom <= 0 || rect.right <= 0 || rect.top >= viewportHeight || rect.left >= viewportWidth) continue;
              for (const textItem of textLeaves) {
                if (occluder.contains(textItem.node) || textItem.node.contains(occluder)) continue;
                const left = Math.max(rect.left, textItem.rect.left);
                const right = Math.min(rect.right, textItem.rect.right);
                const top = Math.max(rect.top, textItem.rect.top);
                const bottom = Math.min(rect.bottom, textItem.rect.bottom);
                const width = right - left;
                const height = bottom - top;
                if (width <= 1 || height <= 1) continue;
                const area = width * height;
                const textArea = Math.max(1, textItem.rect.width * textItem.rect.height);
                if (area < 18 || area / textArea < 0.08) continue;
                const points = [
                  [(left + right) / 2, (top + bottom) / 2],
                  [left + Math.min(2, width / 2), (top + bottom) / 2],
                  [right - Math.min(2, width / 2), (top + bottom) / 2]
                ];
                const paintsAboveText = points.some(([x, y]) => {
                  const stack = document.elementsFromPoint(x, y);
                  const occluderOrder = stack.findIndex((element) => element === occluder || occluder.contains(element));
                  const textOrder = stack.findIndex((element) => element === textItem.node || textItem.node.contains(element));
                  return occluderOrder >= 0 && (textOrder < 0 || occluderOrder < textOrder);
                });
                if (!paintsAboveText) continue;
                items.push({
                  tag: occluder.tagName.toLowerCase(),
                  className: String(occluder.className || "").slice(0, 80),
                  text: textItem.text.slice(0, 40),
                  kind: "occlusion",
                  occluderIndex,
                  overlap: [Math.round(left), Math.round(top), Math.round(right), Math.round(bottom)]
                });
                if (items.length >= 8) return items;
                break;
              }
            }
          }
          return items;
        }""",
        include_overlaps,
    )
