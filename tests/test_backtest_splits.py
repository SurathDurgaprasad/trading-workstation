from datetime import datetime

import pytest

from backtesting.splits import split_periods


def test_split_periods_is_chronological_and_contiguous():
    split = split_periods(datetime(2020, 1, 1), datetime(2030, 1, 1))

    assert split.development_start < split.development_end
    assert split.development_end == split.validation_start
    assert split.validation_end == split.out_of_sample_start
    assert split.out_of_sample_end == datetime(2030, 1, 1)
    assert split.development_start == datetime(2020, 1, 1)


def test_split_periods_uses_documented_default_fractions():
    start, end = datetime(2020, 1, 1), datetime(2030, 1, 1)
    split = split_periods(start, end)

    total_days = (end - start).days
    dev_days = (split.development_end - split.development_start).days
    val_days = (split.validation_end - split.validation_start).days

    assert abs(dev_days / total_days - 0.6) < 0.01
    assert abs(val_days / total_days - 0.2) < 0.01


def test_split_periods_rejects_end_before_start():
    with pytest.raises(ValueError):
        split_periods(datetime(2025, 1, 1), datetime(2020, 1, 1))


def test_split_periods_rejects_fractions_that_leave_no_out_of_sample_room():
    with pytest.raises(ValueError):
        split_periods(datetime(2020, 1, 1), datetime(2030, 1, 1), development_fraction=0.7, validation_fraction=0.4)


def test_custom_fractions_are_respected():
    start, end = datetime(2020, 1, 1), datetime(2030, 1, 1)
    split = split_periods(start, end, development_fraction=0.5, validation_fraction=0.25)

    total_days = (end - start).days
    dev_days = (split.development_end - split.development_start).days
    assert abs(dev_days / total_days - 0.5) < 0.01
