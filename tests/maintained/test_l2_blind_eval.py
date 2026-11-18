"""The L2 blind-eval tool stays offline and carries no deployment-specific names."""

from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "maintained" / "tools" / "l2_blind_eval.py"
)


def _load():
    spec = importlib.util.spec_from_file_location(
        "l2_blind_eval_under_test", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_selftest_covers_the_full_pipeline(capsys):
    assert _load().run_selftest() == 0
    assert "SELFTEST OK" in capsys.readouterr().out


def test_red_line_detectors_cover_all_four_cases():
    mod = _load()
    assert "empty_echo" in mod.compute_mech_flags("哈哈哈确实！！")
    assert "service_tone" in mod.compute_mech_flags(
        "您好，首先建议您检查配置，其次重启服务，希望对您有帮助！"
    )
    assert "particle_spam" in mod.compute_mech_flags(
        "今天也是元气满满的一天呢~大家觉得呢呀~"
    )
    row = {"ts": "2026-11-14 12:00:00", "group": "g", "sent": True}
    later = [
        {"ts": "2026-11-14 12:01:30", "group": "g", "skipped_by": "complaint_quiet"}
    ]
    assert "complaint_triggered" in mod.compute_mech_flags("测试回复", row, later)


def test_no_bot_nickname_is_checked_in(monkeypatch):
    monkeypatch.delenv("L2_BOT_NICKNAMES", raising=False)
    mod = _load()
    assert mod.BOT_NICKNAMES == ()
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "小话" not in source
    assert "hesder" not in source


def test_nicknames_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("L2_BOT_NICKNAMES", "测试昵称, 备用称呼")
    mod = _load()
    assert mod.BOT_NICKNAMES == ("测试昵称", "备用称呼")
    assert "群友" in mod.normalize_candidate_text("测试昵称觉得可以")


def test_echo_whole_regex_does_not_backtrack_exponentially():
    """A long repeated prefix followed by a non-matching char must stay fast."""
    import time

    mod = _load()
    payload = "哈" * 400 + "x"
    start = time.monotonic()
    assert not mod.ECHO_WHOLE_RE.match(payload)
    assert time.monotonic() - start < 0.5


def test_echo_whole_regex_keeps_every_original_phrase():
    """The ReDoS fix must not change which texts the regex accepts."""
    mod = _load()
    for text in [
        "哈",
        "哈哈哈",
        "是的的",
        "对的的",
        "真的的",
        "666",
        "。",
        "笑死笑死",
        "太真实了",
    ]:
        assert mod.ECHO_WHOLE_RE.match(text), text
    assert not mod.ECHO_WHOLE_RE.match("哈哈哈x")
    assert not mod.ECHO_WHOLE_RE.match("我哈")
