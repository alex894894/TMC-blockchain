
import copy
import unittest

from tmc_transaction import (
    MAX_INTEGER,
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

    def test_max_integer_amount_is_accepted(self):
        transaction = create_signed_transaction(
            self.private_key,
            "tmc_bob",
            MAX_INTEGER,
            1,
        )

        self.assertTrue(verify_transaction(transaction))

    def test_amount_above_max_integer_cannot_be_signed(self):
        with self.assertRaises(ValueError):
            create_signed_transaction(
                self.private_key,
                "tmc_bob",
                MAX_INTEGER + 1,
                1,
            )

    def test_nonce_above_max_integer_cannot_be_signed(self):
        with self.assertRaises(ValueError):
            create_signed_transaction(
                self.private_key,
                "tmc_bob",
                100,
                MAX_INTEGER + 1,
            )
            
    def test_public_key_with_spaces_is_rejected(self):
        transaction = create_signed_transaction(
            self.private_key,
            "tmc_test_recipient",
            100,
            1,
        )

        transaction["public_key"] = (
            transaction["public_key"][:2]
            + " "
            + transaction["public_key"][2:]
        )

        self.assertFalse(verify_transaction(transaction))


    def test_signature_with_spaces_is_rejected(self):
        transaction = create_signed_transaction(
            self.private_key,
            "tmc_test_recipient",
            100,
            1,
        )

        transaction["signature"] = (
            transaction["signature"][:2]
            + " "
            + transaction["signature"][2:]
        )

        self.assertFalse(verify_transaction(transaction))

if __name__ == "__main__":
    unittest.main()
