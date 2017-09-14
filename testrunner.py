#!/usr/bin/env python3

import os
import time
import subprocess
import requests
import sys
import glob
from gigablast import GigablastAPI
from junit_xml import TestSuite, TestCase


class TestRunner:
    def __init__(self, testdir, testcase, gb_path, gb_host, gb_port, webserver, ws_scheme, ws_domain, ws_port):
        self.testcase = testcase
        self.testcasedir = os.path.join(testdir, testcase)
        self.testcaseconfigdir = os.path.join(self.testcasedir, 'testcase')
        testcasedescpath = os.path.join(self.testcasedir, 'README')
        if os.path.exists(testcasedescpath):
            self.testcasedesc = self.read_file(testcasedescpath)[0].replace('.', '')
        else:
            self.testcasedesc = self.testcase

        self.gb_path = gb_path
        self.gb_starttime = 0

        self.api = GigablastAPI(gb_host, gb_port)

        self.webserver = webserver
        self.ws_scheme = ws_scheme
        self.ws_domain = ws_domain
        self.ws_port = ws_port

        self.testcases = []

    def run_test(self):
        # verify we have testcase to run
        if os.path.exists(self.testcaseconfigdir):
            # verify gb has started
            if self.start_gb():
                if not self.run_instructions():
                    self.run_testcase()

                # stop & cleanup
                self.stop_gb()

        return self.get_testsuite()

    @staticmethod
    def read_file(filename):
        if os.path.exists(filename):
            with open(filename, 'r') as file:
                return file.read().splitlines()

        return []

    def start_gb(self):
        print('Cleaning old data')
        subprocess.call(['make', 'cleantest'], cwd=self.gb_path, stdout=subprocess.DEVNULL)

        print('Starting gigablast')
        start_time = time.perf_counter()

        subprocess.call(['./gb', 'start'], cwd=self.gb_path, stdout=subprocess.DEVNULL)

        # wait until started
        result = True
        while result:
            try:
                self.update_processuptime()

                # set some default config
                self.config_gb()

                # put some delay after start
                time.sleep(1)
                break
            except requests.exceptions.ConnectionError as e:
                # wait for a max of 300 seconds
                if time.perf_counter() - start_time > 300:
                    result = False
                    break
                time.sleep(0.5)

        self.add_testcase('pre', 'start', start_time, not result)
        return result

    def save_gb(self):
        print('Saving gigablast')
        subprocess.call(['./gb', 'save'], cwd=self.gb_path, stderr=subprocess.DEVNULL)

        # wait for gb mode to be updated
        time.sleep(0.5)

    def stop_gb(self):
        print('Stopping gigablast')
        subprocess.call(['./gb', 'stop'], cwd=self.gb_path, stderr=subprocess.DEVNULL)

    def config_gb(self):
        self.api.config_crawldelay(0, 0)
        self.api.config_dns('127.0.0.1')

        # log debug query
        self.api.config_log({'ldq': '1'})
        self.api.config_log({'ltrc_sp': '1'})
        self.api.config_log({'ltrc_msgfour': '1'})
        self.api.config_log({'ltrc_xmldoc': '1'})

    def run_instructions(self):
        # check instruction file
        filenames = sorted(glob.glob(os.path.join(self.testcaseconfigdir, 'instructions*')))
        for filename in filenames:
            print('Processing', os.path.basename(filename))
            instructions = self.read_file(filename)

            for instruction in instructions:
                tokens = instruction.split()
                token = tokens.pop(0)
                func = getattr(self, token, None)
                if func is not None:
                    func(*tokens)
                else:
                    print('Unknown instruction -', token)

        return len(filenames)

    def run_testcase(self):
        # seed gb
        self.seed()

        # verify gb has done spidering (only run other test if spidering is successful)
        if self.wait_spider_done():
            # search
            self.just_search()

            # verify indexed
            self.verify_indexed()

            # verify not indexed
            self.verify_not_indexed()

            # verify spidered
            self.verify_spidered()

            # verify not spidered
            self.verify_not_spidered()

    def seed(self, *args):
        print('Adding seed for spidering')

        if len(args):
            if len(args[0]):
                seedstr = args[0].format(SCHEME=self.ws_scheme, DOMAIN=self.ws_domain, PORT=self.ws_port) + '\n'
        else:
            filename = os.path.join(self.testcaseconfigdir, 'seeds')
            items = self.read_file(filename)
            seedstr = ""
            if len(items):
                for item in items:
                    seedstr += item.format(SCHEME=self.ws_scheme, DOMAIN=self.ws_domain, PORT=self.ws_port) + '\n'

        if len(seedstr) == 0:
            # default seed
            for entry in os.scandir(self.testcasedir):
                if entry.is_dir() and entry.name != 'testcase':
                    seedstr += "{}://{}.{}.{}:{}/\n".format(self.ws_scheme, entry.name, self.testcase,
                                                            self.ws_domain, self.ws_port)

        seedstr = seedstr.rstrip('\n')
        self.api.config_sitelist(seedstr)

    def wait_spider_done(self, *args):
        print('Waiting for spidering to complete')
        start_time = time.perf_counter()

        # wait until
        #   - spider is in progress
        #   - waitingTree spider time is more than an hour
        #   - no pending doleIP
        #   - nothing is being spidered
        result = True
        while result:
            try:
                response = self.api.get_spiderqueue()['response']
                print(response)
            except:
                result = False
                break

            if response['statusCode'] == 7 and response['doleIPCount'] == 0 and response['spiderCount'] == 0:
                if response['waitingTreeCount'] > 0:
                    has_pending_spider = False
                    for waiting_tree in response['waitingTrees']:
                        if waiting_tree['spiderTime'] < ((time.time() + 3600) * 1000):
                            has_pending_spider = True

                    if not has_pending_spider:
                        self.save_gb()
                        break

            # wait for a max of 300 seconds
            if time.perf_counter() - start_time > 300:
                print(response)
                result = False
                break

            time.sleep(0.5)

        self.add_testcase('pre', 'spider', start_time, not result)

        served_urls = self.webserver.get_served_urls()
        for served_url in served_urls:
            print('Spidered ', served_url)

        return result

    def add_testcase(self, test_type, test_item, start_time, failed=False):
        test_name = test_type + ' - ' + test_item
        testcase = TestCase(test_name,
                            classname='systemtest.' + self.testcasedesc,
                            elapsed_sec=(time.perf_counter() - start_time))
        if failed:
            testcase.add_failure_info(test_name + ' - failed')

        if not self.validate_processuptime():
            testcase.add_failure_info(test_name + ' - gb restarted')
            self.update_processuptime()

        self.testcases.append(testcase)

    def get_testsuite(self):
        return TestSuite(self.testcase, test_cases=self.testcases, package='systemtest')

    def validate_processuptime(self):
        return self.api.status_processstarttime() == self.gb_starttime

    def update_processuptime(self):
        self.gb_starttime = self.api.status_processstarttime()

    def dump(self, *args):
        start_time = time.perf_counter()
        self.api.dump()
        self.add_testcase('dump', '', start_time)

    def just_search(self, *args):
        test_type = 'just_search'
        print('Running test -', test_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for index, item in enumerate(items):
            start_time = time.perf_counter()
            try:
                response = self.api.search(item)
                self.add_testcase(test_type, item, start_time)
            except:
                self.add_testcase(test_type, item, start_time, True)

    def verify_indexed(self, *args):
        test_type = 'verify_indexed'
        print('Running test -', test_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for index, item in enumerate(items):
            start_time = time.perf_counter()
            try:
                response = self.api.search(item)

                failed = (not len(response['results']) != 0)
                if failed:
                    print(response)

                self.add_testcase(test_type, item, start_time, failed)
            except:
                self.add_testcase(test_type, item, start_time, True)

    def verify_not_indexed(self, *args):
        test_type = 'verify_not_indexed'
        print('Running test -', test_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for index, item in enumerate(items):
            start_time = time.perf_counter()
            try:
                response = self.api.search(item)

                failed = (not len(response['results']) == 0)
                if failed:
                    print(response)

                self.add_testcase(test_type, item, start_time, failed)
            except:
                self.add_testcase(test_type, item, start_time, True)

    def verify_spidered(self, *args):
        test_type = 'verify_spidered'
        print('Running test -', test_type)

        items = []
        if len(args):
            items.append(args[0])
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        served_urls = self.webserver.get_served_urls()
        for index, item in enumerate(items):
            start_time = time.perf_counter()
            try:
                url = item.format(SCHEME=self.ws_scheme, DOMAIN=self.ws_domain, PORT=self.ws_port)
                failed = (url not in served_urls)

                self.add_testcase(test_type, item, start_time, failed)
            except:
                self.add_testcase(test_type, item, start_time, True)

    def verify_not_spidered(self, *args):
        test_type = 'verify_not_spidered'
        print('Running test -', test_type)

        items = []
        if len(args):
            items.append(args[0])
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        served_urls = self.webserver.get_served_urls()
        for index, item in enumerate(items):
            start_time = time.perf_counter()
            try:
                url = item.format(SCHEME=self.ws_scheme, DOMAIN=self.ws_domain, PORT=self.ws_port)
                failed = (url in served_urls)

                self.add_testcase(test_type, item, start_time, failed)
            except:
                self.add_testcase(test_type, item, start_time, True)


def main(testdir, testcase, gb_path, gb_host, gb_port, ws_scheme, ws_domain, ws_port):
    test_runner = TestRunner(testdir, testcase, gb_path, gb_host, gb_port, ws_scheme, ws_domain, ws_port)
    result = test_runner.run_test()
    print(TestSuite.to_xml_string([result]))


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('testcase', help='Test case to run')
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
                        help='Destination host scheme (default: 127.0.0.1)')
    parser.add_argument('--dest-domain', dest='ws_domain', default='privacore.test', action='store',
                        help='Destination host domain (default: privacore.test)')
    parser.add_argument('--dest-port', dest='ws_port', type=int, default=28080, action='store',
                        help='Destination host port (default: 28080')

    args = parser.parse_args()

    main(args.testdir, args.testcase, args.gb_path, args.gb_host, args.gb_port,
         args.ws_scheme, args.ws_domain, args.ws_port)
