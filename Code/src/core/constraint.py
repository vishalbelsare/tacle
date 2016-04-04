from enum import Enum
from typing import List, Dict

import numpy

from core.assignment import Source, Filter, Variable, SameLength, ConstraintSource, SameTable, \
    SameOrientation, SameType, SizeFilter, Not
from core.group import GType, Group, Orientation


class Constraint:
    def __init__(self, name, print_format, source: Source, filters: List[Filter]):
        self.name = name
        self.print_format = print_format
        self.source = source
        self._filters = filters

    @property
    def filters(self):
        return self._filters

    @property
    def variables(self):
        return self.source.variables

    def get_variables(self):
        return self.variables

    def to_string(self, assignment):
        return self.print_format.format(**assignment)

    def __str__(self):
        return self.name

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return self.name == other.name

    def __ne__(self, other):
        return not (self == other)


integer = {GType.int}
numeric = {GType.int, GType.float}
textual = {GType.string}
discrete = {GType.string, GType.int}


class Operation(Enum):
    SUM = numpy.sum,
    PRODUCT = numpy.product,
    MAX = numpy.max,
    MIN = numpy.min,
    AVERAGE = numpy.average,

    def __init__(self, f):
        self._f = f

    @property
    def f(self):
        return self._f


class Aggregate(Constraint):
    x = Variable("X", types=numeric)
    y = Variable("Y", vector=True, types=numeric)

    def __init__(self, orientation: Orientation, operation: Operation):
        self._orientation = orientation
        self._operation = operation
        size = Group.columns if orientation == Orientation.VERTICAL else Group.rows
        or_string = "col" if orientation == Orientation.VERTICAL else "row"
        op_string = operation.name
        variables = [self.x, self.y]

        def test(_, a: Dict[str, Group]):
            x_group, y_group = [a[v.name] for v in variables]
            o_match = x_group.row == (orientation == Orientation.HORIZONTAL)
            return y_group.length() <= size(x_group) if o_match else y_group.length() == size(x_group)

        filter_class = type("{}{}Length".format(op_string.lower().capitalize(), or_string.capitalize()),
                            (Filter,), {"test": test})
        size_filter = SizeFilter([self.x], rows=2) if Orientation.column(orientation) else SizeFilter([self.x], cols=2)
        filters = [size_filter, filter_class(variables)]
        format_s = "{Y} = " + op_string.upper() + "({X}, " + or_string + ")"
        super().__init__("{} ({})".format(op_string.lower(), or_string), format_s, Source(variables), filters)

    @property
    def orientation(self):
        return self._orientation

    @property
    def operation(self):
        return self._operation


class ColumnSum(Aggregate):
    def __init__(self):
        super().__init__(Orientation.VERTICAL, Operation.SUM)


class RowSum(Aggregate):
    def __init__(self):
        super().__init__(Orientation.HORIZONTAL, Operation.SUM)


class ColumnProduct(Aggregate):
    def __init__(self):
        super().__init__(Orientation.VERTICAL, Operation.PRODUCT)


class RowProduct(Aggregate):
    def __init__(self):
        super().__init__(Orientation.HORIZONTAL, Operation.PRODUCT)


class ColumnAverage(Aggregate):
    def __init__(self):
        super().__init__(Orientation.VERTICAL, Operation.AVERAGE)


class RowAverage(Aggregate):
    def __init__(self):
        super().__init__(Orientation.HORIZONTAL, Operation.AVERAGE)


class ColumnMax(Aggregate):
    def __init__(self):
        super().__init__(Orientation.VERTICAL, Operation.MAX)


class RowMax(Aggregate):
    def __init__(self):
        super().__init__(Orientation.HORIZONTAL, Operation.MAX)


class ColumnMin(Aggregate):
    def __init__(self):
        super().__init__(Orientation.VERTICAL, Operation.MIN)


class RowMin(Aggregate):
    def __init__(self):
        super().__init__(Orientation.HORIZONTAL, Operation.MIN)


# TODO Same table, different orientation, overlapping bounds => prune assignment already

# TODO Subset -> Fuzzy lookup


class Permutation(Constraint):
    x = Variable("X", types=numeric)

    def __init__(self):
        filters = []
        variables = [self.x]
        super().__init__("permutation", "PERMUTATION({X})", Source(variables), filters)


class Series(Constraint):
    x = Variable("X", types=numeric)

    def __init__(self):
        filters = []
        variables = [self.x]
        super().__init__("series", "SERIES({X})", Source(variables), filters)


class AllDifferent(Constraint):
    x = Variable("X", types=discrete)

    def __init__(self):
        filters = []
        variables = [self.x]
        super().__init__("all-different", "ALLDIFFERENT({X})", Source(variables), filters)


class Rank(Constraint):
    x = Variable("X", vector=True, types=numeric)
    y = Variable("Y", vector=True, types=integer)

    def __init__(self):
        variables = [self.x, self.y]
        filters = [SameLength(variables)]
        super().__init__("rank", "{Y} = RANK({X})", Source(variables), filters)


class ForeignKey(Constraint):
    pk = Variable("PK", vector=True, types=discrete)
    fk = Variable("FK", vector=True, types=discrete)

    def __init__(self):
        variables = [self.pk, self.fk]
        source = ConstraintSource(variables, AllDifferent(), {"X": "PK"})
        filters = [Not(SameTable([self.pk, self.fk])), SameType(variables)]
        super().__init__("foreign-key", "{FK} -> {PK}", source, filters)


class Lookup(Constraint):
    o_key = Variable("OK", vector=True, types=discrete)
    o_value = Variable("OV", vector=True)
    f_key = Variable("FK", vector=True, types=discrete)
    f_value = Variable("FV", vector=True)

    def __init__(self):
        variables = [self.o_key, self.o_value, self.f_key, self.f_value]
        source = ConstraintSource(variables, ForeignKey(), {"PK": "OK", "FK": "FK"})
        filters = [SameType([self.o_value, self.f_value]),
                   SameLength([self.f_key, self.f_value]), SameLength([self.o_key, self.o_value]),
                   SameTable([self.f_key, self.f_value]), SameTable([self.o_key, self.o_value]),
                   SameOrientation([self.f_key, self.f_value]), SameOrientation([self.o_key, self.o_value])]
        super().__init__("lookup", "{FV} = LOOKUP({FK}, {OK}, {OV})", source, filters)


class FuzzyLookup(Constraint):
    o_key = Variable("OK", vector=True, types=numeric)
    o_value = Variable("OV", vector=True)
    f_key = Variable("FK", vector=True, types=numeric)
    f_value = Variable("FV", vector=True)

    def __init__(self):
        variables = [self.o_key, self.o_value, self.f_key, self.f_value]
        source = Source(variables)
        filters = [SameType([self.o_value, self.f_value]),
                   SameLength([self.f_key, self.f_value]), SameLength([self.o_key, self.o_value]),
                   SameTable([self.f_key, self.f_value]), SameTable([self.o_key, self.o_value]),
                   SameOrientation([self.f_key, self.f_value]), SameOrientation([self.o_key, self.o_value])]
        super().__init__("fuzzy-lookup", "{FV} = FUZZY-LOOKUP({FK}, {OK}, {OV})", source, filters)


class ConditionalAggregate(Constraint):
    o_key = Variable("OK", vector=True, types=textual)
    result = Variable("R", vector=True, types=numeric)
    f_key = Variable("FK", vector=True, types=textual)
    values = Variable("V", vector=True, types=numeric)

    def __init__(self, name: str, operator, default=0):
        self._default = default
        self._operator = operator
        variables = [self.o_key, self.result, self.f_key, self.values]
        foreign_key = ForeignKey()
        source = ConstraintSource(variables, foreign_key, {foreign_key.pk.name: "OK", foreign_key.fk.name: "FK"})
        filters = [SameLength([self.o_key, self.result]), SameLength([self.f_key, self.values]),
                   SameTable([self.o_key, self.result]), SameTable([self.f_key, self.values]),
                   SameOrientation([self.o_key, self.result]), SameOrientation([self.f_key, self.values])]
        super().__init__("{}-if".format(name.lower()), "{R} = " + name.upper() + "IF({FK}={OK}, {V})", source, filters)

    @property
    def operator(self):
        return self._operator

    @property
    def default(self):
        return self._default


class SumIf(ConditionalAggregate):
    def __init__(self):
        super().__init__("SUM", lambda acc, new: acc + new)


class MaxIf(ConditionalAggregate):
    def __init__(self):
        super().__init__("MAX", lambda acc, new: max(acc, new))


class RunningTotal(Constraint):
    acc = Variable("A", vector=True, types=numeric)
    pos = Variable("P", vector=True, types=numeric)
    neg = Variable("N", vector=True, types=numeric)

    def __init__(self):
        variables = [self.acc, self.pos, self.neg]
        source = Source(variables)
        filters = [SameLength(variables)]
        super().__init__("running-total", "{A} = PREV({A}) + {P} - {N}", source, filters)


class ForeignOperation(Constraint):
    f_key = Variable("FK", vector=True, types=discrete)
    o_key = Variable("OK", vector=True, types=discrete)
    result = Variable("R", vector=True, types=numeric)
    f_value = Variable("FV", vector=True, types=numeric)
    o_value = Variable("OV", vector=True, types=numeric)

    def __init__(self, name: str, operator):
        self._operator = operator
        foreign = [self.f_key, self.result, self.f_value]
        original = [self.o_key, self.o_value]
        variables = foreign + original
        foreign_key = ForeignKey()
        source = ConstraintSource(variables, foreign_key, {foreign_key.pk.name: "OK", foreign_key.fk.name: "FK"})
        filters = [SameLength(foreign), SameTable(foreign), SameOrientation(foreign),
                   SameLength(original), SameTable(original), SameOrientation(original)]
        super().__init__("foreign-" + name.lower(), "{R} = " + name.upper() + "({FV}, {FK}={OK} | {OV})", source,
                         filters)

    @property
    def operator(self):
        return self._operator


class ForeignProduct(ForeignOperation):
    def __init__(self):
        super().__init__("PRODUCT", lambda fv, ov: fv * ov)
