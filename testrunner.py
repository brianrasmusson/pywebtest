#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import subprocess
import requests
import sys
import glob
import shutil
import ast
from gigablast import GigablastAPI, GigablastInstances, GigablastUtils
from junit_xml import TestSuite, TestCase
from urllib.parse import parse_qs


class TestRunner:
    def __init__(self, testdir, testcase, gb_instances, gb_host, webserver, ws_domain, ws_port, ws_sslport):
        self.testcase = testcase
        self.testcasedir = os.path.join(testdir, testcase)
        self.testcaseconfigdir = os.path.join(self.testcasedir, 'testcase')
        testcasedescpath = os.path.join(self.testcasedir, 'README')
        if os.path.exists(testcasedescpath):
            self.testcasedesc = self.read_file(testcasedescpath)[0].replace('.', '')
        else:
            self.testcasedesc = self.testcase

        self.gb_instances = gb_instances

        self.gb_path = gb_instances.get_instance_path(0)
        self.gb_starttime = 0

        self.spider_apis = []
        if self.gb_instances.num_instances == self.gb_instances.num_shards:
            host_offset = 0
        else:
            host_offset = self.gb_instances.num_shards

        for i in range(self.gb_instances.num_shards):
            self.spider_apis.append(GigablastAPI(gb_host, self.gb_instances.get_instance_port(host_offset + i)))

        self.api = self.spider_apis[0]

        self.gb_util = GigablastUtils()

        self.webserver = webserver
        self.ws_domain = ws_domain
        self.ws_port = ws_port
        self.ws_sslport = ws_sslport

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

    def format_url(self, url):
        return url.format(DOMAIN=self.ws_domain, PORT=self.ws_port, SSLPORT=self.ws_sslport)

    def start_gb(self):
        print('Cleaning old data')
        subprocess.call(['./gb', 'dsh2', 'make cleantest'], cwd=self.gb_path, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.webserver.clear_served_urls()

        print('Copy config files')
        for filename in glob.glob(os.path.join(self.testcaseconfigdir, '*.txt')):
            destfile = shutil.copy(filename, self.gb_path)
            lines = self.read_file(destfile)
            with open(destfile, 'w') as file:
                for line in lines:
                    file.write(self.format_url(line) + '\n')

            subprocess.call(['./gb', 'installfile', os.path.basename(filename)], cwd=self.gb_path)

        print('Starting gigablast')
        start_time = time.perf_counter()

        subprocess.call(['./gb', 'start'], cwd=self.gb_path, stdout=subprocess.DEVNULL)

        # wait until started
        result = True
        while result:
            try:
                # wait until gb is initialized
                self.wait_processup()

                self.update_processuptime()

                # set some default/custom config
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

        # enable debug/trace logs
        self.api.config_log({'ldq': '1'})
        self.api.config_log({'ltd': '1'})
        self.api.config_log({'ldspid': '1'})
        self.api.config_log({'ltrc_sp': '1'})
        self.api.config_log({'ltrc_msgfour': '1'})
        self.api.config_log({'ltrc_xmldoc': '1'})

        # apply custom config
        self.custom_config()

    def run_instructions(self):
        # check instruction file
        filenames = sorted(glob.glob(os.path.join(self.testcaseconfigdir, 'instructions*')))
        for filename in filenames:
            print('Processing', os.path.basename(filename))
            instructions = self.read_file(filename)

            for instruction in instructions:
                # skip comment
                if len(instruction) == 0 or instruction.startswith('#'):
                    continue

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
            # verify query language
            self.verify_query_language()

            # verify query terms
            self.verify_query_terms()

            # search
            self.just_search()

            # verify indexed
            self.verify_indexed()

            # verify not indexed
            self.verify_not_indexed()

            # verify search result url
            self.verify_search_result_url()

            # verify search result title & summary
            self.verify_search_result_titlesummary()

            # verify spidered
            self.verify_spidered()

            # verify only spidered
            self.verify_only_spidered()

            # verify not spidered
            self.verify_not_spidered()

            # verify spider response
            self.verify_spider_response()

            # verify title record
            self.verify_title_record()

            # verify no title record
            self.verify_no_title_record()

    @staticmethod
    def convert_config_log(tokens):
        it = iter(tokens)
        return dict(zip(it, it))

    @staticmethod
    def convert_config_master(tokens):
        it = iter(tokens)
        return dict(zip(it, it))

    @staticmethod
    def convert_config_search(tokens):
        it = iter(tokens)
        return dict(zip(it, it))

    def custom_config(self, *args):
        print('Applying custom config')
        file_name = 'custom_config'

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, file_name)
            items = self.read_file(filename)

        for item in items:
            tokens = item.split()
            token = tokens.pop(0)

            convert_func = getattr(self, 'convert_' + token, None)
            func = getattr(self.api, token, None)
            if func is not None:
                if convert_func is not None:
                    func(convert_func(tokens))
                else:
                    func(*tokens)
            else:
                print('Unknown instruction -', token)

    def seed(self, *args):
        print('Adding seed for spidering')

        if len(args):
            seedstr = '\n'.join(args)
            if len(seedstr):
                seedstr = self.format_url(seedstr) + '\n'
        else:
            filename = os.path.join(self.testcaseconfigdir, 'seeds')
            items = self.read_file(filename)
            seedstr = ""
            if len(items):
                for item in items:
                    seedstr += self.format_url(item) + '\n'

        if len(seedstr) == 0:
            # default seed
            for entry in os.scandir(self.testcasedir):
                if entry.is_dir() and entry.name != 'testcase':
                    seedstr += "http://{}.{}.{}:{}/\n".format(entry.name, self.testcase, self.ws_domain, self.ws_port)

        seedstr = seedstr.rstrip('\n')
        print(seedstr)

        self.api.config_sitelist(seedstr)

    def wait_spider_done(self, *args):
        print('Waiting for spidering to complete')

        # wait until
        #   - spider is in progress
        #   - waitingTree spider time is more than an hour
        #   - no pending doleIP
        #   - nothing is being spidered
        for spider_api in self.spider_apis:
            start_time = time.perf_counter()

            result = True
            while result:
                try:
                    response = spider_api.get_spiderqueue()['response']
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
                            print('no pending spider')
                            break
                    else:
                        # wait for 5 seconds
                        if time.perf_counter() - start_time > 5:
                            print('waitingTreeCount=0 more than 5 seconds')
                            break

                if response['statusCode'] == 0:
                    # we only wait for 5 seconds if it's initializing
                    if time.perf_counter() - start_time > 5:
                        print('statusCode=0 more than 5 seconds')
                        break

                # wait for a max of 180 seconds
                if time.perf_counter() - start_time > 180:
                    print('more than 180 seconds')
                    result = False
                    break

                time.sleep(1.0)

            if result:
                self.save_gb()

            self.add_testcase('pre', 'spider', start_time, not result)

        served_urls = self.webserver.get_served_urls()
        for served_url in served_urls:
            print('Spidered ', served_url)

        return result

    def add_testcase(self, test_type, test_item, start_time, failed=False):
        test_name = test_type + ' - ' + test_item
        testcase = TestCase(test_name,
                            classname='systemtest.' + str(self.gb_instances.offset) + '.' + self.testcasedesc,
                            elapsed_sec=(time.perf_counter() - start_time))
        if failed:
            testcase.add_failure_info(test_name + ' - failed')
        elif not self.validate_processuptime():
            testcase.add_failure_info(test_name + ' - gb restarted')
            self.update_processuptime()

        self.testcases.append(testcase)

    def get_testsuite(self):
        return TestSuite(self.testcase, test_cases=self.testcases, package='systemtest')

    def wait_processup(self):
        for spider_api in self.spider_apis:
            start_time = time.perf_counter()

            while True:
                response = spider_api.status()
                if response['response']['statusCode'] == 0 or response['response']['statusCode'] == 7:
                    # SP_INITIALIZING / SP_INPROGRESS
                    break

                # wait for a max of 60 seconds
                if time.perf_counter() - start_time > 60:
                    print(response)
                    break

                time.sleep(0.5)

    def validate_processuptime(self):
        return self.api.status_processstarttime() == self.gb_starttime

    def update_processuptime(self):
        self.gb_starttime = self.api.status_processstarttime()

    def doc_delete(self, *args):
        action_type = 'doc_delete'
        print('Running action -', action_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()
            key = self.format_url(item)
            docid = str(self.gb_util.calculate_probable_docid(key))

            try:
                response = self.api.doc_delete(docid)
                self.add_testcase(action_type, key + ' - ' + docid, start_time)
            except Exception as e:
                print(e)
                self.add_testcase(action_type, key + ' - ' + docid, start_time, True)

        # wait for msg4 to be processed
        time.sleep(0.5)

    def doc_delete_url(self, *args):
        action_type = 'doc_delete_url'
        print('Running action -', action_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()
            key = self.format_url(item)

            try:
                response = self.api.doc_delete(key)
                self.add_testcase(action_type, key, start_time)
            except Exception as e:
                print(e)
                self.add_testcase(action_type, key, start_time, True)

        # wait for msg4 to be processed
        time.sleep(0.5)

    def doc_rebuild(self, *args):
        action_type = 'doc_rebuild'
        print('Running action -', action_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()
            key = self.format_url(item)
            docid = str(self.gb_util.calculate_probable_docid(key))

            try:
                response = self.api.doc_rebuild(docid)
                self.add_testcase(action_type, key + ' - ' + docid, start_time)
            except Exception as e:
                print(e)
                self.add_testcase(action_type, key + ' - ' + docid, start_time, True)

        # wait for msg4 to be processed
        time.sleep(0.5)

    def doc_rebuild_url(self, *args):
        action_type = 'doc_rebuild_url'
        print('Running action -', action_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()
            key = self.format_url(item)

            try:
                response = self.api.doc_rebuild(key)
                self.add_testcase(action_type, key, start_time)
            except Exception as e:
                print(e)
                self.add_testcase(action_type, key, start_time, True)

        # wait for msg4 to be processed
        time.sleep(0.5)

    def doc_reindex(self, *args):
        action_type = 'doc_reindex'
        print('Running action -', action_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()
            key = self.format_url(item)
            docid = str(self.gb_util.calculate_probable_docid(key))

            try:
                response = self.api.doc_reindex(docid)
                self.add_testcase(action_type, key + ' - ' + docid, start_time)
            except Exception as e:
                print(e)
                self.add_testcase(action_type, key + ' - ' + docid, start_time, True)

        # wait for msg4 to be processed
        time.sleep(0.5)

    def doc_reindex_url(self, *args):
        action_type = 'doc_reindex_url'
        print('Running action -', action_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()
            key = self.format_url(item)

            try:
                response = self.api.doc_reindex(key)
                self.add_testcase(action_type, key, start_time)
            except Exception as e:
                print(e)
                self.add_testcase(action_type, key, start_time, True)

        # wait for msg4 to be processed
        time.sleep(0.5)

    def dump(self):
        action_type = 'dump'
        print('Running action -', action_type)

        start_time = time.perf_counter()
        self.api.dump()
        self.add_testcase(action_type, '', start_time)

    def just_search(self, *args):
        test_type = 'just_search'
        print('Running test -', test_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()
            try:
                response = self.api.search(item)
                self.add_testcase(test_type, item, start_time)
            except:
                self.add_testcase(test_type, item, start_time, True)

    def inject_document(self, *args):
        action_type = 'inject_document'
        print('Running action -', action_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, action_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()

            tokens = item.split('|')
            if len(tokens) != 2:
                print('Invalid format ', item)
                self.add_testcase(action_type, item, start_time, True)
                return

            url = self.format_url(tokens[0])
            content = tokens[1]

            try:
                response = self.api.inject_document(url, content)
                self.add_testcase(action_type, item, start_time)
            except:
                self.add_testcase(action_type, item, start_time, True)

        # put some delay after injection
        time.sleep(1)

    def insert_tagdb(self, *args):
        action_type = 'insert_tagdb'
        print('Running action -', action_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, action_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()

            tokens = item.split('|')
            if len(tokens) != 3:
                print('Invalid format ', item)
                self.add_testcase(action_type, item, start_time, True)
                return

            url = self.format_url(tokens[0])
            name = tokens[1]
            value = tokens[2]

            try:
                response = self.api.insert_tagdb(url, name, value)
                self.add_testcase(action_type, item, start_time)
            except:
                self.add_testcase(action_type, item, start_time, True)

    def verify_indexed(self, *args):
        test_type = 'verify_indexed'
        print('Running test -', test_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()
            try:
                response = self.api.search(item)

                failed = (not len(response['results']) != 0)
                if failed:
                    print(test_type + ' - ' + item)
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

        for item in items:
            start_time = time.perf_counter()
            try:
                response = self.api.search(item)

                failed = (not len(response['results']) == 0)
                if failed:
                    print(test_type + ' - ' + item)
                    print(response)

                self.add_testcase(test_type, item, start_time, failed)
            except:
                self.add_testcase(test_type, item, start_time, True)

    def verify_query_language(self, *args):
        test_type = 'verify_query_language'
        print('Running test -', test_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()

            tokens = item.split('|')
            if len(tokens) != 3:
                print('Invalid format ', item)
                self.add_testcase(test_type, query, start_time, True)
                return

            query = tokens[0]
            query_param = tokens[1]
            language = tokens[2]

            try:
                response = self.api.search(query, parse_qs(query_param))
                failed = (not response['queryInfo']['queryLanguageAbbr'] == language)

                if failed:
                    print(test_type + ' - ' + query + ' - ' + query_param)
                    print(response)

                self.add_testcase(test_type, query + ' - ' + query_param, start_time, failed)
            except:
                self.add_testcase(test_type, query + ' - ' + query_param, start_time, True)

    def verify_query_terms(self, *args):
        test_type = 'verify_query_terms'
        print('Running test -', test_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()

            tokens = item.split('|')

            query = tokens.pop(0)
            if len(tokens) == 0:
                print('Invalid format ', item)
                self.add_testcase(test_type, query, start_time, True)
                return

            query_param = tokens.pop(0)
            if len(tokens) == 0:
                print('Invalid format ', item)
                self.add_testcase(test_type, query, start_time, True)
                return

            num_terms = int(tokens.pop(0))
            if len(tokens) != num_terms:
                print('Invalid format ', item)
                self.add_testcase(test_type, query, start_time, True)
                return

            try:
                response = self.api.search(query, parse_qs(query_param))

                failed = (not response['queryInfo']['queryNumTermsTotal'] == num_terms)
                if not failed:
                    for index, token in enumerate(tokens):
                        term = response['queryInfo']['terms'][index]['termStr']

                        if token != term:
                            failed = True
                            break

                if failed:
                    print(test_type + ' - ' + item)
                    print(response)

                self.add_testcase(test_type, query, start_time, failed)
            except:
                self.add_testcase(test_type, query, start_time, True)

    def verify_search_result_url(self, *args):
        test_type = 'verify_search_result_url'
        print('Running test -', test_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()

            tokens = item.split('|')

            query = self.format_url(tokens.pop(0))
            if len(tokens) == 0:
                print('Invalid format ', item)
                self.add_testcase(test_type, query, start_time, True)
                return

            query_param = tokens.pop(0)
            if len(tokens) == 0:
                print('Invalid format ', item)
                self.add_testcase(test_type, query, start_time, True)
                return

            num_results = int(tokens.pop(0))
            if len(tokens) != num_results:
                print('Invalid format ', item)
                self.add_testcase(test_type, query, start_time, True)
                return

            results = []
            for token in tokens:
                results.append(self.format_url(token))

            try:
                response = self.api.search(query, parse_qs(query_param))

                failed = (not len(response['results']) == num_results)
                if not failed:
                    for index in range(num_results):
                        url = response['results'][index]['url']

                        # gb doesn't return url with scheme when it's http
                        if not url.startswith('https://'):
                            url = 'http://' + url

                        if url not in results:
                            failed = True
                            break

                if failed:
                    print(test_type + ' - ' + query + ' - ' + query_param)
                    print(response)

                self.add_testcase(test_type, query, start_time, failed)
            except:
                self.add_testcase(test_type, query, start_time, True)

    def verify_search_result_titlesummary(self, *args):
        test_type = 'verify_search_result_titlesummary'
        print('Running test -', test_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()

            tokens = item.split('|')

            query = self.format_url(tokens.pop(0))
            if len(tokens) == 0:
                print('Invalid format ', item)
                self.add_testcase(test_type, query, start_time, True)
                return

            query_param = tokens.pop(0)
            if len(tokens) == 0:
                print('Invalid format ', item)
                self.add_testcase(test_type, query + ' - ' + query_param, start_time, True)
                return

            num_results = int(tokens.pop(0))
            if len(tokens) != num_results * 2:
                print('Invalid format ', item)
                self.add_testcase(test_type, query + ' - ' + query_param, start_time, True)
                return

            it = iter(tokens)
            results = zip(it, it)

            try:
                response = self.api.search(query, parse_qs(query_param))

                failed = (not len(response['results']) == num_results)
                if not failed:
                    for index, (title, summary) in enumerate(results):
                        r_title = response['results'][index]['title']
                        r_summary = response['results'][index]['sum']

                        if self.format_url(title) != r_title or summary != r_summary:
                            failed = True
                            break

                if failed:
                    print(test_type + ' - ' + query + ' - ' + query_param)
                    print(response)

                self.add_testcase(test_type, query + ' - ' + query_param, start_time, failed)
            except Exception as e:
                print(e)
                self.add_testcase(test_type, query + ' - ' + query_param, start_time, True)

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
        for item in items:
            start_time = time.perf_counter()
            try:
                url = self.format_url(item)
                failed = (url not in served_urls)

                if failed:
                    print(test_type + ' - ' + url)

                self.add_testcase(test_type, item, start_time, failed)
            except:
                self.add_testcase(test_type, item, start_time, True)

    def verify_only_spidered(self, *args):
        test_type = 'verify_only_spidered'
        print('Running test -', test_type)

        items = []
        if len(args):
            items.append(args[0])
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        if len(items):
            served_urls = self.webserver.get_served_urls()

            start_time = time.perf_counter()

            formated_items = []
            for item in items:
                formated_items.append(self.format_url(item))

            for url in formated_items:
                self.add_testcase(test_type, url, start_time, (url not in served_urls))

            for url in served_urls:
                if url not in formated_items:
                    self.add_testcase(test_type, url, start_time, True)

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
                url = self.format_url(item)
                failed = (url in served_urls)

                if failed:
                    print(test_type + ' - ' + url)

                self.add_testcase(test_type, item, start_time, failed)
            except:
                self.add_testcase(test_type, item, start_time, True)

    def verify_spider_request(self, *args):
        test_type = 'verify_spider_request'
        print('Running test -', test_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()

            tokens = item.split('|')
            if len(tokens) != 2:
                print('Invalid format ', item)
                self.add_testcase(test_type, item, start_time, True)
                return

            url = self.format_url(tokens.pop(0))

            result = ast.literal_eval(tokens.pop(0))
            if type(result) is not dict:
                print('Invalid format ', item)
                self.add_testcase(test_type, item, start_time, True)
                return

            try:
                response = self.api.lookup_spiderdb(url)

                failed = ('spiderRequest' not in response)
                if not failed:
                    for key, value in result.items():
                        if response['spiderRequest'][key] != value:
                            failed = True
                            break

                if failed:
                    print(test_type + ' - ' + url + ' - ' + str(result))
                    print(response)

                self.add_testcase(test_type, url + ' - ' + str(result), start_time, failed)
            except Exception as e:
                print(e)
                self.add_testcase(test_type, url + ' - ' + str(result), start_time, True)

    def verify_no_spider_request(self, *args):
        test_type = 'verify_no_spider_request'
        print('Running test -', test_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()

            url = self.format_url(item)

            try:
                response = self.api.lookup_spiderdb(url)

                failed = ('spiderRequest' in response)
                if failed:
                    print(test_type + ' - ' + url)
                    print(response)

                self.add_testcase(test_type, url, start_time, failed)
            except Exception as e:
                print(e)
                self.add_testcase(test_type, url, start_time, True)

    def verify_spider_response(self, *args):
        test_type = 'verify_spider_response'
        print('Running test -', test_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()

            tokens = item.split('|')
            if len(tokens) != 2:
                print('Invalid format ', item)
                self.add_testcase(test_type, item, start_time, True)
                return

            url = self.format_url(tokens.pop(0))

            result = ast.literal_eval(tokens.pop(0))
            if type(result) is not dict:
                print('Invalid format ', item)
                self.add_testcase(test_type, item, start_time, True)
                return

            try:
                response = self.api.lookup_spiderdb(url)

                failed = ('spiderReply' not in response)
                if not failed:
                    for key, value in result.items():
                        if response['spiderReply'][key] != value:
                            failed = True
                            break

                if failed:
                    print(test_type + ' - ' + url + ' - ' + str(result))
                    print(response)

                self.add_testcase(test_type, url + ' - ' + str(result), start_time, failed)
            except Exception as e:
                print(e)
                self.add_testcase(test_type, url + ' - ' + str(result), start_time, True)

    def verify_no_spider_response(self, *args):
        test_type = 'verify_no_spider_response'
        print('Running test -', test_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()

            url = self.format_url(item)

            try:
                response = self.api.lookup_spiderdb(url)

                failed = ('spiderReply' in response)
                if failed:
                    print(test_type + ' - ' + url)
                    print(response)

                self.add_testcase(test_type, url, start_time, failed)
            except Exception as e:
                print(e)
                self.add_testcase(test_type, url, start_time, True)

    def verify_linkdb_record(self, *args):
        test_type = 'verify_linkdb_record'
        print('Running test -', test_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()

            tokens = item.split('|')
            if len(tokens) != 2:
                print('Invalid format ', item)
                self.add_testcase(test_type, item, start_time, True)
                return

            url = self.format_url(tokens.pop(0))

            try:
                response = self.api.lookup_linkdb(url)
                # print(response)

                failed = (len(response['results']) == 0)
                if failed:
                    print(test_type + ' - ' + url)
                    print(response)
                    self.add_testcase(test_type, url, start_time, failed)
                else:
                    for idx, token in enumerate(tokens):
                        linker_url = self.format_url(token)
                        docid = self.gb_util.calculate_probable_docid(linker_url)
                        sitehash32 = self.gb_util.calculate_sitehash32(linker_url)

                        if response['results'][idx]['docid'] != docid:
                            print('docid', response['results'][idx]['docid'], docid)
                            failed = True

                        if response['results'][idx]['sitehash32'] != sitehash32:
                            print('sitehash32', response['results'][idx]['sitehash32'],sitehash32)
                            failed = True

                        if failed:
                            print(test_type + ' - ' + url + ' - ' + linker_url)
                            print(response)

                        self.add_testcase(test_type, url + ' - ' + linker_url, start_time, failed)
            except Exception as e:
                print(e)
                self.add_testcase(test_type, url, start_time, True)

    def verify_no_linkdb_record(self, *args):
        test_type = 'verify_no_linkdb_record'
        print('Running test -', test_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()

            url = self.format_url(item)

            try:
                response = self.api.lookup_linkdb(url)

                failed = (len(response['records']) != 0)
                if failed:
                    print(test_type + ' - ' + url)
                    print(response)

                self.add_testcase(test_type, url, start_time, failed)
            except Exception as e:
                print(e)
                self.add_testcase(test_type, url, start_time, True)

    def verify_title_record(self, *args):
        test_type = 'verify_title_record'
        print('Running test -', test_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()

            tokens = item.split('|')
            if len(tokens) != 2:
                print('Invalid format ', item)
                self.add_testcase(test_type, item, start_time, True)
                return

            url = self.format_url(tokens.pop(0))

            result = ast.literal_eval(tokens.pop(0))
            if type(result) is not dict:
                print('Invalid format ', item)
                self.add_testcase(test_type, item, start_time, True)
                return

            try:
                response = self.api.lookup_titledb(url)['response']

                failed = ('statusCode' in response)
                if not failed:
                    for key, value in result.items():
                        if response[key] != value:
                            failed = True
                            break

                if failed:
                    print(test_type + ' - ' + url + ' - ' + str(result))
                    print(response)

                self.add_testcase(test_type, url + ' - ' + str(result), start_time, failed)
            except Exception as e:
                print(e)
                self.add_testcase(test_type, url + ' - ' + str(result), start_time, True)

    def verify_no_title_record(self, *args):
        test_type = 'verify_no_title_record'
        print('Running test -', test_type)

        items = []
        if len(args):
            items.append(' '.join(args))
        else:
            filename = os.path.join(self.testcaseconfigdir, test_type)
            items = self.read_file(filename)

        for item in items:
            start_time = time.perf_counter()

            url = self.format_url(item)

            try:
                response = self.api.lookup_titledb(url)['response']

                failed = ('statusCode' not in response)
                if failed:
                    print(test_type + ' - ' + url)
                    print(response)

                self.add_testcase(test_type, url, start_time, failed)
            except Exception as e:
                print(e)
                self.add_testcase(test_type, url, start_time, True)


def main(testdir, testcase, gb_instances, gb_host, webserver, ws_domain, ws_port, ws_sslport):
    test_runner = TestRunner(testdir, testcase, gb_instances, gb_host, webserver, ws_domain, ws_port, ws_sslport)
    result = test_runner.run_test()
    print(TestSuite.to_xml_string([result]))


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('testcase', help='Test case to run')
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

    pargs = parser.parse_args()

    from webserver import TestWebServer

    if not os.path.exists(pargs.ws_sslkey):
        subprocess.call(['./create_ssl_key.sh', pargs.ws_domain], stdout=subprocess.DEVNULL)

    if not os.path.exists(pargs.ws_sslcert):
        subprocess.call(['./create_ssl_cert.sh', pargs.ws_domain], stdout=subprocess.DEVNULL)

    # start webserver
    test_webserver = TestWebServer(pargs.ws_port, pargs.ws_sslport, pargs.ws_sslkey, pargs.ws_sslcert)

    gb_instances = GigablastInstances(pargs.gb_offset, pargs.gb_path, pargs.gb_num_instances, pargs.gb_num_shards, pargs.gb_port)
    main(pargs.testdir, pargs.testcase, gb_instances, pargs.gb_host, test_webserver, pargs.ws_domain, pargs.ws_port, pargs.ws_sslport)

    # stop webserver
    test_webserver.stop()
