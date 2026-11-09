
import tempfile
import unittest
from pathlib import Path

from abci.types import (
    RequestFinalizeBlock,
    RequestProcessProposal,
    RequestCommit,
    ProposalStatus,
    RequestInitChain,
    RequestPrepareProposal,
)
from abci.proto.tendermint.abci.types import CommitInfo
from abci.proto.google.protobuf.timestamp import Timestamp

from tmc_app import TMCApp
from tmc_storage import TMCStorage
from tmc_transaction import (
    generate_keypair,
    create_signed_transaction,
    encode_transaction,
)
from abci.types import RequestCheckTx

from tmc_constants import MAX_INTEGER

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

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

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

    def make_process_proposal_request(self, height, txs):
        return RequestProcessProposal(
            proposed_last_commit=CommitInfo(),
            hash=b"",
            height=height,
            time=Timestamp(seconds=0, nanos=0),
            next_validators_hash=b"",
            proposer_address=b"",
            txs=txs,
        )

    async def test_finalize_block_does_not_save_before_commit(self):
        tx = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=100,
            nonce=1,
        )

        response = await self.app.finalize_block(
            self.make_finalize_request(
                height=1,
                txs=[encode_transaction(tx)],
            )
        )

        self.assertEqual(len(response.tx_results), 1)
        self.assertEqual(response.tx_results[0].code, 0)

        sender = self.storage.get_account(self.sender)
        recipient = self.storage.get_account(self.recipient)

        self.assertEqual(sender["balance_minor"], 1000)
        self.assertEqual(recipient["balance_minor"], 0)

    async def test_commit_saves_balances_and_block_height(self):
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

        sender = self.storage.get_account(self.sender)
        recipient = self.storage.get_account(self.recipient)
        chain_state = self.storage.get_chain_state()

        self.assertEqual(sender["balance_minor"], 900)
        self.assertEqual(sender["nonce"], 1)
        self.assertEqual(recipient["balance_minor"], 100)
        self.assertEqual(chain_state["height"], 1)
        self.assertTrue(chain_state["app_hash"])

    async def test_restart_restores_committed_state(self):
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
        
        restored_sender = restarted_storage.get_account(self.sender)
        restored_recipient = restarted_storage.get_account(self.recipient)

        self.assertEqual(restored_sender["balance_minor"], 900)
        self.assertEqual(restored_sender["nonce"], 1)
        self.assertEqual(restored_recipient["balance_minor"], 100)

    async def test_invalid_transaction_does_not_change_balances(self):
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

        sender = self.storage.get_account(self.sender)
        recipient = self.storage.get_account(self.recipient)

        self.assertEqual(sender["balance_minor"], 1000)
        self.assertEqual(sender["nonce"], 0)
        self.assertEqual(recipient["balance_minor"], 0)

    async def test_process_proposal_accepts_valid_transaction(self):
        tx = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=100,
            nonce=1,
        )

        response = await self.app.process_proposal(
            self.make_process_proposal_request(
                height=1,
                txs=[encode_transaction(tx)],
            )
        )

        self.assertEqual(response.status, ProposalStatus.ACCEPT)

        sender = self.storage.get_account(self.sender)
        recipient = self.storage.get_account(self.recipient)

        self.assertEqual(sender["balance_minor"], 1000)
        self.assertEqual(recipient["balance_minor"], 0)

    async def test_process_proposal_rejects_invalid_transaction(self):
        tx = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=2000,
            nonce=1,
        )

        response = await self.app.process_proposal(
            self.make_process_proposal_request(
                height=1,
                txs=[encode_transaction(tx)],
            )
        )

        self.assertEqual(response.status, ProposalStatus.REJECT)

        sender = self.storage.get_account(self.sender)
        recipient = self.storage.get_account(self.recipient)

        self.assertEqual(sender["balance_minor"], 1000)
        self.assertEqual(recipient["balance_minor"], 0)

    
    async def test_finalize_block_rolls_back_all_transactions_on_error(self):
        # Birinji dogry, ikinji ýalňyş tranzaksiýany döretmek
        tx1 = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=100,
            nonce=1,
        )

        tx2 = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=2000,
            nonce=2,
        )

        response = await self.app.finalize_block(
            self.make_finalize_request(
                height=1,
                txs=[
                    encode_transaction(tx1),
                    encode_transaction(tx2),
                ],
            )
        )

        # Ähli tranzaksiýalaryň ýatyrylandygyny barlamak
        self.assertEqual(len(response.tx_results), 2)
        self.assertTrue(
            all(result.code != 0 for result in response.tx_results)
        )

        sender = self.storage.get_account(self.sender)
        recipient = self.storage.get_account(self.recipient)

        self.assertEqual(sender["balance_minor"], 1000)
        self.assertEqual(sender["nonce"], 0)
        self.assertEqual(recipient["balance_minor"], 0)

    async def test_check_tx_does_not_reserve_pending_nonce(self):
        # Bir iberiji üçin birmeňzeş nonce bilen iki tranzaksiýa döretmek
        tx1 = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=100,
            nonce=1,
        )

        tx2 = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=200,
            nonce=1,
        )

        response1 = await self.app.check_tx(
            RequestCheckTx(tx=encode_transaction(tx1))
        )

        response2 = await self.app.check_tx(
            RequestCheckTx(tx=encode_transaction(tx2))
        )

        # Häzirki ýagdaýda iki tranzaksiýanyň hem kabul edilýändigini barlamak
        self.assertEqual(response1.code, 0)
        self.assertEqual(response2.code, 0)
    
    async def test_process_proposal_rejects_duplicate_nonce(self):
        # Bir iberijiden birmeňzeş nonce bilen iki tranzaksiýa döretmek
        tx1 = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=100,
            nonce=1,
        )

        tx2 = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=200,
            nonce=1,
        )

        response = await self.app.process_proposal(
            self.make_process_proposal_request(
                height=1,
                txs=[
                    encode_transaction(tx1),
                    encode_transaction(tx2),
                ],
            )
        )

        # Gaýtalanýan nonce sebäpli teklibiň ret edilendigini barlamak
        self.assertEqual(response.status, ProposalStatus.REJECT)

        # Teklip barlananda hasaplaryň üýtgemändigini barlamak
        sender = self.storage.get_account(self.sender)
        recipient = self.storage.get_account(self.recipient)

        self.assertEqual(sender["balance_minor"], 1000)
        self.assertEqual(sender["nonce"], 0)
        self.assertEqual(recipient["balance_minor"], 0)
    
    async def test_prepare_proposal_preserves_transaction_order(self):
        # Iki sany dogry tranzaksiýa döretmek
        tx1 = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=100,
            nonce=1,
        )

        tx2 = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=200,
            nonce=2,
        )

        raw_tx1 = encode_transaction(tx1)
        raw_tx2 = encode_transaction(tx2)

        
        response = await self.app.prepare_proposal(
            RequestPrepareProposal(
                max_tx_bytes=1000000,
                txs=[raw_tx1, raw_tx2],
                local_last_commit=CommitInfo(),
                height=1,
                time=Timestamp(seconds=0, nanos=0),
                next_validators_hash=b"",
                proposer_address=b"",
            )
        )


        # Tranzaksiýalaryň sanyny we tertibini barlamak
        self.assertEqual(response.txs, [raw_tx1, raw_tx2])

    
    async def test_prepare_proposal_respects_max_tx_bytes(self):
        # Uly bolmadyk tranzaksiýa teklibini taýýarlamak
        tx1 = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=100,
            nonce=1,
        )

        tx2 = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=200,
            nonce=2,
        )

        raw_tx1 = encode_transaction(tx1)
        raw_tx2 = encode_transaction(tx2)

        # Diňe birinji tranzaksiýanyň ölçegine ýeterlik çäk bellemek
        response = await self.app.prepare_proposal(
            RequestPrepareProposal(
                max_tx_bytes=len(raw_tx1),
                txs=[raw_tx1, raw_tx2],
                local_last_commit=CommitInfo(),
                height=1,
                time=Timestamp(seconds=0, nanos=0),
                next_validators_hash=b"",
                proposer_address=b"",
            )
        )

        # Teklipde diňe birinji tranzaksiýanyň galmalydygyny barlamak
        self.assertEqual(response.txs, [raw_tx1])
    async def test_prepare_proposal_skips_invalid_transaction(self):
        # Nädogry tranzaksiýany geçirip, dogrusyny saýlamak
        invalid_tx = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=999999999,
            nonce=1,
        )
        valid_tx = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=100,
            nonce=1,
        )

        raw_invalid_tx = encode_transaction(invalid_tx)
        raw_valid_tx = encode_transaction(valid_tx)

        response = await self.app.prepare_proposal(
            RequestPrepareProposal(
                max_tx_bytes=len(raw_invalid_tx) + len(raw_valid_tx),
                txs=[raw_invalid_tx, raw_valid_tx],
                local_last_commit=CommitInfo(),
                height=1,
                time=Timestamp(seconds=0, nanos=0),
                next_validators_hash=b"",
                proposer_address=b"",
            )
        )

        self.assertEqual(response.txs, [raw_valid_tx])
    async def test_prepare_proposal_skips_duplicate_nonce(self):
        # Gaýtalanýan nonce bilen tranzaksiýany geçmek
        tx1 = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=100,
            nonce=1,
        )
        tx2 = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=200,
            nonce=1,
        )

        raw_tx1 = encode_transaction(tx1)
        raw_tx2 = encode_transaction(tx2)

        response = await self.app.prepare_proposal(
            RequestPrepareProposal(
                max_tx_bytes=len(raw_tx1) + len(raw_tx2),
                txs=[raw_tx1, raw_tx2],
                local_last_commit=CommitInfo(),
                height=1,
                time=Timestamp(seconds=0, nanos=0),
                next_validators_hash=b"",
                proposer_address=b"",
            )
        )

        self.assertEqual(response.txs, [raw_tx1])

    def test_apply_transaction_rejects_insufficient_balance(self):
        # Ýeterlik däl serişdeli tranzaksiýany ret etmek
        tx = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=999999999,
            nonce=1,
        )
        raw_tx = encode_transaction(tx)
        accounts = self.storage.get_all_accounts()

        with self.assertRaises(ValueError):
            self.app._apply_transaction(accounts, raw_tx)

    def test_apply_transaction_rejects_recipient_balance_overflow(self):
        # Alyjynyň balansyny iň ýokary çäge ýakynlaşdyrmak
        accounts = self.storage.get_all_accounts()
        accounts[self.recipient]["balance_minor"] = MAX_INTEGER - 50

        # Balansyň çäkden geçmegine sebäp bolýan tranzaksiýa
        tx = create_signed_transaction(
            self.sender_private_key,
            self.recipient,
            amount_minor=100,
            nonce=1,
        )

        raw_tx = encode_transaction(tx)

        # Tranzaksiýanyň ret edilmelidigini barlamak
        with self.assertRaises(ValueError):
            self.app._apply_transaction(accounts, raw_tx)

        # Ýalňyşlykdan soň iberijiniň balansynyň üýtgemändigini barlamak
        self.assertEqual(accounts[self.sender]["balance_minor"], 1000)

        # Alyjynyň balansynyň hem üýtgemändigini barlamak
        self.assertEqual(
            accounts[self.recipient]["balance_minor"],
            MAX_INTEGER - 50,
        )
    async def test_init_chain_saves_genesis_state(self):
        response = await self.app.init_chain(
            RequestInitChain(
                time=Timestamp(seconds=0, nanos=0),
                chain_id="tmc-test",
                consensus_params=None,
                validators=[],
            )
        )

        chain_state = self.storage.get_chain_state()
        expected_hash = self.app._state_hash(
            self.storage.get_all_accounts()
        )

        self.assertEqual(response.app_hash, expected_hash)
        self.assertEqual(chain_state["height"], 0)
        self.assertEqual(chain_state["app_hash"], expected_hash.hex())

        self.assertEqual(self.app.height, 0)
        self.assertEqual(self.app.app_hash, expected_hash)

    async def test_init_chain_does_not_overwrite_existing_state(self):
        existing_accounts = self.storage.get_all_accounts()
        existing_hash = self.app._state_hash(existing_accounts).hex()

        self.storage.save_committed_state(
            accounts=existing_accounts,
            height=0,
            app_hash=existing_hash,
        )

        # Bar bolan ýagdaýyň hash bahasyny ýatda saklamak
        saved_hash = self.storage.get_chain_state()["app_hash"]

        response = await self.app.init_chain(
            RequestInitChain(
                time=Timestamp(seconds=0, nanos=0),
                chain_id="tmc-test",
                consensus_params=None,
                validators=[],
            )
        )

        self.assertEqual(response.app_hash.hex(), saved_hash)
        self.assertEqual(
            self.storage.get_chain_state()["app_hash"],
            saved_hash,
        )
if __name__ == "__main__":
    unittest.main()
