"""The AK and AY rows are reasons only: nothing about installing Heron is run by the runner."""

from __future__ import annotations

from live_fakes import load

setup = load("live_check_setup")


def test_nothing_is_measured_here():
    assert setup.CHECKS == ()


def test_every_ak_and_ay_row_has_its_reason():
    assert set(setup.BY_EYE) == {f"AK{n}" for n in range(1, 17)} | {f"AY{n}" for n in range(1, 4)}


def test_no_reason_is_just_a_label():
    assert all(len(why.split()) >= 5 for why in setup.BY_EYE.values())
