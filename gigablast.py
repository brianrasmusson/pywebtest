import requests


class GigablastAPI:
    class _HTTPStatus:
        @staticmethod
        def compare(status, expected_status):
            return status[status.find('(')+1:status.find(')')] == expected_status

        @staticmethod
        def doc_force_delete():
            return 'Doc force deleted'

        @staticmethod
        def record_not_found():
            return 'Record not found'

    def __init__(self, host, port):
        self._host = host
        self._port = port
        self._add_urls = set()

    def finalize(self):
        # cleanup urls
        for url in self._add_urls:
            self.delete_url(url, True)

    def _get_url(self, path):
        return 'http://' + self._host + ':' + self._port + '/' + path

    @staticmethod
    def _apply_default_payload(payload):
        payload.setdefault('c', 'main')
        payload.setdefault('format', 'json')
        payload.setdefault('showinput', '0')

    def _check_http_status(self, e, expected_status):
        # hacks to cater for inject returning invalid status line
        if (len(e.args) == 1 and
                type(e.args[0]) == requests.packages.urllib3.exceptions.ProtocolError and
                len(e.args[0].args) == 2):
            import http.client
            if type(e.args[0].args[1]) == http.client.BadStatusLine:
                if self._HTTPStatus.compare(str(e.args[0].args[1]), expected_status):
                    return True
        return False

    def _add_url(self, url, payload=None):
        if not payload:
            payload = {}

        self._apply_default_payload(payload)

        payload.update({'urls': url})

        response = requests.get(self._get_url('admin/addurl'), params=payload)

        return response.json()

    def _config_master(self, payload):
        self._apply_default_payload(payload)

        requests.get(self._get_url('admin/master'), params=payload)

    def _config_search(self, payload):
        self._apply_default_payload(payload)

        requests.get(self._get_url('admin/search'), params=payload)

    def _config_settings(self, payload):
        self._apply_default_payload(payload)

        requests.get(self._get_url('admin/settings'), params=payload)

    def _config_spider(self, payload):
        self._apply_default_payload(payload)

        requests.get(self._get_url('admin/spider'), params=payload)

    def _inject(self, url, payload=None):
        if not payload:
            payload = {}

        self._apply_default_payload(payload)

        payload.update({'url': url})

        response = requests.get(self._get_url('admin/inject'), params=payload)

        # inject doesn't seem to wait until document is completely indexed
        from time import sleep
        sleep(0.1)

        return response.json()

    def add_url(self, url):
        self._add_urls.add(url)

        return self._add_url(url)['response']['statusCode'] == 0

    def config_sitelist(self, sitelist):
        payload = {'sitelist': sitelist}

        self._config_settings(payload)

    def config_crawldelay(self, norobotscrawldelay, robotsnocrawldelay):
        payload = {'crwldlnorobot': norobotscrawldelay, 'crwldlrobotnodelay': robotsnocrawldelay}

        self._config_spider(payload)

    def config_dns(self, primary, secondary=''):
        payload = {'pdns': primary, 'sdns': secondary}

        self._config_master(payload)

    def config_log(self, payload):
        self._apply_default_payload(payload)

        requests.get(self._get_url('admin/log'), params=payload)

    def delete_url(self, url, finalizer=False):
        if not finalizer:
            self._add_urls.discard(url)

        payload = {'deleteurl': '1'}

        try:
            self._inject(url, payload)
        except requests.exceptions.ConnectionError as e:
            # delete url returns invalid HTTP status line
            return self._check_http_status(e, self._HTTPStatus.doc_force_delete())

        return False

    def dump(self):
        payload = {'dump': '1'}

        self._config_master(payload)

    def get(self, doc_id, payload=None):
        if not payload:
            payload = {}

        self._apply_default_payload(payload)

        payload.update({'d': doc_id})

        try:
            response = requests.get(self._get_url('get'), params=payload)
            return response.json()
        except requests.exceptions.ConnectionError as e:
            if self._check_http_status(e, self._HTTPStatus.record_not_found()):
                import json
                return json.loads('{"response":{"statusCode":32771,"statusMsg":"Record not found"}}')

    def get_spiderqueue(self):
        payload = {}
        self._apply_default_payload(payload)

        response = requests.get(self._get_url('admin/spiderdb'), params=payload)
        return response.json()

    def inject_url(self, url):
        self._add_urls.add(url)

        return self._inject(url)['response']['statusCode'] == 0

    def save(self):
        payload = {'js': '1'}
        self._config_master(payload)

    def search(self, query, payload=None):
        if not payload:
            payload = {}

        self._apply_default_payload(payload)

        payload.update({'q': query})

        response = requests.get(self._get_url('search'), params=payload)

        return response.json()

    def status(self, payload=None):
        if not payload:
            payload = {}

        self._apply_default_payload(payload)

        response = requests.get(self._get_url('admin/status'), params=payload)

        return response.json()

    def status_processstarttime(self):
        return self.status()['response']['processStartTime']
