import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from agentloop.runtime import Runtime
from agentloop.server import handler_for
from agentloop.store import Store


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(Runtime(Store(str(Path(cls.temp.name) / "api.db")))))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def request(self, path, body=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        method = "GET" if body is None else "POST"
        connection.request(method, path, json.dumps(body) if body is not None else None,
                           headers={"Content-Type": "application/json", **(headers or {})})
        response = connection.getresponse()
        data = response.read()
        status, content_type = response.status, response.getheader("Content-Type")
        connection.close()
        return status, json.loads(data) if content_type == "application/json" else data

    def test_api_full_investigation(self):
        status, snapshot = self.request("/api/runs", {"goal": "Investigate"})
        self.assertEqual(201, status)
        path = "/api/runs/" + snapshot["run"]["id"]
        status, snapshot = self.request(path + "/advance", {})
        self.assertEqual("awaiting_approval", snapshot["run"]["status"])
        self.request(path + "/approval", {"approved": True})
        status, snapshot = self.request(path + "/advance", {})
        self.assertEqual("completed", snapshot["run"]["status"])
        self.assertEqual(200, status)

    def test_static_assets(self):
        for path in ["/", "/style.css", "/app.js"]:
            with self.subTest(path=path):
                status, data = self.request(path)
                self.assertEqual(200, status)
                self.assertGreater(len(data), 100)

    def test_invalid_requests(self):
        self.assertEqual(400, self.request("/api/runs", {"goal": "x", "extra": True})[0])
        self.assertEqual(400, self.request("/api/runs", ["invalid"])[0])
        self.assertEqual(404, self.request("/api/runs/missing")[0])
        self.assertEqual(404, self.request("/../../etc/passwd")[0])

    def test_cross_origin_write_is_blocked(self):
        self.assertEqual(403, self.request("/api/runs", {"goal": "x"}, {"Origin": "https://example.com"})[0])
        self.assertEqual(403, self.request("/api/runs", {"goal": "x"}, {"Sec-Fetch-Site": "cross-site"})[0])

    def test_rebinding_host_is_blocked(self):
        self.assertEqual(403, self.request("/api/config", headers={"Host": "attacker.example"})[0])

    def test_non_json_content_type_is_rejected(self):
        self.assertEqual(415, self.request("/api/runs", {"goal": "x"}, {"Content-Type": "text/plain"})[0])


if __name__ == "__main__":
    unittest.main()
