import unittest
from unittest.mock import patch, Mock
import skill_under_test as s


class TestNewSkill(unittest.TestCase):
    def setUp(self):
        # Use a deterministic list of nodes
        self.nodes = [("1.2.3.4", 8000), ("5.6.7.8", 9000)]
        self.skill = s.P2PNetworkSkill(nodes=self.nodes)

    @patch("skill_under_test.socket.gethostbyname", return_value="10.0.0.1")
    @patch("skill_under_test.socket.gethostname", return_value="testhost")
    @patch("skill_under_test.requests.get")
    def test_scan_and_report(self, mock_get, mock_hostname, mock_gethostbyname):
        # Mock response for the first node (online)
        resp_online = Mock()
        resp_online.status_code = 200
        resp_online.text = '<html><body><div id="status">READY</div></body></html>'
        resp_online.raise_for_status = Mock()
        # Mock exception for the second node (offline)
        mock_get.side_effect = [resp_online, s.requests.RequestException("timeout")]

        # Perform scan
        self.skill.scan()

        # Verify results dictionary
        expected_online = {
            "online": True,
            "status": "READY",
            "code": 200,
        }
        self.assertIn(("1.2.3.4", 8000), self.skill.results)
        self.assertEqual(self.skill.results[("1.2.3.4", 8000)], expected_online)

        result_offline = self.skill.results[("5.6.7.8", 9000)]
        self.assertFalse(result_offline["online"])
        self.assertIsNone(result_offline["code"])
        self.assertIn("timeout", result_offline["error"])

        # Verify report content
        report = self.skill.report()
        self.assertIn("Локальный IP: 10.0.0.1", report)
        self.assertIn("1.2.3.4:8000 → ONLINE (status: READY)", report)
        self.assertIn("5.6.7.8:9000 → OFFLINE (timeout)", report)


if __name__ == "__main__":
    unittest.main()