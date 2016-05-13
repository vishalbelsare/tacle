from typing import List, Dict, Set

import itertools
from constraint import Problem
from core.group import Group, Orientation
from parse.parser import GType


class Variable:
    def __init__(self, name, vector=False, types={GType.int, GType.float, GType.string}):
        self.name = name
        self.vector = vector
        if len(types) == 0:
            raise Exception("At least one type must be supported")
        self._types = types

    @property
    def types(self):
        return self._types

    def __str__(self):
        return self.name + "[Var]"

    def get_name(self):
        return self.name

    def is_vector(self):
        return self.vector

    def is_numeric(self):
        return GType.string not in self.types

    def is_textual(self):
        return len(self.types) == 1 and GType.string in self.types

    def is_integer(self):
        return len(self.types) == 1 and GType.int in self.types


class Source:
    def __init__(self, variables: List[Variable]):
        self._variables = variables

    @property
    def variables(self):
        return self._variables

    def candidates(self, groups, solutions, filters):
        return self._complete([{}], groups, filters)

    def _complete(self, assignments, groups, filters):
        result = []

        # TODO type as constraint

        def try_assignment():
            problem = Problem()

            for variable in self.variables:
                candidates = [assignment[variable.name]] if variable.name in assignment else groups
                domain = list([g for g in candidates if g.dtype in variable.types])
                if len(domain) == 0:
                    return variable.name in assignment, []
                problem.addVariable(variable.name, domain)

            for f in filters:
                variables = list([v.name for v in f.variables])

                def c_j(ff, vv):
                    return lambda *args: ff.test({vv[i]: args[i] for i in range(len(args))})

                problem.addConstraint(c_j(f, variables), variables)

            return True, list(problem.getSolutions())

        for assignment in assignments:
            resume, solutions = try_assignment()
            if not resume:
                return []
            result += solutions
        return result

    def depends_on(self) -> Set:
        return set()


class ConstraintSource(Source):
    def __init__(self, variables, constraint, dictionary):
        super().__init__(variables)
        self._constraint = constraint
        self.dictionary = dictionary

    @property
    def constraint(self):
        return self._constraint

    def candidates(self, groups, solutions, filters):
        assignments = [{self.dictionary[k]: v for k, v in s.items()} for s in solutions.get_solutions(self.constraint)]
        return self._complete(assignments, groups, filters)

    def depends_on(self):
        return {self.constraint}


class Filter:
    def __init__(self, variables: List[Variable]):
        self._variables = variables

    @property
    def variables(self):
        return self._variables

    def test(self, assignment: Dict[str, Group]):
        raise NotImplementedError()

    def test_same(self, assignment, f):
        groups = list([assignment[v.name] for v in self.variables])
        return all(f(groups[i]) == f(groups[j]) for i in range(len(groups)) for j in range(i + 1, len(groups)))

    def test_all(self, assignment, f):
        groups = list([assignment[v.name] for v in self.variables])
        return all(f(g) for g in groups)


class Not(Filter):
    def __init__(self, original_filter: Filter):
        super().__init__(original_filter.variables)
        self._original_filter = original_filter

    def test(self, assignment):
        return not self._original_filter.test(assignment)


class If(Filter):
    def __init__(self, if_filter: Filter, then_filter: Filter, else_filter: Filter=None):
        if else_filter is None:
            else_filter = NoFilter([])
        variables = set(if_filter.variables).union(set(then_filter.variables)).union(set(else_filter.variables))
        super().__init__(variables)
        self._if_filter = if_filter
        self._then_filter = then_filter
        self._else_filter = else_filter

    @property
    def if_filter(self):
        return self._if_filter

    @property
    def then_filter(self):
        return self._then_filter

    @property
    def else_filter(self):
        return self._else_filter

    def test(self, assignment: Dict[str, Group]):
        if self.if_filter.test(assignment):
            return self.then_filter.test(assignment)
        else:
            return self.else_filter.test(assignment)


class NoFilter(Filter):
    def test(self, assignment: Dict[str, Group]):
        return True


class SameLength(Filter):
    def test(self, assignment: Dict[str, Group]):
        return self.test_same(assignment, Group.length)


class SameTable(Filter):
    def test(self, assignment: Dict[str, Group]):
        return self.test_same(assignment, lambda g: g.table)


class SameOrientation(Filter):
    def test(self, assignment: Dict[str, Group]):
        return self.test_same(assignment, lambda g: g.row)


class SameType(Filter):
    def test(self, assignment: Dict[str, Group]):
        return self.test_same(assignment, lambda g: g.dtype)


class SizeFilter(Filter):
    def __init__(self, variables, rows=None, cols=None, length=None, vectors=None, max_size=False):
        super().__init__(variables)
        self._rows = rows
        self._cols = cols
        self._length = length
        self._vectors = vectors
        self._max_size = max_size

    def test(self, assignment: Dict[str, Group]):
        groups = list([assignment[v.name] for v in self.variables])
        op = (lambda x, y: x <= y) if self._max_size else (lambda x, y: x >= y)
        return all(self._rows is None or op(g.rows(), self._rows) for g in groups) \
            and all(self._cols is None or op(g.columns(), self._cols) for g in groups) \
            and all(self._length is None or op(g.length(), self._length) for g in groups) \
            and all(self._vectors is None or op(g.vectors(), self._vectors) for g in groups)


class OrientationFilter(Filter):
    def __init__(self, variables, orientation):
        self._orientation = orientation
        super().__init__(variables)

    @property
    def orientation(self):
        return self._orientation

    def test(self, assignment: Dict[str, Group]):
        return self.test_all(assignment, lambda g: g.row == (self.orientation == Orientation.HORIZONTAL))


class NotPartial(Filter):
    def test(self, assignment: Dict[str, Group]):
        return not any([assignment[v.name].is_partial for v in self.variables])


class Partial(Filter):
    def test(self, assignment: Dict[str, Group]):
        return all([assignment[v.name].is_partial for v in self.variables])


class NotSubgroup(Filter):
    def test(self, assignment: Dict[str, Group]):
        if len(self.variables) != 2:
            raise RuntimeError("Expected two variables, got {}".format(len(self.variables)))
        return not assignment[self.variables[0].name].is_subgroup(assignment[self.variables[1].name])
