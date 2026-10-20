import tempfile
import unittest
from pathlib import Path

from tmc_storage import TMCStorage
from tmc_transaction import (
    generate_keypair,
    create_signed_transaction,
    apply_signed_transfer,
)


class TestTMCIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test_tmc.db"
        self.storage = TMCStorage(db_path)

        # Generate Alice's key pair.
        self.alice_private_key, alice_public_key = (
            generate_keypair()
        )

        # Generate Bob's key pair.
        self.bob_private_key, bob_public_key = (
            generate_keypair()
        )

        # Register both accounts with initial test balances.
        self.alice_address = self.storage.register_account(
            alice_public_key,
            initial_balance_minor=10000,
        )

        self.bob_address = self.storage.register_account(
            bob_public_key,
            initial_balance_minor=5000,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_signed_transfer_succeeds(self):
        transaction = create_signed_transaction(
            private_key=self.alice_private_key,
            recipient=self.bob_address,
            amount_minor=2500,
            nonce=1,
        )

        result = apply_signed_transfer(
            self.storage,
            transaction,
        )

        alice = self.storage.get_account(self.alice_address)
        bob = self.storage.get_account(self.bob_address)

        self.assertEqual(result["status"], "success")
        self.assertEqual(alice["balance_minor"], 7500)
        self.assertEqual(bob["balance_minor"], 7500)
        self.assertEqual(alice["nonce"], 1)

    def test_modified_transaction_is_rejected(self):
        transaction = create_signed_transaction(
            private_key=self.alice_private_key,
            recipient=self.bob_address,
            amount_minor=2500,
            nonce=1,
        )

        # Change the amount after signing.
        transaction["amount_minor"] = 9000

        with self.assertRaisesRegex(
            ValueError,
            "Invalid transaction signature",
        ):
            apply_signed_transfer(
                self.storage,
                transaction,
            )

        alice = self.storage.get_account(self.alice_address)
        bob = self.storage.get_account(self.bob_address)

        # Rejected transactions must not change balances.
        self.assertEqual(alice["balance_minor"], 10000)
        self.assertEqual(bob["balance_minor"], 5000)
        self.assertEqual(alice["nonce"], 0)

    def test_unregistered_sender_is_rejected(self):
        unknown_private_key, _ = generate_keypair()

        transaction = create_signed_transaction(
            private_key=unknown_private_key,
            recipient=self.bob_address,
            amount_minor=1000,
            nonce=1,
        )

        with self.assertRaisesRegex(
            ValueError,
            "Sender account does not exist",
        ):
            apply_signed_transfer(
                self.storage,
                transaction,
            )

        bob = self.storage.get_account(self.bob_address)
        self.assertEqual(bob["balance_minor"], 5000)


if __name__ == "__main__":
    unittest.main()
