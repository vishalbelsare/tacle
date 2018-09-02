import numpy as np

from tacle.core.group import Orientation
from tacle.core.template import ConditionalAggregate, Operation, Aggregate, Lookup
from tacle.engine.evaluate import evaluate_template


def test_conditional_sum():
    template = ConditionalAggregate(Operation.SUM)
    assignment = {
        template.o_key: np.array(["a", "b", "c"]),
        template.f_key: np.array(["b", "b", "c", "b", "c"]),
        template.values: np.array([10.2, 3.7, 5.12, 20, 1]),
    }
    result = evaluate_template(template, assignment)
    assert 0 == result[0]
    assert sum(assignment[template.values][np.array([True, True, False, True, False])]) == result[1]
    assert sum(assignment[template.values][np.array([False, False, True, False, True])]) == result[2]


def test_conditional_max():
    template = ConditionalAggregate(Operation.MAX)
    assignment = {
        template.o_key: np.array(["a", "b", "c"]),
        template.f_key: np.array(["b", "b", "c", "b", "c"]),
        template.values: np.array([10.2, 3.7, 5.12, 20, 1]),
    }
    result = evaluate_template(template, assignment)
    assert result[0] is None
    assert max(assignment[template.values][np.array([True, True, False, True, False])]) == result[1]
    assert max(assignment[template.values][np.array([False, False, True, False, True])]) == result[2]


def test_mean():
    template_h = Aggregate(Orientation.HORIZONTAL, Operation.AVERAGE)
    template_v = Aggregate(Orientation.VERTICAL, Operation.AVERAGE)
    x = np.array([
        [20.3, 14, 7],
        [8.9, 1.6, 5.2],
        [2.3, 43.8, 140],
    ])

    result = evaluate_template(template_h, {template_h.x: x})
    assert all(result == np.mean(x, axis=0))

    result = evaluate_template(template_v, {template_h.x: x})
    assert all(result == np.mean(x, axis=1))


def test_lookup():
    template = Lookup()
    ok = np.array([1, 2, 3])
    ov = np.array(["a", "b", "c"])

    d = {1: "a", 2: "b", 3: "c"}

    fk = np.array([2, 2, 3, 3, 2])

    result = evaluate_template(template, {template.o_key: ok, template.f_key: fk, template.o_value: ov})
    assert all(result == [d[k] for k in fk])