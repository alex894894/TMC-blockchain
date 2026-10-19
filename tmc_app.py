
import hashlib
import logging
from typing import Union

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


class TMCApp(
    abc.Application,
    ConsensusHandler,
    InfoHandler,
    MempoolHandler,
    StateSyncHandler,
):
    """Минимальное ABCI-приложение для проверки подключения TMC."""

    def __init__(self):
        self._logger = logging.getLogger("tmc")
        self.height = 0
        self.app_hash = b""
        self.pending_height = 0
        self.pending_hash = b""

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
        self.app_hash = hashlib.sha256(
            req.app_state_bytes
        ).digest()
        return ResponseInitChain(app_hash=self.app_hash)

    async def check_tx(
        self, req: RequestCheckTx
    ) -> ResponseCheckTx:
        # Временно разрешаем транзакции только для smoke-теста.
        return ResponseCheckTx()

    async def query(self, req: RequestQuery) -> ResponseQuery:
        return ResponseQuery(
            log="TMC test application; queries not implemented"
        )

    async def prepare_proposal(
        self, req: RequestPrepareProposal
    ) -> ResponsePrepareProposal:
        return ResponsePrepareProposal(txs=req.txs)

    async def process_proposal(
        self, req: RequestProcessProposal
    ) -> ResponseProcessProposal:
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
        # Временный детерминированный hash для smoke-теста.
        digest = hashlib.sha256()
        digest.update(self.app_hash)
        digest.update(req.height.to_bytes(8, "big"))

        for tx in req.txs:
            digest.update(len(tx).to_bytes(8, "big"))
            digest.update(tx)

        self.pending_height = req.height
        self.pending_hash = digest.digest()

        return ResponseFinalizeBlock(
            tx_results=[ExecTxResult() for _ in req.txs],
            app_hash=self.pending_hash,
        )

    async def commit(self, req: RequestCommit) -> ResponseCommit:
        self.height = self.pending_height
        self.app_hash = self.pending_hash
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
