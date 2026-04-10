import pytest
from orchestration.termination import create_termination_check


def test_termination_check_evaluator_passed():
    check = create_termination_check()
    assert check({"content": "EVALUATION PASSED - ALL DIMENSIONS ABOVE THRESHOLD", "name": "Evaluator"})


def test_termination_check_evaluator_terminate():
    check = create_termination_check()
    assert check({"content": "TERMINATE", "name": "Evaluator"})


def test_termination_check_not_passed():
    check = create_termination_check()
    assert not check({"content": "EVALUATION Report\n### Verdict: NEEDS IMPROVEMENT", "name": "Evaluator"})


def test_termination_check_non_evaluator():
    check = create_termination_check()
    assert not check({"content": "TERMINATE", "name": "Generator"})
    assert not check({"content": "EVALUATION PASSED", "name": "Planner"})


def test_termination_check_empty():
    check = create_termination_check()
    assert not check({"content": "", "name": "Evaluator"})


def test_termination_check_none():
    check = create_termination_check()
    assert not check({"content": None, "name": "Evaluator"})
