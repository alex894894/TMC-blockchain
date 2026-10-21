
import tempfile
import unittest
from pathlib import Path

from abci.types import RequestFinalizeBlock, RequestCommit

from tmc_app import TMCApp
from tmc_storage import TMCStorage
from tmc_transaction import (
    generate_keypair,
    create_signed_transaction,
    encode_transaction,
)
from abci.proto.tendermint.abci.types import CommitInfo
from abci.proto.google.protobuf.timestamp import Timestamp

class TestTMCApp(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_tmc.db"

        self.storage = TMCStorage(self.db_path)

        self.sender_private_key, sender_public_key = generate_keypair()
        _, recipient_public_key = generate_keypair()

        self.sender = self.storage.register_account(
            sender_public_key,
            initial_balance_minor=1000,
        )
        self.recipient = self.storage.register_account(
            recipient_public_key,
            initial_balance_minor=0,
        )

        self.app = TMCApp(storage=self.storage)

    def make_finalize_request(self, height, txs):
        return RequestFinalizeBlock(
            decided_last_commit=CommitInfo(),
            hash=b"",
            height=height,
            time=Timestamp(seconds=0, nanos=0),
            next_validators_hash=b"",
            proposer_address=b"",
            txs=txs,
        )

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    async def test_finalize_block_does_not_save_before_commit(self):
        # Tranzaksiýany taýýarlamak
        tx = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=100,
            nonce=1,
        )

        request = self.make_finalize_request(
            height=1,
            txs=[encode_transaction(tx)],
        )

        # Blokdaky tranzaksiýalary wagtlaýyn ýerine ýetirmek
        response = await self.app.finalize_block(request)

        self.assertEqual(len(response.tx_results), 1)
        self.assertEqual(response.tx_results[0].code, 0)

        # Commit bolmanka maglumatlar bazasy üýtgemeli däl
        sender = self.storage.get_account(self.sender)
        recipient = self.storage.get_account(self.recipient)

        self.assertEqual(sender["balance_minor"], 1000)
        self.assertEqual(recipient["balance_minor"], 0)

    async def test_commit_saves_balances_and_block_height(self):
        # Tranzaksiýany taýýarlamak
        tx = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=100,
            nonce=1,
        )

        request = self.make_finalize_request(
            height=1,
            txs=[encode_transaction(tx)],
        )
        await self.app.finalize_block(request)
        await self.app.commit(RequestCommit())

        # Tassyklanan hasap ýagdaýyny barlamak
        sender = self.storage.get_account(self.sender)
        recipient = self.storage.get_account(self.recipient)
        chain_state = self.storage.get_chain_state()

        self.assertEqual(sender["balance_minor"], 900)
        self.assertEqual(sender["nonce"], 1)
        self.assertEqual(recipient["balance_minor"], 100)
        self.assertEqual(chain_state["height"], 1)
        self.assertTrue(chain_state["app_hash"])

    async def test_restart_restores_committed_state(self):
        # Tranzaksiýany taýýarlamak
        tx = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=100,
            nonce=1,
        )

        await self.app.finalize_block(
            self.make_finalize_request(
                height=1,
                txs=[encode_transaction(tx)],
            )
        )
        await self.app.commit(RequestCommit())

        # Programmanyň täze nusgasyny şol bir maglumatlar bazasy bilen döretmek
        restarted_storage = TMCStorage(self.db_path)
        restarted_app = TMCApp(storage=restarted_storage)

        self.assertEqual(restarted_app.height, 1)
        self.assertEqual(
            restarted_app.app_hash.hex(),
            self.app.app_hash.hex(),
        )
        self.assertEqual(
            restarted_storage.get_account(self.sender)["balance_minor"],
            900,
        )

    async def test_invalid_transaction_does_not_change_balances(self):
        # Hasapdaky serişdelerden köp pul geçirmek synanyşygy
        tx = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=2000,
            nonce=1,
        )

        response = await self.app.finalize_block(
            self.make_finalize_request(
                height=1,
                txs=[encode_transaction(tx)],
            )
        )

        self.assertEqual(response.tx_results[0].code, 1)

        # Nädogry tranzaksiýa hasaplaryň ýagdaýyny üýtgetmeli däl
        sender = self.storage.get_account(self.sender)
        recipient = self.storage.get_account(self.recipient)

        self.assertEqual(sender["balance_minor"], 1000)
        self.assertEqual(sender["nonce"], 0)
        self.assertEqual(recipient["balance_minor"], 0)


if __name__ == "__main__":
    unittest.main()
