import copy
import hashlib
import json
import logging
from typing import Union
import os

from abci import abc
from abci.abc import (
    ConsensusHandler,
    InfoHandler,
    MempoolHandler,
    StateSyncHandler,
)
from abci.types import (
    RequestInfo,
    ResponseInfo,
    RequestInitChain,
    ResponseInitChain,
    RequestCheckTx,
    ResponseCheckTx,
    RequestQuery,
    ResponseQuery,
    RequestPrepareProposal,
    ResponsePrepareProposal,
    RequestProcessProposal,
    ResponseProcessProposal,
    ProposalStatus,
    RequestExtendVote,
    ResponseExtendVote,
    RequestVerifyVoteExtension,
    ResponseVerifyVoteExtension,
    VerifyStatus,
    RequestFinalizeBlock,
    ResponseFinalizeBlock,
    ExecTxResult,
    RequestCommit,
    ResponseCommit,
    RequestListSnapshots,
    ResponseListSnapshots,
    RequestOfferSnapshot,
    ResponseOfferSnapshot,
    RequestLoadSnapshotChunk,
    ResponseLoadSnapshotChunk,
    RequestApplySnapshotChunk,
    ResponseApplySnapshotChunk,
)
from tmc_storage import TMCStorage
from tmc_transaction import decode_transaction

from tmc_constants import MAX_INTEGER

class TMCApp(
    abc.Application,
    ConsensusHandler,
    InfoHandler,
    MempoolHandler,
    StateSyncHandler,
):
    """TMC töleg ulgamynyň ABCI programmasy."""

    def __init__(self, storage=None):
        self._logger = logging.getLogger("tmc")

        # Hasaplaryň maglumatlar bazasyny taýýarlamak
        self.storage = storage if storage is not None else TMCStorage()        

        # Tassyklanan ýagdaýy maglumatlar bazasyndan dikeltmek
        saved_state = self.storage.get_chain_state()
        self.height = saved_state["height"]
        # Emitentiň ýagdaýyny dikeltmek
        self.issuer_nonce = saved_state["issuer_nonce"]

        # Emitentiň açyk açaryny daşky gurşawdan almak
        issuer_public_key_hex = os.getenv("TMC_ISSUER_PUBLIC_KEY")

        self.issuer_public_key = None

        if issuer_public_key_hex:
            try:
                issuer_public_key = bytes.fromhex(issuer_public_key_hex)
            except ValueError as exc:
                raise ValueError("Emitentiň açyk açary nädogry.") from exc

            if len(issuer_public_key) != 32:
                raise ValueError("Emitentiň açyk açary 32 baýt bolmaly.")

            self.issuer_public_key = issuer_public_key

        saved_hash = saved_state["app_hash"]

        if saved_hash:
            # Saklanan blok hash-y barlamak
            if not isinstance(saved_hash, str) or len(saved_hash) != 64:
                raise ValueError(
                    "Maglumatlar bazasyndaky blok hash-y nädogry."
                )

            try:
                stored_hash = bytes.fromhex(saved_hash)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "Maglumatlar bazasyndaky blok hash-y nädogry."
                ) from exc

            if len(stored_hash) != 32:
                raise ValueError(
                    "Maglumatlar bazasyndaky blok hash-y nädogry."
                )

            # Hasaplaryň häzirki ýagdaýyny barlamak
            accounts = self.storage.get_all_accounts()
            calculated_hash = self._state_hash(
                accounts,
                self.issuer_nonce,
            )

            if calculated_hash != stored_hash:
                raise ValueError(
                    "Maglumatlar bazasyndaky ýagdaý hash-y bilen gabat gelmeýär."
                )

            self.app_hash = stored_hash

        else:
            if self.height > 0:
                raise ValueError(
                    "Blok beýikligi bar, ýöne blok hash-y ýok."
                )

            self.app_hash = b""

        # Tassyklanmadyk blok üçin wagtlaýyn maglumatlar
        self.pending_height = None
        self.pending_hash = None
        self.pending_accounts = None
        self.pending_issuer_nonce = None

    @property
    def logger(self) -> logging.Logger:
        return self._logger

    @property
    def handlers(
        self,
    ) -> Union[
        ConsensusHandler,
        InfoHandler,
        MempoolHandler,
        StateSyncHandler,
    ]:
        return self

    @staticmethod
    def _state_hash(accounts, issuer_nonce=0):
        # Hasaplary hemişe birmeňzeş tertipde kodlamak
        account_state = [
            {
                "address": address,
                "balance_minor": account["balance_minor"],
                "nonce": account["nonce"],
                "public_key": account["public_key"],
            }
            for address, account in sorted(accounts.items())
        ]

        # Köne bloklaryň hash formatyny saklamak
        if issuer_nonce == 0:
            state = account_state
        else:
            state = {
                "accounts": account_state,
                "issuer_nonce": issuer_nonce,
            }

        encoded = json.dumps(
            state,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")

        return hashlib.sha256(encoded).digest()

    def _apply_transaction(self, accounts, raw_tx, issuer_nonce=0):
    # Tranzaksiýanyň görnüşini we goluny barlamak
        tx = decode_transaction(raw_tx)

        # Täze hasaby hasaba almak
        if tx["type"] == "register_account":
            address = tx["address"]

            if address in accounts:
                raise ValueError("Bu hasap eýýäm hasaba alnan.")

            accounts[address] = {
                "address": address,
                "balance_minor": 0,
                "nonce": 0,
                "public_key": tx["public_key"],
            }

            return issuer_nonce

        # TMC çykarmak
        if tx["type"] == "mint":
            if self.issuer_public_key is None:
                raise ValueError("Emitentiň açyk açary sazlanmady.")

            if tx["public_key"] != self.issuer_public_key.hex():
                raise ValueError("Emitentiň açyk açary gabat gelmeýär.")

            if issuer_nonce >= MAX_INTEGER:
                raise ValueError("Emitentiň nonce çägi doldu.")

            if tx["nonce"] != issuer_nonce + 1:
                raise ValueError("Emitentiň nonce bahasy nädogry.")

            recipient_address = tx["recipient"]
            recipient = accounts.get(recipient_address)

            if recipient is None:
                raise ValueError("TMC alyjysynyň hasaby tapylmady.")

            amount = tx["amount_minor"]

            if recipient["balance_minor"] > MAX_INTEGER - amount:
                raise ValueError("Alyjynyň balansy rugsat edilen çäkden geçýär.")

            # TMC serişdelerini hasaba goşmak
            recipient["balance_minor"] += amount

            return tx["nonce"]

        # Adaty töleg tranzaksiýasy
        if tx["type"] != "transfer":
            raise ValueError("Tranzaksiýanyň görnüşi nädogry.")

        sender_address = tx["sender"]
        recipient_address = tx["recipient"]

        sender = accounts.get(sender_address)
        recipient = accounts.get(recipient_address)

        if sender is None:
            raise ValueError("Iberijiniň hasaby tapylmady.")

        if recipient is None:
            raise ValueError("Alyjynyň hasaby tapylmady.")

        if sender_address == recipient_address:
            raise ValueError("Bir hasapdan şol bir hasaba töleg bolmaýar.")

        if sender["public_key"] != tx["public_key"]:
            raise ValueError("Açyk açar hasaba gabat gelmeýär.")

        if sender["nonce"] >= MAX_INTEGER:
            raise ValueError("Iberijiniň nonce çägi doldu.")

        if tx["nonce"] != sender["nonce"] + 1:
            raise ValueError("Tranzaksiýanyň nonce bahasy nädogry.")

        amount = tx["amount_minor"]

        if sender["balance_minor"] < amount:
            raise ValueError("Hasapda serişdeler ýeterlik däl.")

        if recipient["balance_minor"] > MAX_INTEGER - amount:
            raise ValueError("Alyjynyň balansy rugsat edilen çäkden geçýär.")

        # Üýtgeşmeler diňe wagtlaýyn ýagdaýda ýerine ýetirilýär
        sender["balance_minor"] -= amount
        sender["nonce"] = tx["nonce"]
        recipient["balance_minor"] += amount

        return issuer_nonce

    async def info(self, req: RequestInfo) -> ResponseInfo:
        return ResponseInfo(
            data="TMC",
            version="0.1.0",
            last_block_height=self.height,
            last_block_app_hash=self.app_hash,
        )

    async def init_chain(
        self, req: RequestInitChain
    ) -> ResponseInitChain:

        # Häzirki blok ýagdaýyny almak
        chain_state = self.storage.get_chain_state()

        # Blok beýikligi bar bolsa, öň döredilen zynjyry ulanmak
        if chain_state["height"] > 0:
            if not chain_state["app_hash"]:
                raise ValueError("Blok hash-y tapylmady.")

            self.height = chain_state["height"]
            self.app_hash = bytes.fromhex(chain_state["app_hash"])

            return ResponseInitChain(app_hash=self.app_hash)

        # Öň başlangyç hash ýazylan bolsa, ony gaýtadan ulanmak
        if chain_state["app_hash"]:
            self.height = chain_state["height"]
            self.app_hash = bytes.fromhex(chain_state["app_hash"])

            return ResponseInitChain(app_hash=self.app_hash)
        # Başlangyç hasaplaryň ýagdaýyny almak
        accounts = self.storage.get_all_accounts()

        # Genesis ýagdaýynyň hash bahasyny hasaplamak
        self.app_hash = self._state_hash(
            accounts,
            self.issuer_nonce,
        )

        # Başlangyç ýagdaýy maglumatlar bazasyna ýazmak
        self.storage.save_committed_state(
            accounts=accounts,
            height=0,
            app_hash=self.app_hash.hex(),
            issuer_nonce=self.issuer_nonce,
        )

        self.height = 0

        return ResponseInitChain(app_hash=self.app_hash)

    async def check_tx(
        self, req: RequestCheckTx
    ) -> ResponseCheckTx:
        # Tranzaksiýanyň deslapky barlagy
        try:
            accounts = self.storage.get_all_accounts()
            issuer_nonce = self.storage.get_chain_state()["issuer_nonce"]

            self._apply_transaction(
                accounts,
                req.tx,
                issuer_nonce,
            )

        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            self._logger.exception("Tranzaksiýa barlagynda ýalňyşlyk:")
            return ResponseCheckTx(
                code=1,
                log=str(exc),
            )

        return ResponseCheckTx(
            code=0,
            log="Tranzaksiýa deslapky barlagdan geçdi.",
        )

    async def query(self, req: RequestQuery) -> ResponseQuery:
        # Hasap ýagdaýyny görmek üçin ýönekeý API
        try:
            path = req.path.strip("/")
            parts = path.split("/")

            if len(parts) == 2 and parts[0] == "account":
                account = self.storage.get_account(parts[1])

                if account is None:
                    return ResponseQuery(
                        code=1,
                        log="Hasap tapylmady.",
                    )

                data = json.dumps(
                    account,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")

                return ResponseQuery(
                    code=0,
                    value=data,
                    log="Hasap tapyldy.",
                )

            if path == "state":
                state = {
                    "height": self.height,
                    "app_hash": self.app_hash.hex(),
                    "accounts": self.storage.get_all_accounts(),
                    "issuer_nonce": self.issuer_nonce,
                }

                return ResponseQuery(
                    code=0,
                    value=json.dumps(
                        state,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8"),
                    log="Ulgamyň ýagdaýy alyndy.",
                )

        except (ValueError, TypeError, KeyError):
            return ResponseQuery(
                code=1,
                log="Talap maglumatlary nädogry.",
            )

        return ResponseQuery(
            code=1,
            log="Talap ýoly goldanylmaýar.",
        )

   
    
    async def prepare_proposal(
        self, req: RequestPrepareProposal
    ) -> ResponsePrepareProposal:
        # Teklip üçin hasaplaryň wagtlaýyn ýagdaýyny almak
        accounts = self.storage.get_all_accounts()
        issuer_nonce = self.storage.get_chain_state()["issuer_nonce"]
        selected_txs = []
        total_bytes = 0
        max_bytes = max(0, req.max_tx_bytes)

        for raw_tx in req.txs:
            tx_size = len(raw_tx)

            # Ölçeg çäginden geçýän tranzaksiýany geçirmek
            if total_bytes + tx_size > max_bytes:
                continue

            # Tranzaksiýany aýratyn wagtlaýyn ýagdaýda barlamak
            candidate_accounts = copy.deepcopy(accounts)

            try:
                candidate_issuer_nonce = self._apply_transaction(
                    candidate_accounts,
                    raw_tx,
                    issuer_nonce,
                )
            except (ValueError, TypeError, KeyError, OverflowError):
                # Nädogry tranzaksiýany teklibe goşmazlyk
                continue

            # Diňe dogry tranzaksiýany we onuň ýagdaýyny kabul etmek
            selected_txs.append(raw_tx)
            issuer_nonce = candidate_issuer_nonce
            total_bytes += tx_size
            accounts = candidate_accounts

        return ResponsePrepareProposal(txs=selected_txs)


    async def process_proposal(
        self, req: RequestProcessProposal
    ) -> ResponseProcessProposal:
        # Teklipdäki ähli tranzaksiýalary wagtlaýyn barlamak
        accounts = self.storage.get_all_accounts()
        issuer_nonce = self.storage.get_chain_state()["issuer_nonce"]

        try:
            for raw_tx in req.txs:
                issuer_nonce = self._apply_transaction(
                    accounts,
                    raw_tx,
                    issuer_nonce,
                )
        except (ValueError, TypeError, KeyError, OverflowError):
            return ResponseProcessProposal(
                status=ProposalStatus.REJECT
            )

        return ResponseProcessProposal(
            status=ProposalStatus.ACCEPT
        )

    async def extend_vote(
        self, req: RequestExtendVote
    ) -> ResponseExtendVote:
        return ResponseExtendVote()

    async def verify_vote_extension(
        self, req: RequestVerifyVoteExtension
    ) -> ResponseVerifyVoteExtension:
        return ResponseVerifyVoteExtension(
            status=VerifyStatus.ACCEPT
        )

   
    async def finalize_block(
        self, req: RequestFinalizeBlock
    ) -> ResponseFinalizeBlock:

        # Tassyklanan ýagdaýdan wagtlaýyn nusga almak
        accounts = self.storage.get_all_accounts()
        issuer_nonce = self.storage.get_chain_state()["issuer_nonce"]

        # Blok beýikligini barlamak
        if req.height != self.height + 1:
            raise ValueError("Blok beýikligi nädogry.")

        results = []

        # Ähli tranzaksiýalary wagtlaýyn ýagdaýda barlamak
        try:
            for raw_tx in req.txs:
                issuer_nonce = self._apply_transaction(
                    accounts,
                    raw_tx,
                    issuer_nonce,
                )

        except (ValueError, TypeError, KeyError, OverflowError):
            accounts = self.storage.get_all_accounts()
            issuer_nonce = self.storage.get_chain_state()["issuer_nonce"]

            results = [
                ExecTxResult(
                    code=1,
                    log="Blokdaky tranzaksiýalar kabul edilmedi.",
                )
                for _ in req.txs
            ]

        else:
            results = [
                ExecTxResult(
                    code=0,
                    log="Tranzaksiýa üstünlikli ýerine ýetirildi.",
                )
                for _ in req.txs
            ]

        new_hash = self._state_hash(accounts, issuer_nonce)

        self.pending_height = req.height
        self.pending_issuer_nonce = issuer_nonce
        self.pending_hash = new_hash
        self.pending_accounts = accounts

        return ResponseFinalizeBlock(
            tx_results=results,
            app_hash=new_hash,
        )

    async def commit(self, req: RequestCommit) -> ResponseCommit:
        # Tassyklanan ýagdaýyň dolulygyny barlamak
        if self.pending_accounts is not None:

            if (
                self.pending_height is None
                or self.pending_hash is None
            ):
                raise ValueError("Tassyklanan ýagdaý doly däl.")

            # Tassyklanan ýagdaýy maglumatlar bazasyna bilelikde ýazmak
            self.storage.save_committed_state(
                accounts=self.pending_accounts,
                height=self.pending_height,
                app_hash=self.pending_hash.hex(),
                issuer_nonce=self.pending_issuer_nonce,
            )

            self.height = self.pending_height
            self.app_hash = self.pending_hash
            self.issuer_nonce = self.pending_issuer_nonce

            self.pending_height = None
            self.pending_hash = None
            self.pending_accounts = None
            self.pending_issuer_nonce = None

        return ResponseCommit()

    async def list_snapshots(
        self, req: RequestListSnapshots
    ) -> ResponseListSnapshots:
        return ResponseListSnapshots()

    async def offer_snapshot(
        self, req: RequestOfferSnapshot
    ) -> ResponseOfferSnapshot:
        return ResponseOfferSnapshot()

    async def load_snapshot_chunk(
        self, req: RequestLoadSnapshotChunk
    ) -> ResponseLoadSnapshotChunk:
        return ResponseLoadSnapshotChunk()

    async def apply_snapshot_chunk(
        self, req: RequestApplySnapshotChunk
    ) -> ResponseApplySnapshotChunk:
        return ResponseApplySnapshotChunk()
