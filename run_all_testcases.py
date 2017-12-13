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


def main(testdir, gb_offset, gb_path, gb_num_instances, gb_num_shards, gb_host, gb_port, ws_domain, ws_port, ws_sslport, ws_sslkey, ws_sslcert):
    # prepare gigablast
    gb_instances = GigablastInstances(gb_offset, gb_path, gb_num_instances, gb_num_shards, gb_port)

    # prepare webserver
    ws_port += gb_offset
    ws_sslport += gb_offset

    if not os.path.exists(ws_sslkey):
        subprocess.call(['./create_ssl_key.sh', ws_domain], stdout=subprocess.DEVNULL)

    if not os.path.exists(ws_sslcert):
        subprocess.call(['./create_ssl_cert.sh', ws_domain], stdout=subprocess.DEVNULL)

    # start webserver
    test_webserver = TestWebServer(ws_port, ws_sslport, ws_sslkey, ws_sslcert)

    # run testcases
    testcases = natural_sort(next(os.walk(args.testdir))[1])
    results = []
    for testcase in testcases:
        print('Running testcase -', testcase)
        test_webserver.clear_served_urls()
        test_runner = TestRunner(testdir, testcase, gb_instances, gb_host, test_webserver, ws_domain, ws_port, ws_sslport)
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
    parser.add_argument('--dest-domain', dest='ws_domain', default='privacore.test', action='store',
                        help='Destination host domain (default: privacore.test)')
    parser.add_argument('--dest-port', dest='ws_port', type=int, default=28080, action='store',
                        help='Destination host port (default: 28080')
    parser.add_argument('--dest-sslport', dest='ws_sslport', type=int, default=28443, action='store',
                        help='Destination host ssl port (default: 28443')
    parser.add_argument('--dest-sslkey', dest='ws_sslkey', default='privacore.test.key', action='store',
                        help='Destination host domain (default: privacore.test.key)')
    parser.add_argument('--dest-sslcert', dest='ws_sslcert', default='privacore.test.cert', action='store',
                        help='Destination host domain (default: privacore.test.cert)')

    args = parser.parse_args()
    main(args.testdir, args.gb_offset, args.gb_path, args.gb_num_instances, args.gb_num_shards, args.gb_host, args.gb_port, args.ws_domain, args.ws_port, args.ws_sslport, args.ws_sslkey, args.ws_sslcert)
