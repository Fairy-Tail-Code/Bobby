import pytest
from orchestration.termination import create_termination_check


def test_termination_check_passed():
    check = create_termination_check()
    assert check({"content": "EVALUATION PASSED - ALL DIMENSIONS ABOVE THRESHOLD"})


def test_termination_check_not_passed():
    check = create_termination_check()
    assert not check({"content": "EVALUATION Report\n### Verdict: NEEDS IMPROVEMENT"})


def test_termination_check_terminate():
    check = create_termination_check()
    assert check({"content": "TERMINATE"})


def test_termination_check_empty():
    check = create_termination_check()
    assert not check({"content": ""})


def test_termination_check_none():
    check = create_termination_check()
    assert not check({"content": None})
