#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from gigablast import GigablastInstances
import os
import subprocess


def main(gb_offset, gb_path, gb_num_instances, gb_num_shards, gb_port):
    gb_instances = GigablastInstances(gb_offset, gb_path, gb_num_instances, gb_num_shards, gb_port)
    instance_path = gb_instances.get_instance_path(0)

    try:
        subprocess.call(['./gb', 'stop'], cwd=instance_path, stderr=subprocess.DEVNULL, timeout=5)
    except subprocess.TimeoutExpired:
        pass


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument('--offset', dest='gb_offset', type=int, default=0, action='store',
                        help='Gigablast offset for running multiple gb at the same time (default: 0)')
    default_gbpath = os.path.normpath(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                   '../open-source-search-engine'))
    parser.add_argument('--path', dest='gb_path', default=default_gbpath, action='store',
                        help='Directory containing gigablast binary (default: {})'.format(default_gbpath))
    parser.add_argument('--num-instances', dest="gb_num_instances", type=int, default=1, action='store',
                        help='Number of gigablast instances (default: 1)')
    parser.add_argument('--num-shards', dest="gb_num_shards", type=int, default=1, action='store',
                        help='Number of gigablast shards (default: 1)')
    parser.add_argument('--port', dest='gb_port', type=int, default=28000, action='store',
                        help='Gigablast port (default: 28000')

    args = parser.parse_args()
    main(args.gb_offset, args.gb_path, args.gb_num_instances, args.gb_num_shards, args.gb_port)
