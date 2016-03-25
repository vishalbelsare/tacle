from engine import *
from constraint import *
from group import *


def find_groups(constraint: Constraint, engine: Engine, groups: [Group], solutions) -> [[Group]]:
	return engine.generate_groups(constraint, groups, solutions)
