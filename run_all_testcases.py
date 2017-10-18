#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import subprocess
from webserver import TestWebServer
from testrunner import TestRunner
from junit_xml import TestSuite


def natural_sort(l):
    convert = lambda text: int(text) if text.isdigit() else text.lower()
    alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]
    return sorted(l, key=alphanum_key)


def gb_get_instance_path(gb_path, gb_instances, host_id):
    return '%s/instances%02d/%s' % (gb_path, gb_instances, str(host_id).zfill(3))


def gb_create_hostfile(gb_path, gb_instances, gb_shards, gb_port, port_offset=0):
    with open(os.path.join(gb_path, 'hosts.conf'), 'w') as f:
        num_mirrors = (gb_instances / gb_shards) - 1
        f.write('num-mirrors: %d\n' % num_mirrors)

        gb_mergepath = os.path.normpath(os.path.join(gb_path, 'instances%02d/merge' % gb_instances))

        dnsclient_port = gb_port - 2000 + port_offset
        https_port = gb_port - 1000 + port_offset
        http_port = gb_port + port_offset
        udp_port = gb_port + 1000 + port_offset

        for host_id in range(gb_instances):
            instance_path = gb_get_instance_path(gb_path, gb_instances, host_id)
            f.write('%d %d %d %d %d 127.0.0.1 127.0.0.1 %s %s\n' %
                    (host_id, dnsclient_port + host_id, https_port + host_id, http_port + host_id, udp_port + host_id,
                     instance_path, gb_mergepath))


def main(testdir, gb_path, gb_instances, gb_shards, gb_host, gb_port, ws_scheme, ws_domain, ws_port):
    executor_number = os.getenv('EXECUTOR_NUMBER')
    port_offset = 0 if executor_number is None else int(executor_number)

    # prepare gigablast
    gb_create_hostfile(gb_path, gb_instances, gb_shards, gb_port, port_offset)

    if gb_instances == gb_shards:
        host_id = 0
    else:
        host_id = gb_shards

    subprocess.call(['./gb', 'install'], cwd=gb_path, stdout=subprocess.DEVNULL)
    subprocess.call(['./gb', 'installfile', 'Makefile'], cwd=gb_path, stdout=subprocess.DEVNULL)

    spider_instance_path = gb_get_instance_path(gb_path, gb_instances, host_id)
    spider_instance_port = gb_port + port_offset + host_id

    # start webserver
    ws_port += port_offset
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
    parser.add_argument('--num-instances', dest="gb_instances", type=int, default=1, action='store',
                        help='Number of gigablast instances (default: 1)')
    parser.add_argument('--num-shards', dest="gb_shards", type=int, default=1, action='store',
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
    main(args.testdir, args.gb_path, args.gb_instances, args.gb_shards, args.gb_host, args.gb_port, args.ws_scheme, args.ws_domain, args.ws_port)
