"""本机 Magpie 缓存额度与异步轮播；不读取凭据、不触发供应商刷新。"""
from __future__ import annotations

import json
import math
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Qt, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkProxy, QNetworkReply, QNetworkRequest

# shortcut: 只接本机默认端口；需要连接改端口的 Magpie 时再开放连接设置。
QUOTAS_URL = "http://127.0.0.1:3425/v1/magpie/quotas?kept=1"
_MAX_RESPONSE = 1024 * 1024
_WINDOW_NAMES = {"5 hours": "5 小时", "7 days": "7 天", "Credits": "积分", "Add-on credits": "附加积分"}


def _label(value, fallback="") -> str:
    return " ".join(str(value or fallback).split())[:80]


def _percent(value) -> bool:
    return type(value) in (int, float) and 0 <= value <= 100 and math.isfinite(value)


def quota_lines(payload) -> list[str]:
    """保留 Magpie 顺序，展开每个账户的所有窗口；未知读数不冒充零。"""
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("无效的 Magpie 额度响应")
    lines = []
    for item in payload["data"]:
        if not isinstance(item, dict):
            raise ValueError("无效的 Magpie 额度条目")
        name = _label(item.get("alias") or item.get("name") or item.get("provider"), "账户")
        if item.get("error"):
            lines.append(f"{name} · 暂不可用")
            continue
        windows = item.get("windows", [])
        if not isinstance(windows, list) or any(not isinstance(w, dict) for w in windows):
            raise ValueError("无效的 Magpie 额度窗口")
        for window in windows:
            label = _label(window.get("name"), "额度")
            label = _WINDOW_NAMES.get(label, label)
            remaining = window.get("remaining")
            if "remaining" not in window and _percent(window.get("used")):
                remaining = 100 - window["used"]
            value = f"{remaining:.1f}".rstrip("0").rstrip(".") + "%" if _percent(remaining) else "--"
            text = f"{name} · {label} · 剩余 {value}"
            reset = window.get("resetsAt")
            if isinstance(reset, str) and reset:
                try:
                    reset_at = datetime.fromisoformat(reset.replace("Z", "+00:00")).astimezone()
                    text += f" · {reset_at:%m-%d %H:%M} 重置"
                except ValueError:
                    pass
            lines.append(text)
        if not windows:
            balance = _label(item.get("balance"))
            lines.append(f"{name} · 余额 {balance}" if balance else f"{name} · 暂无额度数据")
    return lines


class MagpieCarousel(QObject):
    """Qt 网络请求全异步；未选择/隐藏时停表并取消在途请求。"""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active = False
        self.lines: list[str] = []
        self.index = 0
        self.status = "查询中…"
        self._reply = None
        self._display_cache = None
        self._network = QNetworkAccessManager(self)
        self._network.setProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(60_000)
        self.refresh_timer.timeout.connect(self.refresh)
        self.rotate_timer = QTimer(self)
        self.rotate_timer.setInterval(5000)
        self.rotate_timer.timeout.connect(self.advance)

    @property
    def text(self) -> str:
        if self.lines:
            return f"Magpie {self.index + 1}/{len(self.lines)} · {self.lines[self.index]}"
        return f"Magpie · {self.status}"

    def display(self, metrics) -> tuple[str, str]:
        """同一批额度只测宽一次；轮播按省略后最宽的一项固定胶囊宽度。"""
        if not self.lines:
            text = metrics.elidedText(self.text, Qt.TextElideMode.ElideRight, 360)
            return text, text
        key = (tuple(self.lines), metrics)
        if self._display_cache is None or self._display_cache[0] != key:
            texts = [metrics.elidedText(f"Magpie {i + 1}/{len(self.lines)} · {line}",
                                       Qt.TextElideMode.ElideRight, 360)
                     for i, line in enumerate(self.lines)]
            self._display_cache = (key, texts, max(texts, key=metrics.horizontalAdvance))
        _, texts, sample = self._display_cache
        return texts[self.index], sample

    def set_active(self, active: bool) -> None:
        if active == self.active:
            return
        self.active = active
        if active:
            self.status = "查询中…"
            self.refresh_timer.start()
            self.refresh()
        else:
            self.refresh_timer.stop()
            self.rotate_timer.stop()
            reply, self._reply = self._reply, None
            if reply is not None:
                reply.abort()
                reply.deleteLater()
            self.lines = []
            self.index = 0
            self._display_cache = None

    def refresh(self) -> None:
        if not self.active or self._reply is not None:
            return
        request = QNetworkRequest(QUrl(QUOTAS_URL))
        request.setTransferTimeout(3000)
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                             QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        request.setRawHeader(b"Accept", b"application/json")
        self._reply = self._network.get(request)
        self._reply.setReadBufferSize(_MAX_RESPONSE + 1)
        self._reply.readyRead.connect(self._check_size)
        self._reply.finished.connect(self._finished)

    def _check_size(self) -> None:
        reply = self.sender()
        if reply is self._reply and reply.bytesAvailable() > _MAX_RESPONSE:
            reply.abort()

    def _finished(self) -> None:
        reply = self.sender()
        if reply is not self._reply:
            return
        self._reply = None
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError or reply.attribute(
                QNetworkRequest.Attribute.HttpStatusCodeAttribute
            ) != 200:
                raise ValueError("Magpie 请求失败")
            self.lines = quota_lines(json.loads(bytes(reply.readAll())))
            self.status = "暂无额度数据" if not self.lines else ""
            # 主动刷新仍保留当前项，不把每分钟刷新变成从第一项重新播放。
            if len(self.lines) > 1 and not self.rotate_timer.isActive():
                self.rotate_timer.start()
            elif len(self.lines) <= 1:
                self.rotate_timer.stop()
        except (ValueError, UnicodeError, RecursionError):
            self.lines = []
            self.status = "无法读取额度，请检查 Magpie"
            self.rotate_timer.stop()
        finally:
            reply.deleteLater()
        self.index %= max(1, len(self.lines))
        self.changed.emit()

    def advance(self) -> None:
        if self.active and len(self.lines) > 1:
            self.index = (self.index + 1) % len(self.lines)
            self.changed.emit()
