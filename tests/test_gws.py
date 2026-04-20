import subprocess
import unittest
from unittest.mock import MagicMock, patch

from drivecat.gws import GwsClient, GwsError, GwsPaginationError, GwsVersionError, _extract_json_object


class GwsHelpersTests(unittest.TestCase):
    def test_extract_json_object_from_pretty_output_with_prefix(self) -> None:
        text = """Using keyring backend: keyring
{
  "error": {
    "code": 401,
    "message": "Authentication failed",
    "reason": "authError"
  }
}"""
        self.assertEqual(_extract_json_object(text), {
            "error": {
                "code": 401,
                "message": "Authentication failed",
                "reason": "authError",
            }
        })


class GwsClientTests(unittest.TestCase):
    @patch("drivecat.gws.which", return_value="/usr/local/bin/gws")
    @patch("drivecat.gws.subprocess.run")
    def test_rejects_unsupported_version(self, run_mock, _which_mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess(
            args=["gws", "--version"],
            returncode=0,
            stdout="gws 0.21.9\n",
            stderr="",
        )

        with self.assertRaises(GwsVersionError) as ctx:
            GwsClient()

        self.assertIn("Require >= 0.22.0", str(ctx.exception))

    @patch("drivecat.gws.which", return_value="/usr/local/bin/gws")
    @patch("drivecat.gws.subprocess.Popen")
    @patch("drivecat.gws.subprocess.run")
    def test_iter_children_raises_if_page_limit_hit_with_next_page_token(self, run_mock, popen_mock, _which_mock) -> None:
        run_mock.return_value = subprocess.CompletedProcess(
            args=["gws", "--version"],
            returncode=0,
            stdout="gws 0.22.5\n",
            stderr="",
        )

        process = MagicMock()
        process.stdout = iter(['{"files":[{"id":"a","name":"A","mimeType":"text/plain"}],"nextPageToken":"more"}\n'])
        process.stderr.read.return_value = ""
        process.wait.return_value = 0
        popen_mock.return_value = process

        client = GwsClient(page_limit=1)
        with self.assertRaises(GwsPaginationError) as ctx:
            list(client.iter_children("folder-1"))

        self.assertEqual(ctx.exception.kind, "pagination_limit")

    @patch("drivecat.gws.which", return_value="/usr/local/bin/gws")
    @patch("drivecat.gws.subprocess.run")
    def test_run_classifies_gws_error_and_extracts_reason(self, run_mock, _which_mock) -> None:
        run_mock.side_effect = [
            subprocess.CompletedProcess(
                args=["gws", "--version"],
                returncode=0,
                stdout="gws 0.22.5\n",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["gws", "drive", "files", "get"],
                returncode=2,
                stdout='{"error":{"code":401,"message":"Authentication failed","reason":"authError"}}\n',
                stderr="error[auth]: Authentication failed\n",
            ),
        ]

        client = GwsClient()
        with self.assertRaises(GwsError) as ctx:
            client.get_file("root")

        self.assertEqual(ctx.exception.kind, "auth_error")
        self.assertEqual(ctx.exception.exit_code, 2)
        self.assertEqual(ctx.exception.reason, "authError")
        self.assertIn("Authentication failed", str(ctx.exception))

    @patch("drivecat.gws.which", return_value="/usr/local/bin/gws")
    @patch("drivecat.gws.time.sleep")
    @patch("drivecat.gws.subprocess.run")
    def test_get_file_retries_transient_error(self, run_mock, _sleep_mock, _which_mock) -> None:
        run_mock.side_effect = [
            subprocess.CompletedProcess(
                args=["gws", "--version"],
                returncode=0,
                stdout="gws 0.22.5\n",
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["gws", "drive", "files", "get"],
                returncode=1,
                stdout='{"error":{"code":503,"message":"Backend error","reason":"backendError"}}\n',
                stderr="",
            ),
            subprocess.CompletedProcess(
                args=["gws", "drive", "files", "get"],
                returncode=0,
                stdout='{"id":"root","name":"Root","mimeType":"application/vnd.google-apps.folder"}',
                stderr="",
            ),
        ]

        client = GwsClient()
        result = client.get_file("root")

        self.assertEqual(result["id"], "root")
        self.assertEqual(run_mock.call_count, 3)

    @patch("drivecat.gws.which", return_value="/usr/local/bin/gws")
    @patch("drivecat.gws.time.sleep")
    @patch("drivecat.gws.subprocess.Popen")
    @patch("drivecat.gws.subprocess.run")
    def test_iter_children_retries_before_yielding_any_results(
        self,
        run_mock,
        popen_mock,
        _sleep_mock,
        _which_mock,
    ) -> None:
        run_mock.return_value = subprocess.CompletedProcess(
            args=["gws", "--version"],
            returncode=0,
            stdout="gws 0.22.5\n",
            stderr="",
        )

        first_process = MagicMock()
        first_process.stdout = iter([])
        first_process.stderr.read.return_value = ""
        first_process.wait.return_value = 1

        second_process = MagicMock()
        second_process.stdout = iter(['{"files":[{"id":"a","name":"A","mimeType":"text/plain"}]}\n'])
        second_process.stderr.read.return_value = ""
        second_process.wait.return_value = 0

        popen_mock.side_effect = [first_process, second_process]

        client = GwsClient()
        with patch.object(
            GwsClient,
            "_to_error",
            side_effect=[
                GwsError("temporary backend issue", kind="api_error", api_code=503),
            ],
        ):
            children = list(client.iter_children("folder-1"))

        self.assertEqual([child["id"] for child in children], ["a"])
        self.assertEqual(popen_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
