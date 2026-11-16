from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SecondaryInteraction:
    action: str
    surface: str
    caption: str
    requires_confirmation: bool = False

    @property
    def mode(self) -> str:
        return "confirm" if self.requires_confirmation else "instant"


def mobile_secondary_interaction(module: Any) -> SecondaryInteraction:
    title = str(getattr(module, "title", "") or "")
    description = str(getattr(module, "description", "") or "")
    pages = " ".join(str(item) for item in (getattr(module, "pages", None) or []))
    text = f"{title} {description} {pages}"

    if "搜索" in title:
        return SecondaryInteraction("查看搜索结果", "search_results", "输入关键词后展示匹配歌曲、歌手和专辑，可继续筛选或播放。")
    if "歌词" in title:
        return SecondaryInteraction("查看歌词", "lyrics_view", "进入歌词页后同步当前播放进度，高亮当前歌词并支持滚动定位。")
    if "下载" in title:
        return SecondaryInteraction("下载歌曲", "download_options", "选择音质后开始下载，页面直接显示下载进度、暂停和继续入口。")
    if "播放队列" in title or "队列" in title:
        return SecondaryInteraction("调整播放顺序", "queue_editor", "打开播放队列后可拖动调整顺序、切换歌曲或移除队列项。")
    if "歌曲播放" in title or title.endswith("播放"):
        return SecondaryInteraction("播放歌曲", "player", "点击播放后立即进入播放页，可暂停、切歌、拖动进度或切换播放模式。")
    if "收藏" in title or "歌单" in title:
        return SecondaryInteraction("收藏歌单", "favorite_state", "点击收藏后立即更新收藏状态，并可进入歌单详情继续浏览歌曲。")
    if "歌手" in title:
        return SecondaryInteraction("查看歌手详情", "artist_detail", "进入歌手详情页查看简介、热门歌曲和专辑，并可直接试听。")
    if "专辑" in title:
        return SecondaryInteraction("查看专辑详情", "album_detail", "进入专辑详情页查看发行信息和曲目列表，并可播放全部歌曲。")
    if "本地音乐" in title or "本地歌曲" in title:
        return SecondaryInteraction("播放本地歌曲", "local_player", "选择本地歌曲后直接开始播放，并显示文件来源和播放状态。")
    if "推荐" in title or "记录" in title:
        return SecondaryInteraction("查看推荐内容", "recommendation_detail", "进入推荐页查看最近播放和个性化内容，可直接播放或收藏。")

    if "搜索" in text:
        return SecondaryInteraction("查看搜索结果", "search_results", "输入关键词后展示匹配歌曲、歌手和专辑，可继续筛选或播放。")
    if "歌词" in text:
        return SecondaryInteraction("查看歌词", "lyrics_view", "进入歌词页后同步当前播放进度，高亮当前歌词并支持滚动定位。")
    if "下载" in text or "离线" in text:
        return SecondaryInteraction("下载歌曲", "download_options", "选择音质后开始下载，页面直接显示下载进度、暂停和继续入口。")
    if "播放队列" in text or "队列" in text:
        return SecondaryInteraction("调整播放顺序", "queue_editor", "打开播放队列后可拖动调整顺序、切换歌曲或移除队列项。")
    if "播放" in text or "听歌" in text:
        return SecondaryInteraction("播放歌曲", "player", "点击播放后立即进入播放页，可暂停、切歌、拖动进度或切换播放模式。")
    return SecondaryInteraction("查看详情", "detail", f"进入{title or '当前内容'}详情页查看完整信息和可用操作。")


def action_requires_confirmation(action: str) -> bool:
    text = str(action or "")
    return any(term in text for term in ("删除", "清空", "支付", "注销", "覆盖", "重置", "取消下载", "提交审核", "正式发布"))
