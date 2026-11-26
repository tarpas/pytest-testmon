"""gzip bodies between RemoteDB and testmon.net; see timeout_transport in testmon_core."""

import gzip
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from xmlrpc.client import ServerProxy, dumps, loads

import pytest

from testmon import testmon_core

FILES = {f"package/module_{i}.py": "a" * 40 for i in range(100)}


@pytest.fixture
def server():
    """A stand-in for testmon.net; `server.requests` lists (Content-Encoding, params, method)."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self):  # pylint: disable=invalid-name
            body = self.rfile.read(int(self.headers["Content-Length"]))
            encoding = self.headers["Content-Encoding"]
            if encoding == "gzip":
                body = gzip.decompress(body)
            httpd.requests.append((encoding, *loads(body)))
            response = gzip.compress(
                dumps((httpd.result,), methodresponse=True).encode()
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/xml")
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Content-Length", str(len(httpd.broken or response)))
            self.end_headers()
            self.wfile.write(httpd.broken or response)

        def log_message(self, format, *args):  # pylint: disable=redefined-builtin
            pass

    with HTTPServer(("127.0.0.1", 0), Handler) as httpd:
        httpd.requests = []
        httpd.result = {"exec_id": 1, "gzip_requests": True}
        httpd.broken = None
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{httpd.server_port}/"
        transport = testmon_core.timeout_transport(url, headers=[("x-api-key", "k")])
        httpd.remote = testmon_core.RemoteDB(
            ServerProxy(url, allow_none=True, transport=transport)
        )
        yield httpd
        httpd.remote.close()
        httpd.shutdown()
        thread.join()


def test_large_requests_are_compressed_once_the_server_announces_it(server):
    remote = server.remote

    result = remote.fetch_unknown_files(FILES, 1)  # also: a gzip response is read
    remote.use(result)
    remote.fetch_unknown_files(FILES, 1)
    remote.filenames(1)

    assert result == server.result
    assert server.requests == [
        (None, (FILES, 1), "fetch_unknown_files"),
        ("gzip", (FILES, 1), "fetch_unknown_files"),
        (None, (1,), "filenames"),
    ]


def test_requests_stay_plain_for_a_server_that_does_not_announce_it(server):
    server.remote.use({"exec_id": 1})
    server.remote.fetch_unknown_files(FILES, 1)

    assert [encoding for encoding, _, _ in server.requests] == [None]


@pytest.mark.parametrize("cut", [10, -8], ids=["header", "body"])
def test_broken_gzip_response_is_a_remote_error(server, cut):
    server.broken = gzip.compress(b"<methodResponse>" * 100)[:cut]

    with pytest.raises(testmon_core.REMOTE_ERRORS):
        server.remote.filenames(1)
