import csv
import hashlib
import json
import time
from threading import Lock
from datetime import datetime
from io import StringIO
from typing import BinaryIO
from lib import database
from lib.database import db, User, Transaction, Block
from lib.logger import ledger_logger

MONEY_TYPE = int | str | float

GENESIS_BLOCK_REWARD = int(1e9)
EMPTY_HASH = "0" * 64
mining_lock = Lock()


class LedgerError(Exception):
    pass


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


class BalanceError(LedgerError):
    pass


def compute_hash(data: dict) -> str:
    payload = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def compute_merkle_root(tx_hashes: list[str]) -> str:
    if len(tx_hashes) == 0:
        return EMPTY_HASH

    level = [bytes.fromhex(h) for h in tx_hashes]

    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])

        next_level = []
        for i in range(0, len(level), 2):
            combined = level[i] + level[i + 1]
            hash1 = hashlib.sha256(combined).digest()
            hash2 = hashlib.sha256(hash1).digest()
            next_level.append(hash2)

        level = next_level

    return level[0].hex()


def check_hash_difficulty(block_hash: str, diff: str) -> bool:
    return block_hash.startswith(diff)


def reward_function(base_reward: int, block_number: int) -> int:
    return base_reward + block_number * 0


class Ledger:
    def __init__(self, base_block_reward: int, difficulty=2):
        self.base_block_reward = base_block_reward
        self.diff = "0" * difficulty  # block mining difficulty
        self.genesis_id = 0
        self.fee_percentage = 0
        self.__balances: dict[int, int] = dict()
        self.__max_balances: dict[int, int] = dict()
        self.__total_gain: dict[int, int] = dict()

    def init_genesis(self, genesis_user: User):
        if database.get_blocks_count() == 0:
            self.__mine_block(genesis_user, GENESIS_BLOCK_REWARD, "Genesis block reward")
            ledger_logger.info("Genesis block created!")

    def __update_balance(self, tx: Transaction) -> None:
        if tx.from_user:
            deduction = tx.amount + tx.fee
            if tx.from_user.id not in self.__balances or self.__balances[tx.from_user.id] < deduction:
                raise BalanceError(f"Insufficient balance! {self.__balances[tx.from_user.id]} < {deduction}")
            self.__balances[tx.from_user.id] -= deduction

        if tx.to_user.id not in self.__balances:
            self.__balances[tx.to_user.id] = tx.amount
            self.__total_gain[tx.to_user.id] = tx.amount
            self.__max_balances[tx.to_user.id] = self.__balances[tx.to_user.id]
        else:
            self.__balances[tx.to_user.id] += tx.amount
            self.__total_gain[tx.to_user.id] += tx.amount
            self.__max_balances[tx.to_user.id] = max(self.__max_balances[tx.to_user.id], self.__balances[tx.to_user.id])

    def __update_balance_transactions(self, txs: list[Transaction]) -> None:
        for tx in txs:
            self.__update_balance(tx)

    def __revert_balance_transactions(self, txs: list[Transaction]) -> None:
        for tx in txs:
            self.__update_balance(tx)

    @staticmethod
    def calculate_total_fees(txs: list[Transaction]):
        return sum(tx.fee for tx in txs)

    def load_and_verify_chain(self, genesis_id: int, genesis_username: str) -> str:
        self.genesis_id = genesis_id

        t = time.monotonic()
        self.__balances.clear()

        with db.atomic():
            blocks = database.get_blocks(ascending=True)
            if not blocks:
                self.init_genesis(database.create_user(genesis_id, genesis_username))
                return "Genesis block created!"

            if blocks[0].miner.id != self.genesis_id:
                raise BlockchainBroken(
                    blocks[0].height,
                    f"Genesis user id mismatch! '{blocks[0].miner.id}' != '{self.genesis_id}'"
                )

            prev_hash = EMPTY_HASH
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
                expected_base_reward = reward_function(self.base_block_reward, block.height)
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
                        miner, merkle_root, height, prev_hash, self.diff, block.base_reward, block.total_fees,
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

                self.__update_balance_transactions(txs)
                prev_hash = block.block_hash

        self.__update_balance_transactions(database.get_pending_transactions(ascending=True))

        return (
            f"Blockchain verified in {time.monotonic() - t:.3f} seconds!\n"
            f"Blocks loaded: {database.get_blocks_count()}\n"
            f"Transactions loaded: {database.get_transactions_count()}\n"
            f"Users with balance: {len(self.__balances)}"
        )

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
            base_reward = reward_function(self.base_block_reward, last_block.height + 1)
        if pending_txs is None:
            pending_txs = []

        with db.atomic():
            total_fees = self.calculate_total_fees(pending_txs)
            coinbase_tx = self.create_transaction(None, miner.id, base_reward + total_fees, tx_description)
            pending_txs += [coinbase_tx]
            merkle_root = compute_merkle_root([tx.tx_hash for tx in pending_txs])

            block = self.create_block(
                miner, merkle_root, last_block.height + 1, last_block.block_hash, self.diff,
                base_reward, total_fees, nonce
            )
            self.__record_transaction(coinbase_tx)
            block.save(force_insert=True)

            for tx in pending_txs:
                tx.block = block
                tx.save()

            ledger_logger.info(
                f"Block {block.height} with {len(pending_txs)} transactions mined by {block.miner}! Nonce: {block.nonce}, Block hash: {block.block_hash}"
            )
            return block

    @staticmethod
    def get_last_block() -> Block:
        last_block = database.get_last_block()
        return last_block if last_block else Block(height=-1, block_hash=EMPTY_HASH)

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
        block_data["nonce"] = Ledger.mine_nonce(block_data, diff) if nonce is None else nonce
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

    @staticmethod
    def create_transaction(from_user_id: int | None, to_user_id: int, amount: MONEY_TYPE,
                           description: str = None, timestamp: str = None, fee: MONEY_TYPE = 0) -> Transaction:
        amount = int(amount)
        fee = int(fee)

        if amount <= 0:
            raise BalanceError("Amount must be positive")

        tx_data = dict()
        tx_data.update({
            "timestamp": datetime.now().isoformat() if timestamp is None else timestamp,
            "from_user": from_user_id if from_user_id else None,
            "to_user": to_user_id,
            "amount": amount,
            "fee": fee,
            "description": description,
        })

        tx_data["tx_hash"] = compute_hash(tx_data)
        tx_data["from_user"] = database.get_user_or_exception(from_user_id) if from_user_id else None
        tx_data["to_user"] = database.get_user_or_exception(to_user_id)
        return Transaction(**tx_data)

    def __record_transaction(self, tx: Transaction):
        self.__update_balance(tx)
        ledger_logger.info(f"Transaction recorded {tx.from_user} -> {tx.to_user}: {tx.amount}, {tx.description}")

    def record_transaction(self, from_user_id: int, to_user_id: int, amount: MONEY_TYPE,
                           description: str = None, timestamp: str = None) -> Transaction:
        tx = self.create_transaction(
            from_user_id, to_user_id, amount, description, timestamp, int(int(amount) * self.fee_percentage)
        )
        self.__record_transaction(tx)
        tx.save()
        return tx

    def record_deposit(self, from_user_id: int, amount: MONEY_TYPE, description: str = None):
        self.record_transaction(from_user_id, self.genesis_id, amount, description)

    def record_gain(self, to_user_id: int, amount: MONEY_TYPE, description: str = None):
        self.record_transaction(self.genesis_id, to_user_id, amount, description)

    def get_user_balance(self, user_id: int) -> int:
        return self.__balances.get(user_id, 0)

    def get_user_max_balance(self, user_id: int) -> int:
        return self.__max_balances.get(user_id, 0)

    def get_user_total_gain(self, user_id: int) -> int:
        return self.__total_gain.get(user_id, 0)

    @staticmethod
    def fill_in_users(l: list[tuple[int, int]]) -> list[tuple[User, int]]:
        return [(database.get_user_or_exception(user_id), amount) for user_id, amount in l]

    def get_all_balances(self) -> list[tuple[User, int]]:
        return self.fill_in_users(sorted(list(self.__balances.items()), key=lambda item: item[1], reverse=True))

    def get_all_max_balances(self) -> list[tuple[User, int]]:
        return self.fill_in_users(sorted(list(self.__max_balances.items()), key=lambda item: item[1], reverse=True))

    def get_all_total_gains(self) -> list[tuple[User, int]]:
        return self.fill_in_users(sorted(list(self.__total_gain.items()), key=lambda item: item[1], reverse=True))

    def delete_pending_transactions(self) -> int:
        self.__revert_balance_transactions(database.get_pending_transactions(ascending=False))
        return database.delete_pending_transactions()

    def import_transactions_csv(self, file: BinaryIO) -> int:
        reader = csv.reader(StringIO(file.read().decode("utf-8")), delimiter=' ', quotechar='"')
        next(reader)
        count = 0
        with db.atomic():
            for row in reader:
                if all(row):
                    count += 1
                    self.record_transaction(*row)

        return count

    @staticmethod
    def export_transactions_csv() -> str:
        file = StringIO()
        writer = csv.writer(file, delimiter=' ', quotechar='"')
        writer.writerow(["from_user", "to_user", "amount", "description", "timestamp"])
        for tx in database.get_transactions(ascending=True):
            writer.writerow([
                tx.from_user.id if tx.from_user else None,
                tx.to_user.id,
                tx.amount,
                tx.description,
                tx.timestamp
            ])
        file.name = "transactions.csv"
        return file.getvalue()
