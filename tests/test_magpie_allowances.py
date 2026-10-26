"""Magpie 缓存额度 → 灵动岛轮播；网络边界用本机 HTTP 服务验证。"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from pet.config import Config
from pet.island import magpie
from pet.island.dynamic_island import DynamicIsland


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def wait_for(predicate):
    if predicate():
        return
    loop = QEventLoop()
    poll = QTimer()
    poll.setInterval(10)
    poll.timeout.connect(lambda: loop.quit() if predicate() else None)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    poll.start()
    deadline.start(5000)
    loop.exec()
    poll.stop()
    deadline.stop()
    assert predicate(), "等待 Qt 事件超时"


@pytest.fixture
def endpoint(monkeypatch):
    state = {"status": 200, "body": {"data": [
        {"name": "Claude", "windows": [
            {"name": "5 hours", "used": 20, "remaining": 80},
            {"name": "7 days", "used": 60, "remaining": 40},
        ]},
    ]}, "paths": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["paths"].append(self.path)
            self.send_response(state["status"])
            self.end_headers()
            try:
                self.wfile.write(json.dumps(state["body"]).encode())
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(magpie, "QUOTAS_URL", f"http://127.0.0.1:{server.server_port}/v1/magpie/quotas?kept=1")
    yield state
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_formats_all_windows_and_balance_without_inventing_percentages():
    rows = magpie.quota_lines({"data": [
        {"name": "Claude", "windows": [
            {"name": "5 hours", "used": 20, "remaining": 80},
            {"name": "7 days", "remaining": 0},
        ]},
        {"name": "Credits", "windows": [{"name": "Credits", "remaining": 75.25, "display": "3,010 / 4,000"}]},
        {"name": "API", "balance": "$3.50", "windows": []},
        {"name": "Offline", "error": "private upstream error", "windows": []},
        {"name": "Unknown", "windows": []},
    ]})
    assert len(rows) == 6
    assert "Claude · 5 小时 · 剩余 80%" in rows
    assert "Claude · 7 天 · 剩余 0%" in rows
    assert any("剩余 75.2%" in row for row in rows)
    assert "API · 余额 $3.50" in rows
    assert "Offline · 暂不可用" in rows
    assert "Unknown · 暂无额度数据" in rows
    assert "private" not in " ".join(rows)


@pytest.mark.parametrize("value", [None, True, "80", float("nan"), float("inf"), -1, 101, 10**1000])
def test_invalid_percentages_are_unknown(value):
    rows = magpie.quota_lines({"data": [{"name": "Plan", "windows": [{"name": "Weekly", "remaining": value}]}]})
    assert "剩余 --" in rows[0]


def test_bad_payload_is_rejected_but_empty_list_is_valid():
    assert magpie.quota_lines({"data": []}) == []
    for payload in [None, [], {}, {"data": "bad"}, {"data": [None]}]:
        with pytest.raises(ValueError):
            magpie.quota_lines(payload)


def test_missing_remaining_can_use_valid_used():
    assert "剩余 75%" in magpie.quota_lines({"data": [{"windows": [{"used": 25}]}]})[0]


def test_carousel_fetches_cache_rotates_and_clears_on_error(app, endpoint):
    carousel = magpie.MagpieCarousel()
    try:
        carousel.set_active(True)
        wait_for(lambda: len(carousel.lines) == 2)
        assert endpoint["paths"] == ["/v1/magpie/quotas?kept=1"]
        assert "80%" in carousel.text
        assert carousel.refresh_timer.interval() == 60_000
        assert carousel.rotate_timer.interval() == 5000
        carousel.advance()
        assert "40%" in carousel.text
        carousel.advance()
        assert "80%" in carousel.text
        endpoint["status"] = 503
        carousel.refresh()
        wait_for(lambda: "无法读取" in carousel.text)
        assert not carousel.lines  # 失败后不能继续把旧额度冒充当前额度
    finally:
        carousel.set_active(False)


def test_stop_aborts_reply_and_stops_timers(app, endpoint):
    carousel = magpie.MagpieCarousel()
    carousel.set_active(True)
    carousel.set_active(False)
    app.processEvents()
    assert not carousel.refresh_timer.isActive()
    assert not carousel.rotate_timer.isActive()
    assert not carousel.lines
    carousel.refresh()
    app.processEvents()
    assert not carousel.active


@pytest.mark.parametrize("body", [{}, {"data": "bad"}, {"data": []}])
def test_invalid_or_empty_response_clears_previous_readings(app, endpoint, body):
    carousel = magpie.MagpieCarousel()
    try:
        carousel.set_active(True)
        wait_for(lambda: len(carousel.lines) == 2)
        endpoint["body"] = body
        carousel.refresh()
        wait_for(lambda: not carousel.lines)
        assert "80%" not in carousel.text
        assert not carousel.rotate_timer.isActive()
    finally:
        carousel.set_active(False)


def test_local_queries_ignore_system_proxy(app, endpoint):
    from PySide6.QtNetwork import QNetworkProxy

    carousel = magpie.MagpieCarousel()
    assert carousel._network.proxy().type() == QNetworkProxy.ProxyType.NoProxy


def test_reset_time_is_optional_and_invalid_timestamp_does_not_break_other_windows():
    rows = magpie.quota_lines({"data": [{"name": "Plan", "windows": [
        {"name": "5 hours", "remaining": 50, "resetsAt": "2030-01-01T12:00:00Z"},
        {"name": "7 days", "remaining": 70, "resetsAt": "bad"},
    ]}]})
    assert "重置" in rows[0]
    assert rows[1] == "Plan · 7 天 · 剩余 70%"


def test_stopped_before_first_show_creates_no_magpie_network_client(app, tmp_path):
    cfg = Config(base=tmp_path)
    cfg.set("dynamic_island", {"enabled": True, "info_mode": "magpie"})
    island = DynamicIsland(cfg)
    try:
        assert island._magpie is None
    finally:
        island.deleteLater()
        app.processEvents()


def test_magpie_mode_roundtrip_and_settings_option(app, tmp_path):
    from pet.modern_settings_dialog import ModernSettingsDialog

    cfg = Config(base=tmp_path)
    cfg.set("dynamic_island", {"enabled": True, "info_mode": "magpie"})
    cfg.save()
    assert Config(base=tmp_path).get("dynamic_island")["info_mode"] == "magpie"
    dialog = ModernSettingsDialog(cfg)
    try:
        assert dialog.island_info_mode_select.currentData() == "magpie"
        assert "Magpie" in dialog.island_info_mode_select.currentText()
    finally:
        dialog.deleteLater()
        app.processEvents()


def test_long_allowances_keep_same_width_and_tooltip_keeps_full_text(app, endpoint, tmp_path):
    endpoint["body"] = {"data": [{"name": "A very long subscription account name", "windows": [
        {"name": "5 hours", "remaining": 80, "resetsAt": "2030-01-01T12:00:00Z"},
        {"name": "7 days", "remaining": 40, "resetsAt": "2030-01-07T12:00:00Z"},
        {"name": "Credits", "remaining": 99.9},
    ]}]}
    cfg = Config(base=tmp_path)
    cfg.set("dynamic_island", {"enabled": True, "info_mode": "magpie", "show_name": False})
    island = DynamicIsland(cfg)
    try:
        island.show()
        wait_for(lambda: island._magpie and len(island._magpie.lines) == 3)
        widths = []
        for _ in range(3):
            widths.append(island.width())
            island._magpie.advance()
        assert len(set(widths)) == 1, widths
        assert "2030" not in island.toolTip()  # 重置时间采用本地月日，完整条目保留在提示里
        assert "99.9%" in island.toolTip()
    finally:
        island.close()
        island.deleteLater()
        app.processEvents()


def test_island_shows_live_rows_and_stops_when_hidden_or_mode_changes(app, endpoint, tmp_path):
    cfg = Config(base=tmp_path)
    cfg.set("dynamic_island", {"enabled": True, "show_info": True, "info_mode": "magpie"})
    island = DynamicIsland(cfg)
    try:
        island.show()
        wait_for(lambda: "80%" in island._info_text())
        width = island.width()
        island._magpie.advance()
        assert "40%" in island._info_text()
        assert island.width() == width
        assert "80%" in island.toolTip() and "40%" in island.toolTip()
        island.hide()
        assert not island._magpie.active
        assert island.toolTip() == ""
        island.show()
        assert "80%" not in island.toolTip()
        wait_for(lambda: "80%" in island._info_text())
        cfg.set("dynamic_island", {"enabled": True, "show_info": False, "info_mode": "magpie"})
        island.refresh_from_config()
        assert not island._magpie.active
        cfg.set("dynamic_island", {"enabled": True, "info_mode": "time"})
        island.refresh_from_config()
        assert not island._magpie.active
        assert "Magpie" not in island.toolTip()
    finally:
        island.close()
        island.deleteLater()
        app.processEvents()
