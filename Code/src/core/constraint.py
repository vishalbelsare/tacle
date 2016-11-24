from enum import Enum
from typing import List, Dict

import numpy

from core.assignment import Source, Filter, Variable, SameLength, ConstraintSource, SameTable, \
    SameOrientation, SameType, SizeFilter, Not, NotPartial, Partial, SatisfiesConstraint
from core.group import GType, Group, Orientation


class Constraint:
    def __init__(self, name, print_format, source: Source, filters: List[Filter], depends_on=set()):
        self.name = name
        self.print_format = print_format
        self.source = source
        self._filters = filters
        self._depends_on = set.union(depends_on, source.depends_on())

    @property
    def filters(self):
        return self._filters

    @property
    def variables(self):
        return self.source.variables

    def depends_on(self):
        return self._depends_on

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

filter_nan = lambda e: not numpy.isnan(e)
filter_none = lambda e: e is not None


def blank_filter(data, vectorized=False):
    if numpy.issubdtype(data.dtype, numpy.float):
        blank, blank_f = [numpy.nan, filter_nan]
    else:
        blank, blank_f = [None, filter_none]
    return blank, (blank_f if not vectorized else numpy.vectorize(blank_f))


def count_agg(data, axis=None):
    if axis is None:
        res = [len(data.flatten())]
    elif axis == 0:
        res = [data.shape[0]] * data.shape[1]
    elif axis == 1:
        res = [data.shape[1]] * data.shape[0]
    else:
        raise Exception("Invalid axis: {}".format(axis))
    return numpy.array(res)


class Operation(Enum):
    SUM = (numpy.sum, lambda x, y: x + y)
    MAX = (numpy.max, lambda x, y: max(x, y))
    MIN = (numpy.min, lambda x, y: min(x, y))
    AVERAGE = (numpy.average, lambda x, y: (x + y) / 2)
    PRODUCT = (numpy.product, lambda x, y: x * y)
    COUNT = (count_agg, lambda x, y: x + y)

    # noinspection PyInitNewSignature
    def __init__(self, aggregate, func):
        self._aggregate = aggregate
        self._func = func

    @property
    def aggregate(self):
        def apply(data, axis=None, partial=True):
            if axis == 1:
                data = data.T
            if not data.shape:
                data = numpy.array([[data]])
            blank, blank_test = blank_filter(data, vectorized=True)
            if len(data.shape) > 1:
                rows, cols = data.shape
                if partial:
                    results = numpy.array([blank] * cols)
                    for i in range(cols):
                        vec = data[:, i][blank_test(data[:, i])]
                        if len(vec) != 0:
                            vec = numpy.array(vec, dtype=numpy.float64)
                            results[i] = self._aggregate(vec)
                    return results
                else:
                    return self._aggregate(data, 0)
            else:
                if partial:
                    array = numpy.array(data[blank_test(data)], dtype=numpy.float64)
                    return self._aggregate(array) if len(array) > 0 else blank
                else:
                    return self._aggregate(data)

        return apply

    @property
    def func(self):
        return self._func


class Aggregate(Constraint):
    x = Variable("X", types=numeric)
    y = Variable("Y", vector=True, types=numeric)

    def __init__(self, orientation: Orientation, operation: Operation):
        self._orientation = orientation
        self._operation = operation
        self.min_size = 2
        self.min_vectors = 3 if operation == Operation.PRODUCT or operation == Operation.SUM else 2
        size = Group.columns if orientation == Orientation.VERTICAL else Group.rows
        or_string = "col" if orientation == Orientation.VERTICAL else "row"
        op_string = operation.name
        variables = [self.x, self.y]

        def test(_, a: Dict[str, Group], _solutions):
            x_group, y_group = [a[v.name] for v in variables]
            o_match = x_group.row == (orientation == Orientation.HORIZONTAL)
            if not o_match and x_group.vectors() < self.min_vectors:
                return False
            return y_group.length() <= size(x_group) if o_match else y_group.length() == size(x_group)

        filter_class = type("{}{}Length".format(op_string.lower().capitalize(), or_string.capitalize()),
                            (Filter,), {"test": test})
        x_size_filter = SizeFilter([self.x], rows=self.min_size)\
            if Orientation.column(orientation) else SizeFilter([self.x], cols=self.min_size)
        filters = [x_size_filter, filter_class(variables)]
        format_s = "{Y} = " + op_string.upper() + "({X}, " + or_string + ")"
        name = "{} ({})".format(op_string.lower(), or_string)
        # TODO Dependency only min max average
        super().__init__(name, format_s, Source(variables), filters, {Equal(), Projection()})

    @property
    def orientation(self):
        return self._orientation

    @property
    def operation(self):
        return self._operation

    @classmethod
    def instance(cls, orientation: Orientation, operation: Operation):
        return Aggregate(orientation, operation)

    @classmethod
    def instances(cls):
        return list(cls.instance(o, op) for o in Orientation for op in Operation)  # if not op == Operation.PRODUCT)


# TODO Same table, different orientation, overlapping bounds => prune assignment already

# TODO Subset -> Fuzzy lookup


class Permutation(Constraint):
    x = Variable("X", types=numeric)

    def __init__(self):
        variables = [self.x]
        source = ConstraintSource(variables, AllDifferent(), {AllDifferent.x.name: self.x.name})
        filters = [NotPartial(variables)]
        super().__init__("permutation", "PERMUTATION({X})", source, filters)


class Series(Constraint):
    x = Variable("X", types=numeric)

    def __init__(self):
        variables = [self.x]
        source = ConstraintSource(variables, Permutation(), {Permutation.x.name: self.x.name})
        filters = [NotPartial(variables)]
        super().__init__("series", "SERIES({X})", source, filters)


class AllDifferent(Constraint):
    x = Variable("X", types=discrete)

    def __init__(self):
        variables = [self.x]
        filters = [NotPartial(variables)]
        super().__init__("all-different", "ALLDIFFERENT({X})", Source(variables), filters)


class Ordered(Constraint):
    x = Variable("X", types=numeric)

    def __init__(self):
        variables = [self.x]
        source = Source(variables)
        filters = [NotPartial(variables)]
        super().__init__("ordered", "ORDERED({X})", source, filters)


class Rank(Constraint):
    x = Variable("X", vector=True, types=numeric)
    y = Variable("Y", vector=True, types=integer)

    def __init__(self):
        variables = [self.x, self.y]
        source = Source(variables)  # Not from Permutation because of possible ties
        filters = [SameLength(variables), NotPartial(variables)]
        super().__init__("rank", "{Y} = RANK({X})", source, filters, {Equal()})


class ForeignKey(Constraint):
    pk = Variable("PK", vector=True, types=discrete)
    fk = Variable("FK", vector=True, types=discrete)

    def __init__(self):
        variables = [self.pk, self.fk]
        source = ConstraintSource(variables, AllDifferent(), {"X": "PK"})
        filters = [Not(SameTable(variables)), SameType(variables), NotPartial([self.pk])]
        super().__init__("foreign-key", "{FK} -> {PK}", source, filters)


class Lookup(Constraint):
    o_key = Variable("OK", vector=True, types=discrete)
    o_value = Variable("OV", vector=True)
    f_key = Variable("FK", vector=True, types=discrete)
    f_value = Variable("FV", vector=True)

    def __init__(self):
        variables = [self.o_key, self.o_value, self.f_key, self.f_value]
        source = ConstraintSource(variables, ForeignKey(), {"PK": "OK", "FK": "FK"})
        filters = [SameType([self.o_value, self.f_value]), NotPartial(variables),
                   SameLength([self.f_key, self.f_value]), SameLength([self.o_key, self.o_value]),
                   SameTable([self.f_key, self.f_value]), SameTable([self.o_key, self.o_value]),
                   SameOrientation([self.f_key, self.f_value]), SameOrientation([self.o_key, self.o_value])]
        super().__init__("lookup", "{FV} = LOOKUP({FK}, {OK}, {OV})", source, filters, {Equal()})


class FuzzyLookup(Constraint):
    o_key = Variable("OK", vector=True, types=numeric)
    o_value = Variable("OV", vector=True)
    f_key = Variable("FK", vector=True, types=numeric)
    f_value = Variable("FV", vector=True)

    def __init__(self):
        variables = [self.o_key, self.o_value, self.f_key, self.f_value]
        # source = Source(variables)
        source = ConstraintSource(variables, Ordered(), {Ordered.x.name: self.o_key.name})
        filters = [SameType([self.o_value, self.f_value]), NotPartial(variables),
                   SameLength([self.f_key, self.f_value]), SameLength([self.o_key, self.o_value]),
                   SameTable([self.f_key, self.f_value]), SameTable([self.o_key, self.o_value]),
                   SameOrientation([self.f_key, self.f_value]), SameOrientation([self.o_key, self.o_value])]
        super().__init__("fuzzy-lookup", "{FV} = FUZZY-LOOKUP({FK}, {OK}, {OV})", source, filters, {Equal()})


class ConditionalAggregate(Constraint):
    o_key = Variable("OK", vector=True, types=discrete)
    result = Variable("R", vector=True, types=numeric)
    f_key = Variable("FK", vector=True, types=discrete)
    values = Variable("V", vector=True, types=numeric)

    def __init__(self, operation: Operation, default=0):
        self._default = default
        self._operation = operation
        name = operation.name
        variables = [self.o_key, self.result, self.f_key, self.values]
        all_diff = AllDifferent()
        source = ConstraintSource(variables, all_diff, {all_diff.x.name: "OK"})
        filters = [SameLength([self.o_key, self.result]), SameLength([self.f_key, self.values]),
                   SameTable([self.f_key, self.values]), Not(SameTable([self.f_key, self.o_key])),
                   # SameTable([self.o_key, self.result]),  # TODO think about this
                   NotPartial([self.o_key]), SameType([self.f_key, self.o_key]),
                   SameOrientation([self.o_key, self.result]), SameOrientation([self.f_key, self.values])]
        p_format = "{R} = " + name.upper() + "IF({FK}={OK}, {V})"
        super().__init__("{}-if".format(name.lower()), p_format, source, filters, depends_on={Lookup()})

    @property
    def operation(self) -> Operation:
        return self._operation

    @property
    def default(self):
        return self._default

    @classmethod
    def instance(cls, operation: Operation):
        return ConditionalAggregate(operation)

    @classmethod
    def instances(cls):
        return list(cls.instance(op) for op in Operation if not op == Operation.PRODUCT)


class RunningTotal(Constraint):
    acc = Variable("A", vector=True, types=numeric)
    pos = Variable("P", vector=True, types=numeric)
    neg = Variable("N", vector=True, types=numeric)

    def __init__(self):
        variables = [self.acc, self.pos, self.neg]
        source = Source(variables)
        filters = [SameLength(variables), SizeFilter(variables, length=2), NotPartial(variables)]
        super().__init__("running-total", "{A} = PREV({A}) + {P} - {N}", source, filters, {Equal()})


class ForeignOperation(Constraint):
    f_key = Variable("FK", vector=True, types=discrete)
    o_key = Variable("OK", vector=True, types=discrete)
    result = Variable("R", vector=True, types=numeric)
    f_value = Variable("FV", vector=True, types=numeric)
    o_value = Variable("OV", vector=True, types=numeric)

    def __init__(self, name: str, operation: Operation):
        self._operation = operation
        foreign = [self.f_key, self.result, self.f_value]
        original = [self.o_key, self.o_value]
        variables = foreign + original
        foreign_key = ForeignKey()
        source = ConstraintSource(variables, foreign_key, {foreign_key.pk.name: "OK", foreign_key.fk.name: "FK"})
        filters = [SameLength(foreign), SameTable(foreign), SameOrientation(foreign), NotPartial(variables),
                   SameLength(original), SameTable(original), SameOrientation(original)]
        super().__init__("foreign-" + name.lower(), "{R} = " + name.upper() + "({FV}, {FK}={OK} | {OV})", source,
                         filters)

    @property
    def operation(self):
        return self._operation


class ForeignProduct(ForeignOperation):
    def __init__(self):
        super().__init__("PRODUCT", Operation.PRODUCT)


class VectorOperation(Constraint):
    result = Variable("R", vector=True, types=numeric)
    first = Variable("O1", vector=True, types=numeric)
    second = Variable("O2", vector=True, types=numeric)

    def __init__(self, name, p_format, source, filters, symmetric=False, depends_on=set()):
        self._symmetric = symmetric
        super().__init__(name, p_format, source, filters, depends_on=depends_on)

    @property
    def symmetric(self):
        return self._symmetric

    @classmethod
    def list_variables(cls):
        return [cls.result, cls.first, cls.second]


class Product(VectorOperation):
    def __init__(self):
        variables = self.list_variables()
        source = Source(variables)
        filters = [SameLength(variables), NotPartial(variables)]
        super().__init__("product", "{R} = {O1} * {O2}", source, filters, True)


class Diff(VectorOperation):
    def __init__(self):
        variables = self.list_variables()
        source = Source(variables)
        filters = [SameLength(variables), NotPartial(variables), SameOrientation(variables)]
        super().__init__("difference", "{R} = {O1} - {O2}", source, filters)


class PercentualDiff(VectorOperation):
    def __init__(self):
        variables = self.list_variables()
        source = Source(variables)
        filters = [SameLength(variables), NotPartial(variables), SameOrientation(variables)]
        super().__init__("percentual-diff", "{R} = ({O1} - {O2}) / {O2}", source, filters, False, {Equal()})


class Projection(Constraint):
    result = Variable("R", vector=True)
    projected = Variable("P")

    def __init__(self):
        variables = [self.result, self.projected]
        source = Source(variables)
        filters = [SameLength(variables), SameOrientation(variables), SameTable(variables), SameType(variables),
                   SizeFilter([self.projected], vectors=2), Partial([self.projected])]
        super().__init__("project", "{R} = PROJECT({P})", source, filters)


class SumProduct(Constraint):
    result = Variable("R", vector=True, types=numeric)
    first = Variable("O1", vector=True, types=numeric)
    second = Variable("O2", vector=True, types=numeric)

    def __init__(self):
        variables = [self.result, self.first, self.second]
        source = Source(variables)
        filters = [SameLength([self.first, self.second]), NotPartial(variables),
                   SizeFilter([self.first, self.second], length=2), SizeFilter([self.result], rows=1, cols=1),
                   SizeFilter([self.result], rows=1, cols=1, max_size=True)]
        super().__init__("sum-product", "{R} = SUMPRODUCT({O1}, {O2})", source, filters)


class Equal(Constraint):
    first = Variable("O1", vector=True)
    second = Variable("O2", vector=True)

    def __init__(self):
        variables = [self.first, self.second]
        source = Source(variables)
        filters = [SameLength(variables), SameType(variables)]
        super().__init__("equal", "{O1} = {O2}", source, filters)


class EqualGroup(Constraint):
    x = Variable("X")

    def __init__(self):
        variables = [self.x]
        source = Source(variables)
        filters = [SizeFilter(variables, vectors=2)]
        super().__init__("equal-group", "EQUAL({X})", source, filters)
