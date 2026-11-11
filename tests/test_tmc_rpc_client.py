import unittest
from unittest.mock import patch

from tmc_rpc_client import TMCRPCClient, TMCClientError


class TestTMCRPCClient(unittest.TestCase):

    def setUp(self):
        self.client = TMCRPCClient()

    @patch.object(TMCRPCClient, "_request")
    def test_get_status(self, mock_request):
        mock_request.return_value = {
            "node_info": {},
            "sync_info": {},
        }

        result = self.client.get_status()

        self.assertIn("node_info", result)
        mock_request.assert_called_once_with("status")

    @patch.object(TMCRPCClient, "_request")
    def test_get_account_not_found(self, mock_request):
        mock_request.return_value = {
            "response": {
                "code": 1,
                "log": "Account not found",
            }
        }

        result = self.client.get_account("tmc_test")

        self.assertIsNone(result)

    def test_get_account_rejects_empty_address(self):
        with self.assertRaises(ValueError):
            self.client.get_account("")

    def test_get_transaction_rejects_invalid_hash(self):
        with self.assertRaises(ValueError):
            self.client.get_transaction("invalid-hash")


if __name__ == "__main__":
    unittest.main()
