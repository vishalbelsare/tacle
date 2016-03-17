from parser import *
from group_assign import *


def main(csv_file, groups_file):
	groups = get_groups_tables(csv_file, groups_file)
	print(len(groups))
	print(find_groups(SumColumn(), IDP(), groups))


def arg_parser():
	import argparse
	p = argparse.ArgumentParser()
	p.add_argument('csv_file')
	p.add_argument('groups_file')
	return p


if __name__ == '__main__':
	main(**vars(arg_parser().parse_args()))
