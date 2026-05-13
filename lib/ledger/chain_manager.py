from datetime import datetime
from lib.ledger.helpers import compute_hash, compute_merkle_root, check_hash_difficulty, EMPTY_HASH
from lib.ledger.state_manager import StateManager
from lib.ledger.tx_manager import TxManager
from lib.ledger.validator import LedgerError
import time
from threading import Lock
import lib.database as database
from lib.database import db, Transaction, Block, User
from lib.logger import ledger_logger
from libcpp.cpp_wrapper import reward_function

GENESIS_BLOCK_REWARD = int(1e9)
mining_lock = Lock()


class BlockchainBroken(LedgerError):
    def __init__(self, height: int, reason: str) -> None:
        self.height = height
        self.reason = reason
        super().__init__(f"BLOCKCHAIN BROKEN at height {self.height}! {reason}")


class BlockNotMined(LedgerError):
    def __init__(self, height: int, block_hash: str) -> None:
        self.height = height
        self.block_hash = block_hash
        super().__init__(f"Block not mined at height {self.height}! {block_hash}")


class ChainManager:
    def __init__(self, state: StateManager, tx: TxManager, base_block_reward: int, difficulty: int):
        self._state = state
        self._tx = tx
        self.base_block_reward = base_block_reward
        self.diff = "0" * difficulty  # block mining difficulty
        self.genesis_id = 0

    def set_genesis_id(self, genesis_id: int) -> None:
        self.genesis_id = genesis_id

    def load_and_verify_chain(self, genesis_username: str) -> str:
        t = time.monotonic()
        self._state.clear()

        with db.atomic():
            blocks = database.get_blocks(ascending=True)
            if not blocks:
                self.init_genesis(database.create_user(self.genesis_id, genesis_username))
                return "Genesis block created!"

            if blocks[0].miner.id != self.genesis_id:
                raise BlockchainBroken(
                    blocks[0].height,
                    f"Genesis user id mismatch! '{blocks[0].miner.id}' != '{self.genesis_id}'"
                )

            prev_block = self.get_last_block(empty_block=True)
            for height, block in enumerate(blocks):
                txs = database.get_block_transactions(block, ascending=True)

                # Check coinbase
                if len(txs) == 0 or txs[-1].from_user is not None:
                    raise BlockchainBroken(block.height, f"No coinbase transaction in block")

                for i in range(len(txs) - 1):
                    if txs[i].from_user is None:
                        raise BlockchainBroken(
                            block.height, f"Several coinbase transactions in block, transaction: {txs[i]}"
                        )

                coinbase_tx = txs[-1]
                miner_user_id = coinbase_tx.to_user.id
                miner = database.get_user_or_exception(miner_user_id)
                if miner_user_id != block.miner.id:
                    raise BlockchainBroken(
                        block.height,
                        f"Coinbase transaction user id: {miner_user_id}, block miner user id: {block.miner.id}"
                    )

                miner_reward = coinbase_tx.amount
                total_fees = self.calculate_total_fees(txs)
                expected_base_reward = reward_function(self.base_block_reward, prev_block.height + 1, prev_block.nonce)
                if block.height != 0 and (
                        block.base_reward != expected_base_reward or block.total_fees != total_fees or miner_reward != expected_base_reward + total_fees
                ):
                    raise BlockchainBroken(
                        block.height,
                        f"Transaction coinbase amount: {miner_reward}, "
                        f"transaction total fees: {total_fees}, "
                        f"block base reward: {block.base_reward}, "
                        f"block total fees: {block.total_fees}, "
                        f"expected base reward: {expected_base_reward}"
                    )

                merkle_root = compute_merkle_root([tx.tx_hash for tx in txs])
                if merkle_root != block.merkle_root:
                    raise BlockchainBroken(
                        block.height, f"Transactions merkle root: {merkle_root}, block merkle root: {block.merkle_root}"
                    )

                try:
                    expected_block = self.create_block(
                        miner, merkle_root, height, prev_block.block_hash, self.diff, block.base_reward,
                        block.total_fees,
                        block.nonce, block.timestamp
                    )
                except BlockNotMined as e:
                    raise BlockchainBroken(
                        block.height, f"Computed hash: {e.block_hash}, difficulty: {self.diff}"
                    )

                if expected_block.block_hash != block.block_hash:
                    raise BlockchainBroken(
                        block.height, f"Block hash: {block.block_hash}, expected hash: {expected_block.block_hash}"
                    )

                self._state.apply_tx(txs)
                prev_block = expected_block

        pending_txs = database.get_pending_transactions(ascending=True)
        self._state.apply_tx(pending_txs)

        return (
            f"Blockchain verified in {time.monotonic() - t:.3f} seconds!\n"
            f"Blocks loaded: {database.get_blocks_count()}\n"
            f"Transactions loaded: {database.get_transactions_count()} ({len(pending_txs)} pending)\n"
            f"Users with balance: {len(self._state.get_all_balances())}"
        )

    @staticmethod
    def calculate_total_fees(txs: list[Transaction]):
        return sum(tx.fee for tx in txs)

    def init_genesis(self, genesis_user: User):
        if database.get_blocks_count() == 0:
            self.__mine_block(genesis_user, GENESIS_BLOCK_REWARD, "Genesis block reward")
            ledger_logger.info("Genesis block created!")

    def mine_block(self, miner_user_id: int = None, nonce: int = None) -> Block | None:
        if miner_user_id is None:
            miner_user_id = self.genesis_id
        miner = database.get_user_or_exception(miner_user_id)

        with mining_lock:
            pending_txs = database.get_pending_transactions(ascending=True)

            if not pending_txs and nonce is None:
                return None

            return self.__mine_block(miner=miner, pending_txs=pending_txs, nonce=nonce)

    def __mine_block(self, miner: User, base_reward: int = None, tx_description="Block reward",
                     pending_txs: list[Transaction] = None, nonce: int = None) -> Block:
        last_block = self.get_last_block()
        if base_reward is None:
            base_reward = reward_function(self.base_block_reward, last_block.height + 1, last_block.nonce)
        if pending_txs is None:
            pending_txs = []

        with db.atomic():
            total_fees = self.calculate_total_fees(pending_txs)
            coinbase_tx = self._tx.create_transaction(None, miner.id, base_reward + total_fees, tx_description)
            pending_txs += [coinbase_tx]
            merkle_root = compute_merkle_root([tx.tx_hash for tx in pending_txs])

            block = self.create_block(
                miner, merkle_root, last_block.height + 1, last_block.block_hash, self.diff,
                base_reward, total_fees, nonce
            )
            self._tx.save_tx(coinbase_tx)
            block.save(force_insert=True)

            for tx in pending_txs:
                tx.block = block
                tx.save()

            ledger_logger.info(
                f"Block {block.height} with {len(pending_txs)} transactions mined by {block.miner}! Nonce: {block.nonce}, Block hash: {block.block_hash}"
            )
            return block

    @staticmethod
    def get_last_block(empty_block=False) -> Block:
        last_block = database.get_last_block() if not empty_block else None
        return last_block if last_block else Block(height=-1, nonce=0, block_hash=EMPTY_HASH)

    @staticmethod
    def create_block(miner: User, merkle_root: str, height: int, prev_hash: str, diff: str,
                     base_reward: int, total_fees: int, nonce: int = None, timestamp: str = None) -> Block:
        if timestamp is None:
            timestamp = datetime.now().isoformat()

        block_data = dict()
        block_data.update({
            "height": height,
            "timestamp": timestamp,
            "miner": miner.id,
            "base_reward": base_reward,
            "total_fees": total_fees,
            "merkle_root": merkle_root,
            "prev_hash": prev_hash
        })
        block_data["nonce"] = ChainManager.mine_nonce(block_data, diff) if nonce is None else nonce
        block_data["block_hash"] = compute_hash(block_data)

        if not check_hash_difficulty(block_data["block_hash"], diff):
            raise BlockNotMined(height, block_data["block_hash"])

        block_data["miner"] = miner
        return Block(**block_data)

    @staticmethod
    def mine_nonce(block_data: dict, diff: str) -> int:
        nonce = 0
        while True:
            block_data["nonce"] = nonce
            block_hash = compute_hash(block_data)
            if check_hash_difficulty(block_hash, diff):
                break
            nonce += 1
        return nonce
