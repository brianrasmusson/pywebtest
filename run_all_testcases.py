#!/usr/bin/env python3

import os
import re
from webserver import TestWebServer
from testrunner import TestRunner
from junit_xml import TestSuite


def natural_sort(l):
    convert = lambda text: int(text) if text.isdigit() else text.lower()
    alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]
    return sorted(l, key=alphanum_key)


# @todo ALC cater for multiple instance
def gb_create_hostfile(gb_path, port_offset=0):
    gb_mergepath = os.path.normpath(os.path.join(gb_path, '../merge'))
    with open(os.path.join(gb_path, 'hosts.conf'), 'w') as f:
        f.write(('num-mirrors: 0\n'
                 '0 %d %d %d %d 127.0.0.1 127.0.0.1 %s %s\n' %
                 (25998 + port_offset, 27000 + port_offset, 28000 + port_offset, 29000 + port_offset,
                  gb_path, gb_mergepath)))
    pass


def main(testdir, gb_path, gb_host, gb_port, ws_scheme, ws_domain, ws_port):
    # prepare gigablast
    gb_create_hostfile(gb_path)

    # start webserver
    test_webserver = TestWebServer(ws_port)

    # run testcases
    testcases = natural_sort(next(os.walk(args.testdir))[1])
    results = []
    for testcase in testcases:
        print('Running testcase -', testcase)
        test_webserver.clear_served_urls()
        test_runner = TestRunner(testdir, testcase, gb_path, gb_host, gb_port, test_webserver, ws_scheme, ws_domain, ws_port)
        results.append(test_runner.run_test())

    # stop webserver
    test_webserver.stop()

    # write output
    with open('output.xml', 'w') as f:
        TestSuite.to_file(f, results)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--testdir', dest='testdir', default='tests', action='store',
                        help='Directory containing test cases')

    default_gbpath = os.path.normpath(os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                   '../open-source-search-engine'))
    parser.add_argument('--path', dest='gb_path', default=default_gbpath, action='store',
                        help='Directory containing gigablast binary (default: {})'.format(default_gbpath))
    parser.add_argument('--host', dest='gb_host', default='127.0.0.1', action='store',
                        help='Gigablast host (default: 127.0.0.1)')
    parser.add_argument('--port', dest='gb_port', default='28000', action='store',
                        help='Gigablast port (default: 28000')

    parser.add_argument('--dest-scheme', dest='ws_scheme', default='http', action='store',
                        help='Destination host scheme (default: http)')
    parser.add_argument('--dest-domain', dest='ws_domain', default='privacore.test', action='store',
                        help='Destination host domain (default: privacore.test)')
    parser.add_argument('--dest-port', dest='ws_port', type=int, default=28080, action='store',
                        help='Destination host port (default: 28080')

    args = parser.parse_args()
    main(args.testdir, args.gb_path, args.gb_host, args.gb_port, args.ws_scheme, args.ws_domain, args.ws_port)
