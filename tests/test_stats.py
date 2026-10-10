import io
import json
import unittest
from http.client import HTTPResponse
from unittest.mock import Mock, patch

from api import stats


class StatsTests(unittest.TestCase):
    def request(self, method, headers=None):
        headers = {"Host": "stats.example", "Origin": "https://game.example",
                   **(headers or {})}
        request = f"{method} /api/stats HTTP/1.1\r\n"
        request += "".join(f"{key}: {value}\r\n" for key, value in headers.items())
        connection = Mock()
        connection.makefile.return_value = io.BytesIO((request + "\r\n").encode())
        with patch.object(stats.handler, "log_message"):
            stats.handler(connection, ("127.0.0.1", 12345), Mock())
        raw = b"".join(call.args[0] for call in connection.sendall.call_args_list)
        response_socket = Mock()
        response_socket.makefile.return_value = io.BytesIO(raw)
        response = HTTPResponse(response_socket)
        response.begin()
        return response

    def test_cross_origin_get_serves_snapshot(self):
        with patch.object(stats.Path, "read_text", return_value='{"total_games": 42}'):
            response = self.request("GET")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Access-Control-Allow-Origin"), "*")
        self.assertEqual(response.getheader("Content-Type"), "application/json")
        self.assertEqual(response.getheader("Cache-Control"), "public, s-maxage=60")
        self.assertEqual(json.load(response), {"total_games": 42, "data_source": "saved_report"})

    def test_cross_origin_get_exposes_snapshot_errors(self):
        for error in (OSError("missing snapshot"), ValueError("invalid snapshot")):
            with self.subTest(error=error), patch.object(stats, "load_snapshot", side_effect=error):
                response = self.request("GET")
                self.assertEqual(response.status, 503)
                self.assertEqual(response.getheader("Access-Control-Allow-Origin"), "*")
                self.assertEqual(json.load(response), {"error": "Statistics snapshot unavailable"})

    def test_preflight_preserves_previous_contract_without_loading_snapshot(self):
        with patch.object(stats, "load_snapshot", side_effect=OSError("missing snapshot")) as load:
            response = self.request("OPTIONS", {
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type",
            })
        self.assertEqual(response.status, 200)
        self.assertEqual(response.getheader("Access-Control-Allow-Origin"), "*")
        self.assertEqual(response.getheader("Access-Control-Allow-Methods"), "GET, OPTIONS")
        self.assertEqual(response.getheader("Access-Control-Allow-Headers"), "Content-Type")
        self.assertEqual(response.read(), b"")
        load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
