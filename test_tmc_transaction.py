
import copy
import unittest

from tmc_transaction import (
    create_signed_transaction,
    generate_keypair,
    transaction_id,
    verify_transaction,
)


class TestTMCTransaction(unittest.TestCase):
    def setUp(self):
        self.private_key, self.public_key = generate_keypair()

        self.transaction = create_signed_transaction(
            private_key=self.private_key,
            recipient="tmc_bob",
            amount_minor=2500,
            nonce=1,
        )

    def test_valid_signature_accepted(self):
        self.assertTrue(verify_transaction(self.transaction))

    def test_modified_amount_rejected(self):
        changed = copy.deepcopy(self.transaction)
        changed["amount_minor"] = 9000

        self.assertFalse(verify_transaction(changed))

    def test_modified_recipient_rejected(self):
        changed = copy.deepcopy(self.transaction)
        changed["recipient"] = "tmc_eve"

        self.assertFalse(verify_transaction(changed))

    def test_modified_nonce_rejected(self):
        changed = copy.deepcopy(self.transaction)
        changed["nonce"] = 2

        self.assertFalse(verify_transaction(changed))

    def test_modified_sender_rejected(self):
        changed = copy.deepcopy(self.transaction)
        changed["sender"] = "tmc_someone_else"

        self.assertFalse(verify_transaction(changed))

    def test_modified_signature_rejected(self):
        changed = copy.deepcopy(self.transaction)
        changed["signature"] = "00" * 64

        self.assertFalse(verify_transaction(changed))

    def test_transaction_id_is_stable(self):
        first_id = transaction_id(self.transaction)
        second_id = transaction_id(self.transaction)

        self.assertEqual(first_id, second_id)
        self.assertEqual(len(first_id), 64)

    def test_invalid_amount_cannot_be_signed(self):
        with self.assertRaises(ValueError):
            create_signed_transaction(
                self.private_key,
                "tmc_bob",
                0,
                1,
            )


if __name__ == "__main__":
    unittest.main()
