"""The AU, BB and BE rows are reasons only: the plug-in's reads are compared with a second server, which the runner does not start."""

from __future__ import annotations

from live_fakes import load

reads = load("live_check_plugin_reads")


def test_nothing_is_measured_here():
    assert reads.CHECKS == ()


def test_every_row_has_its_reason():
    want = {f"AU{n}" for n in range(1, 9)} | {f"BB{n}" for n in range(1, 11)} | {f"BE{n}" for n in range(1, 11)}
    assert set(reads.BY_EYE) == want


def test_no_reason_is_just_a_label():
    assert all(len(why.split()) >= 6 for why in reads.BY_EYE.values())
