#!/usr/bin/env python3

from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import urllib.parse as urlparse
import urllib.parse as urllib
import mimetypes

import threading
import os
import argparse
import logging
import logging.config
import ssl
import time
import cgi
import socket
import struct

global logger

root_dir = "tests"


def unescape_path(s):
    return urllib.unquote(s)


def init_mimetypes():
    mimetypes.init()
    mimetypes.add_type('text/x-csrc', '.c')
    mimetypes.add_type('text/x-csrc', '.h')
    mimetypes.add_type('text/x-c++src', '.cc')
    mimetypes.add_type('text/x-c++src', '.cpp')
    mimetypes.add_type('text/x-c++src', '.hpp')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        logger.info("%s" % (format % args))

    def file_content(self, path, content_type=None, charset=None):
        """Return content of file. Empty string for non-existing files"""
        if not os.path.isfile(path):
            return bytes()

        if charset is None:
            charset = 'utf-8'

        if content_type is None:
            content_type = 'text/plain'

        content = bytes()
        try:
            with open(path, "rb") as f:
                if self.server == self.server.webserver.http_server_thread.server:
                    scheme = "http"
                else:
                    scheme = "https"

                content = f.read()
                if content_type.startswith('text/'):
                    content = content.decode(charset).format(SCHEME=scheme, DOMAIN=self.domain, PORT=self.server.server_port).encode(charset)

        except IOError:
            pass

        if content != "" and content[:-1] == '\n' and content.count('\n') == 1:
            return content.partition('\n')[0]

        return content

    def do_GET(self):
        parsed_url = urlparse.urlparse(self.path)
        host = self.headers["Host"]
        # strip of port from host (eg. www.example.com:80
        host = host.split(':')[0]

        isHttp = (self.server == self.server.webserver.http_server_thread.server)

        if isHttp:
            url = "http://"
        else:
            url = "https://"

        url += host.encode('ascii').decode('idna')

        if (isHttp and self.server.server_port != 80) or (not isHttp and self.server.server_port != 443):
            url += ':' + str(self.server.server_port)

        url += self.path

        self.server.webserver.add_served_url(url)

        # Host is expected to be in the form of <server>.<testcase>.something.....
        if len(host.split('.')) < 2:
            return self.respond_unknown_host(host)

        host_parts = host.split('.')
        server = host_parts[0]
        testset = host_parts[1]
        self.domain = ".".join(host_parts[2:len(host_parts)])

        path = parsed_url.path

        logger.debug("testset=%s, server=%s, path=%s", testset, server, path)
        return self.serve_page(testset, server, path)

    def respond_unknown_host(self, host):
        self.send_response(500)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(('<html><body>Host %s is unknown</body></html>' % host).encode())

    def respond_unknown_testset(self, testset):
        self.send_response(500)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(('<html><body>testset %s is unknown</body></html>' % testset).encode())

    def respond_unknown_server(self, server):
        self.send_response(500)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(('<html><body>server %s is unknown</body></html>' % server).encode())

    def respond_connection_reset(self):
        self.request.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                                struct.pack('ii', 1, 0))
        self.request.close()
        return False

    def serve_page(self, testset, server, path):
        path = unescape_path(path)

        if not os.path.exists(root_dir + "/" + testset):
            return self.respond_unknown_testset(testset)

        if not os.path.exists(root_dir + "/" + testset + "/" + server):
            return self.respond_unknown_server(server)

        # ok, directory exist so testet and server is known
        base_path = root_dir + "/" + testset + "/" + server + path
        if os.path.isdir(base_path):
            if os.path.exists(base_path + '/index.html'):
                base_path = os.path.join(base_path, 'index.html')
                path = 'index.html'
            else:
                return self.maybe_serve_index_page(base_path, path)
        if not os.path.exists(base_path):
            return self.respond_not_found(base_path)

        if os.path.exists(base_path + ".connection-reset"):
            return self.respond_connection_reset()

        # Setup defaults
        status_code = 200
        content_type = "application/octet-stream"
        content_encoding = None
        charset = None
        extra_headers = []

        mime = mimetypes.guess_type(path, False)
        if mime[0] is not None:
            content_type = mime[0]
        if content_type.startswith('text/'):
            charset = 'UTF-8'

        # then look for overrides
        if os.path.exists(base_path + ".status-code"):
            status_code = int(self.file_content(base_path + ".status-code"))
        if os.path.exists(base_path + ".content-type"):
            content_type = self.file_content(base_path + ".content-type").decode().strip()
        if os.path.exists(base_path + ".charset"):
            charset = self.file_content(base_path + ".charset").decode().strip()
        if os.path.exists(base_path + ".content-encoding"):
            content_encoding = self.file_content(base_path + ".content-encoding").decode().strip()
        if os.path.exists(base_path + ".extra-headers"):
            extra_headers = self.file_content(base_path + ".extra-headers").decode().split('\n')

        if content_type == "":
            content_type = None
        if charset == "":
            charset = None
        if content_encoding == "":
            content_encoding = None

        if os.path.exists(base_path + ".connection-delay"):
            time.sleep(int(self.file_content(base_path + ".connection-delay")))

        # ok, got it all
        self.send_response(status_code)

        if content_type is not None:
            if charset is None:
                self.send_header("Content-type", content_type)
            else:
                self.send_header("Content-type", content_type + "; charset=" + charset)

        if content_encoding:
            self.send_header("Content-Encoding", content_encoding)

        for h in extra_headers:
            if ':' in h:
                self.send_header(h.split(":")[0], h.partition(":")[2])

        self.end_headers()

        self.wfile.write(self.file_content(base_path, content_type, charset))

    def maybe_serve_index_page(self, dir, path):
        if os.path.exists(dir + "/_noindex"):
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()

        self.wfile.write('<html>'.encode())
        self.wfile.write('<head>'.encode())
        self.wfile.write('<meta charset="UTF-8"/>'.encode())
        self.wfile.write(('	<title>Contents of %s</title>' % dir).encode())
        self.wfile.write('</head>'.encode())
        self.wfile.write('<body>'.encode())

        l = os.listdir(dir)
        l.sort()

        special_ending = ('.status-code', '.content-type', '.charset', '.content-encoding', '.extra-headers', '.connection-reset', '.connection-delay')
        special_file = ('README', 'robots.txt')
        filedir = "" if (path == "/") else path
        for f in l:
            if not f.endswith(special_ending) and f not in special_file:
                self.wfile.write(('<p><a href="%s/%s">%s</a></p>' % (filedir, cgi.escape(f), cgi.escape(f))).encode())

        self.wfile.write('</body>'.encode())
        self.wfile.write('</html>'.encode())

    def respond_not_found(self, path):
        self.send_response(404)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(('<html><body>404 - %s was not found</body></html>' % path).encode())


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle requests in a separate thread."""
    pass


class ServerThread(threading.Thread):
    def __init__(self, server, webserver):
        threading.Thread.__init__(self, name="ServerThread")
        self.server = server
        self.server.webserver = webserver

    def run(self):
        self.server.serve_forever()


class TestWebServer:
    def __init__(self, port=8080, sslport=4443, keyfile=None, certfile=None, loggingconf='logging.conf'):
        logging.config.fileConfig(loggingconf)

        global logger
        logger = logging.getLogger(__name__)
        logger.info("webserver initializing")

        init_mimetypes()

        self.http_server_thread = None
        self.https_server_thread = None
        self.served_urls = []

        if keyfile is not None and certfile is not None:
            def servername_callback(ssl_sock, server_name, initial_context):
                if server_name is None:
                    return ssl.ALERT_DESCRIPTION_HANDSHAKE_FAILURE

            httpsd = ThreadedHTTPServer(("", sslport), Handler)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLSv1)
            ctx.load_cert_chain(certfile, keyfile)
            ctx.set_servername_callback(servername_callback)

            httpsd.socket = ctx.wrap_socket(httpsd.socket, server_side=True)
            self.https_server_thread = ServerThread(httpsd, self)
            self.https_server_thread.daemon = True
            self.https_server_thread.start()

        httpd = ThreadedHTTPServer(("", port), Handler)
        self.http_server_thread = ServerThread(httpd, self)
        self.http_server_thread.daemon = True
        self.http_server_thread.start()

        logger.info("webserver initialized")

    def stop(self):
        logger.info("webserver stopping")

        if self.http_server_thread:
            self.http_server_thread.server.shutdown()

        if self.https_server_thread:
            self.https_server_thread.server.shutdown()

        logger.info("webserver stopped")

    def add_served_url(self, url):
        self.served_urls.append(url)

    def get_served_urls(self):
        return self.served_urls

    def clear_served_urls(self):
        self.served_urls = []


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--port", type=int, help="HTTP server port number", default=8080)
    parser.add_argument("--sslport", type=int, help="HTTPS server port number", default=4443)
    parser.add_argument("--keyfile", type=str, help="SSL key file (.key)")
    parser.add_argument("--certfile", type=str, help="SSL certificate file (.cert)")
    parser.add_argument("--loggingconf", type=str, default="logging.conf")
    args = parser.parse_args()

    test_webserver = TestWebServer(args.port, args.sslport, args.keyfile, args.certfile, args.loggingconf)

    time.sleep(10 * 356 * 84100)

# openssl genrsa -out localhost.key 2048
# openssl req -new -x509 -key localhost.key -out localhost.cert -days 3650 -subj "/CN=localhost"
