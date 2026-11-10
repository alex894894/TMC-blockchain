
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tmc_constants import MAX_INTEGER
from tmc_storage import TMCStorage


class TestTMCStorage(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test.db"
        self.storage = TMCStorage(db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_and_read_account(self):
        self.storage.create_account("tmc_alice", 10000)

        account = self.storage.get_account("tmc_alice")

        self.assertEqual(account["address"], "tmc_alice")
        self.assertEqual(account["balance_minor"], 10000)
        self.assertEqual(account["nonce"], 0)

    def test_missing_account(self):
        self.assertIsNone(
            self.storage.get_account("unknown_account")
        )

    def test_negative_balance_rejected(self):
        with self.assertRaises(ValueError):
            self.storage.create_account("tmc_alice", -100)

    def test_duplicate_address_rejected(self):
        self.storage.create_account("tmc_alice", 10000)

        with self.assertRaises(sqlite3.IntegrityError):
            self.storage.create_account("tmc_alice", 20000)

    def set_up_transfer_accounts(self):
        self.storage.create_account("tmc_alice", 10000)
        self.storage.create_account("tmc_bob", 5000)

    def test_successful_transfer(self):
        self.set_up_transfer_accounts()

        result = self.storage.transfer(
            "tmc_alice", "tmc_bob", 2500, 1
        )

        alice = self.storage.get_account("tmc_alice")
        bob = self.storage.get_account("tmc_bob")

        self.assertEqual(alice["balance_minor"], 7500)
        self.assertEqual(alice["nonce"], 1)
        self.assertEqual(bob["balance_minor"], 7500)
        self.assertEqual(result["status"], "success")

    def test_insufficient_balance_rejected(self):
        self.set_up_transfer_accounts()

        with self.assertRaisesRegex(ValueError, "Insufficient balance"):
            self.storage.transfer(
                "tmc_alice", "tmc_bob", 20000, 1
            )

        self.assertEqual(
            self.storage.get_account("tmc_alice")["balance_minor"],
            10000,
        )
        self.assertEqual(
            self.storage.get_account("tmc_alice")["nonce"],
            0,
        )

    def test_invalid_nonce_rejected(self):
        self.set_up_transfer_accounts()

        with self.assertRaisesRegex(ValueError, "Invalid nonce"):
            self.storage.transfer(
                "tmc_alice", "tmc_bob", 1000, 2
            )

        self.assertEqual(
            self.storage.get_account("tmc_alice")["balance_minor"],
            10000,
        )

    def test_replayed_nonce_rejected(self):
        self.set_up_transfer_accounts()

        self.storage.transfer("tmc_alice", "tmc_bob", 1000, 1)

        with self.assertRaisesRegex(ValueError, "Invalid nonce"):
            self.storage.transfer("tmc_alice", "tmc_bob", 1000, 1)

        self.assertEqual(
            self.storage.get_account("tmc_alice")["balance_minor"],
            9000,
        )
        self.assertEqual(
            self.storage.get_account("tmc_bob")["balance_minor"],
            6000,
        )

    def test_same_account_transfer_rejected(self):
        self.set_up_transfer_accounts()

        with self.assertRaisesRegex(ValueError, "same account"):
            self.storage.transfer(
                "tmc_alice", "tmc_alice", 1000, 1
            )

    def test_zero_amount_rejected(self):
        self.set_up_transfer_accounts()

        with self.assertRaises(ValueError):
            self.storage.transfer(
                "tmc_alice", "tmc_bob", 0, 1
            )

    def test_balance_above_max_integer_rejected(self):
        with self.assertRaises(ValueError):
            self.storage.create_account(
                "tmc_alice",
                MAX_INTEGER + 1,
            )
    
    def test_recipient_balance_overflow_rejected(self):
        self.storage.create_account(
            "tmc_alice",
            1000,
        )
        self.storage.create_account(
            "tmc_bob",
            MAX_INTEGER - 100,
        )

        with self.assertRaisesRegex(
            ValueError,
            "Recipient balance would exceed",
        ):
            self.storage.transfer(
                "tmc_alice",
                "tmc_bob",
                200,
                1,
            )

        alice = self.storage.get_account("tmc_alice")
        bob = self.storage.get_account("tmc_bob")

        self.assertEqual(alice["balance_minor"], 1000)
        self.assertEqual(alice["nonce"], 0)
        self.assertEqual(bob["balance_minor"], MAX_INTEGER - 100)
    
    def test_batch_overflow_rolls_back_all_transfers(self):
        self.storage.create_account("tmc_alice", 10000)
        self.storage.create_account("tmc_bob", 5000)
        self.storage.create_account(
            "tmc_charlie",
            MAX_INTEGER - 100,
        )

        transfers = [
            {
                "sender": "tmc_alice",
                "recipient": "tmc_bob",
                "amount_minor": 1000,
                "nonce": 1,
            },
            {
                "sender": "tmc_bob",
                "recipient": "tmc_charlie",
                "amount_minor": 200,
                "nonce": 1,
            },
        ]

        with self.assertRaisesRegex(
            ValueError,
            "Recipient balance would exceed",
        ):
            self.storage.transfer_batch(transfers)

        alice = self.storage.get_account("tmc_alice")
        bob = self.storage.get_account("tmc_bob")
        charlie = self.storage.get_account("tmc_charlie")

        self.assertEqual(alice["balance_minor"], 10000)
        self.assertEqual(alice["nonce"], 0)

        self.assertEqual(bob["balance_minor"], 5000)
        self.assertEqual(bob["nonce"], 0)

        self.assertEqual(charlie["balance_minor"], MAX_INTEGER - 100)

    def test_batch_missing_account_rejected(self):
        self.storage.create_account("tmc_alice", 10000)

        transfers = [
            {
                "sender": "tmc_alice",
                "recipient": "tmc_unknown",
                "amount_minor": 1000,
                "nonce": 1,
            }
        ]

        with self.assertRaisesRegex(
            ValueError,
            "Recipient account does not exist",
        ):
            self.storage.transfer_batch(transfers)

        alice = self.storage.get_account("tmc_alice")

        self.assertEqual(alice["balance_minor"], 10000)
        self.assertEqual(alice["nonce"], 0)
    
    def test_save_state_rejects_balance_above_max_integer(self):
        self.storage.create_account("tmc_old", 500)

        accounts = {
            "tmc_new": {
                "balance_minor": MAX_INTEGER + 1,
                "nonce": 0,
                "public_key": None,
            }
        }

        with self.assertRaises(ValueError):
            self.storage.save_committed_state(
                accounts,
                1,
                "test_hash",
            )

        self.assertIsNotNone(
            self.storage.get_account("tmc_old")
        )

        self.assertIsNone(
            self.storage.get_account("tmc_new")
        )

        self.assertEqual(
            self.storage.get_chain_state()["height"],
            0,
        )
    
    def test_save_state_rejects_nonce_above_max_integer(self):
        accounts = {
            "tmc_alice": {
                "balance_minor": 1000,
                "nonce": MAX_INTEGER + 1,
                "public_key": None,
            }
        }

        with self.assertRaises(ValueError):
            self.storage.save_committed_state(
                accounts,
                1,
                "test_hash",
            )

        self.assertIsNone(
            self.storage.get_account("tmc_alice")
        )
    def test_save_committed_state_successfully(self):
        accounts = {
            "tmc_alice": {
                "balance_minor": 5000,
                "nonce": 2,
                "public_key": None,
            }
        }

        self.storage.save_committed_state(
            accounts,
            5,
            "test_app_hash",
        )

        account = self.storage.get_account("tmc_alice")
        state = self.storage.get_chain_state()

        self.assertEqual(account["balance_minor"], 5000)
        self.assertEqual(account["nonce"], 2)
        self.assertEqual(state["height"], 5)
        self.assertEqual(state["app_hash"], "test_app_hash")
if __name__ == "__main__":
    unittest.main()
