import fnmatch
from typing import List, Union

import numpy as np
import csv

from .convert import get_tables, get_blocks
from .detect import detect_table_ranges, get_type_data
from .learn import learn_constraints
from .core.solutions import Constraint


def parse_csv(csv_file):
    data = []
    with open(csv_file) as f:
        csv_reader = csv.reader(f, delimiter=',')
        max_length = 0
        for row in csv_reader:
            max_length = max(max_length, len(row))
            data.append(row)

    # Fill rows to max length
    for i in range(len(data)):
        data[i] += ["" for _ in range(max_length - len(data[i]))]

    return data


def learn_from_csv(csv_file, filters=None):
    return learn_from_cells(parse_csv(csv_file), filters)


def learn_from_cells(data, filters=None):
    data = np.array(data, dtype=object)
    type_data = get_type_data(data)
    t_ranges = detect_table_ranges(type_data)
    constraints = learn_constraints(data, t_ranges).constraints
    if filters is not None:
        constraints = filter_constraints(filters)
    return constraints


def ranges_from_csv(csv_file):
    return ranges_from_cells(parse_csv(csv_file))


def ranges_from_cells(data):
    data = np.array(data, dtype=object)
    type_data = get_type_data(data)
    t_ranges = detect_table_ranges(type_data)
    return t_ranges


def tables_from_csv(csv_file):
    return ranges_from_cells(parse_csv(csv_file))


def tables_from_cells(data):
    data = np.array(data, dtype=object)
    type_data = get_type_data(data)
    return get_tables(data, type_data, detect_table_ranges(type_data))


def filter_constraints(constraints, *args):
    # type: (List[Constraint], List[Union[str, type]]) -> List[Constraint]

    all_formulas = "<formula>" in args or "<f>" in args
    all_constraints = "<constraint>" in args or "<c>" in args

    def check(_c):
        # type: (Constraint) -> bool
        if all_formulas and _c.is_formula():
            return True
        elif all_constraints and not _c.is_formula():
            return True
        return any(
            fnmatch.fnmatch(_c.template.name, pattern) if isinstance(pattern, str) else isinstance(_c.template, pattern)
            for pattern in args
        )

    return [c for c in constraints if check(c)]
