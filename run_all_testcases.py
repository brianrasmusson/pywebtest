#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import subprocess
from webserver import TestWebServer
from testrunner import TestRunner
from junit_xml import TestSuite
from gigablast import GigablastInstances


def natural_sort(l):
    convert = lambda text: int(text) if text.isdigit() else text.lower()
    alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]
    return sorted(l, key=alphanum_key)


def main(testdir, gb_offset, gb_path, gb_num_instances, gb_num_shards, gb_host, gb_port, ws_scheme, ws_domain, ws_port):
    # prepare gigablast
    gb_instances = GigablastInstances(gb_offset, gb_path, gb_num_instances, gb_num_shards, gb_port)

    if gb_num_instances == gb_num_shards:
        host_id = 0
    else:
        host_id = gb_num_shards

    spider_instance_path = gb_instances.get_instance_path(host_id)
    spider_instance_port = gb_instances.get_instance_port(host_id)

    # start webserver
    ws_port += gb_offset
    test_webserver = TestWebServer(ws_port)

    # run testcases
    testcases = natural_sort(next(os.walk(args.testdir))[1])
    results = []
    for testcase in testcases:
        print('Running testcase -', testcase)
        test_webserver.clear_served_urls()
        test_runner = TestRunner(testdir, testcase, spider_instance_path, gb_host, spider_instance_port, test_webserver, ws_scheme, ws_domain, ws_port)
        results.append(test_runner.run_test())

    # stop webserver
    test_webserver.stop()

    # write output
    with open('output%02d.xml' % gb_offset, 'w') as f:
        TestSuite.to_file(f, results)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--testdir', dest='testdir', default='tests', action='store',
                        help='Directory containing test cases')

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
    parser.add_argument('--host', dest='gb_host', default='127.0.0.1', action='store',
                        help='Gigablast host (default: 127.0.0.1)')
    parser.add_argument('--port', dest='gb_port', type=int, default=28000, action='store',
                        help='Gigablast port (default: 28000')
    parser.add_argument('--dest-scheme', dest='ws_scheme', default='http', action='store',
                        help='Destination host scheme (default: http)')
    parser.add_argument('--dest-domain', dest='ws_domain', default='privacore.test', action='store',
                        help='Destination host domain (default: privacore.test)')
    parser.add_argument('--dest-port', dest='ws_port', type=int, default=28080, action='store',
                        help='Destination host port (default: 28080')

    args = parser.parse_args()
    main(args.testdir, args.gb_offset, args.gb_path, args.gb_num_instances, args.gb_num_shards, args.gb_host, args.gb_port, args.ws_scheme, args.ws_domain, args.ws_port)
