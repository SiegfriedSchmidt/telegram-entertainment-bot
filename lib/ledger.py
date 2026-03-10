import csv
import hashlib
import json
import time
from threading import Lock
from decimal import Decimal
from datetime import datetime
from io import StringIO
from typing import BinaryIO
from lib import database
from lib.database import db, User, Transaction, Block
from lib.logger import ledger_logger

GENESIS_BLOCK_REWARD = Decimal(1e9)
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


class Ledger:
    def __init__(self, block_reward: int | Decimal, difficulty=2):
        self.block_reward = Decimal(block_reward)
        self.difficulty = "0" * difficulty
        self.__genesis_username = ""
        self.__balances: dict[str, Decimal] = dict()
        self.__max_balances: dict[str, Decimal] = dict()

    @property
    def genesis_username(self) -> str:
        return self.__genesis_username

    @genesis_username.setter
    def genesis_username(self, username: str):
        self.__genesis_username = username

    def check_hash_difficulty(self, block_hash: str) -> bool:
        return block_hash.startswith(self.difficulty)

    def init_genesis(self):
        if database.get_blocks_count() == 0:
            self.__mine_block(self.__genesis_username, GENESIS_BLOCK_REWARD, "Genesis block reward")
            ledger_logger.info("Genesis block created!")

    def __update_balance(self, from_username: str | None, to_username: str, amount: Decimal) -> None:
        if from_username:
            if from_username not in self.__balances or self.__balances[from_username] < amount:
                raise BalanceError("Negative balance detected!")
            self.__balances[from_username] -= amount

        if to_username not in self.__balances:
            self.__balances[to_username] = amount
            self.__max_balances[to_username] = self.__balances[to_username]
        else:
            self.__balances[to_username] += amount
            self.__max_balances[to_username] = max(self.__max_balances[to_username], self.__balances[to_username])

    def __update_balance_transactions(self, txs: list[Transaction]) -> None:
        for tx in txs:
            self.__update_balance(
                tx.from_user.username if tx.from_user else None,
                tx.to_user.username,
                tx.amount
            )

    def __revert_balance_transactions(self, txs: list[Transaction]) -> None:
        for tx in txs:
            self.__update_balance(
                tx.to_user.username,
                tx.from_user.username if tx.from_user else None,
                tx.amount
            )

    def load_and_verify_chain(self):
        t = time.monotonic()
        self.__balances.clear()

        with db.atomic():
            blocks = database.get_blocks(ascending=True)
            if not blocks:
                self.init_genesis()
                return

            if blocks[0].miner.username != self.genesis_username:
                raise BlockchainBroken(
                    blocks[0].height,
                    f"Genesis username mismatch! '{blocks[0].miner.username}' != '{self.genesis_username}'"
                )

            prev_hash = EMPTY_HASH
            for block in blocks:
                txs = database.get_block_transactions(block, ascending=True)
                miner_tx = txs[-1]  # The last transaction in block is miner reward transaction

                merkle_root = compute_merkle_root([tx.tx_hash for tx in txs])
                if merkle_root != block.merkle_root:
                    raise BlockchainBroken(
                        block.height, f"Transactions merkle root: {merkle_root}, block merkle root: {block.merkle_root}"
                    )

                miner_username = miner_tx.to_user.username
                if miner_username != block.miner.username:
                    raise BlockchainBroken(
                        block.height,
                        f"Transaction miner username: {miner_username}, block miner username: {block.miner.username}"
                    )

                # MINER REWARD CHECK
                # miner_reward = miner_tx.amount
                # if block.height != 0 and miner_reward != self.block_reward:
                #     raise BlockchainBroken(
                #         block.height,
                #         f"Transaction miner reward: {miner_reward}, block miner reward: {self.block_reward}"
                #     )

                block_data = {
                    "height": block.height,
                    "timestamp": block.timestamp,
                    "miner": miner_username,
                    "merkle_root": merkle_root,
                    "nonce": block.nonce,
                    "prev_hash": prev_hash,
                }
                computed_hash = compute_hash(block_data)

                if computed_hash != block.block_hash:
                    raise BlockchainBroken(
                        block.height, f"Block hash: {block.block_hash}, computed hash: {computed_hash}"
                    )

                if not self.check_hash_difficulty(computed_hash):
                    raise BlockchainBroken(
                        block.height, f"Computed hash: {computed_hash}, difficulty: {self.difficulty}"
                    )

                self.__update_balance_transactions(txs)
                prev_hash = computed_hash

        self.__update_balance_transactions(database.get_pending_transactions(ascending=True))
        self.mine_block()

        ledger_logger.info(
            f"Blockchain verified in {time.monotonic() - t:.3f} seconds! "
            f"{database.get_blocks_count()} blocks loaded. "
            f"{database.get_transactions_count()} transactions loaded. "
            f"Users with balance: {len(self.__balances)}"
        )

    def mine_block(self, miner_username: str = None, nonce: int = None) -> Block | None:
        if miner_username is None:
            miner_username = self.__genesis_username

        with mining_lock:
            pending_txs = database.get_pending_transactions(ascending=True)

            if not pending_txs and nonce is None:
                return None

            return self.__mine_block(miner_username=miner_username, pending_txs=pending_txs, nonce=nonce)

    def __mine_block(self, miner_username: str, reward: Decimal = None, tx_description="Block reward",
                     pending_txs: list[Transaction] = None, nonce: int = None) -> Block:
        if reward is None:
            reward = self.block_reward
        if pending_txs is None:
            pending_txs = []

        with db.atomic():
            miner_tx = self.__create_transaction(None, miner_username, reward, tx_description)
            pending_txs += [miner_tx]
            merkle_root = compute_merkle_root([tx.tx_hash for tx in pending_txs])

            block = self.__create_block(miner_username, merkle_root, nonce)
            self.__record_transaction(miner_tx)  # apply miner tx only if block successfully created

            for tx in pending_txs:
                tx.block = block
                tx.save()

            ledger_logger.info(
                f"Block {block.height} with {len(pending_txs)} transactions mined by {block.miner}! Nonce: {block.nonce}, Block hash: {block.block_hash}"
            )
            return block

    def __create_block(self, miner_username: str, merkle_root: str, nonce: int = None) -> Block:
        last_block = Block.select(Block.height, Block.block_hash).order_by(Block.height.desc()).first()
        if last_block is None:
            height = 0
            prev_hash = EMPTY_HASH
        else:
            height = last_block.height + 1
            prev_hash = last_block.block_hash

        block_data = dict()
        block_data.update({
            "height": height,
            "timestamp": datetime.now().isoformat(),
            "miner": miner_username,
            "merkle_root": merkle_root,
            "prev_hash": prev_hash
        })
        block_data["nonce"] = self.__mine_nonce(block_data) if nonce is None else nonce
        block_data["block_hash"] = compute_hash(block_data)

        if not self.check_hash_difficulty(block_data["block_hash"]):
            raise BlockNotMined(height, block_data["block_hash"])

        block_data["miner"] = User.get_or_create(username=miner_username)[0]
        return Block.create(**block_data)

    def __mine_nonce(self, block_data: dict) -> int:
        nonce = 0
        while True:
            block_data["nonce"] = nonce
            block_hash = compute_hash(block_data)
            if self.check_hash_difficulty(block_hash):
                break
            nonce += 1
        return nonce

    def __create_transaction(self, from_username: str | None, to_username: str, amount: Decimal | str | float,
                             description: str = None, timestamp: str = None) -> Transaction:
        amount = Decimal(int(amount))

        if amount <= 0:
            raise BalanceError("Amount must be positive")

        if from_username and self.__balances.get(from_username, Decimal("0")) < amount:
            raise BalanceError("Insufficient balance")

        tx_data = dict()
        tx_data.update({
            "timestamp": datetime.now().isoformat() if timestamp is None else timestamp,
            "from_user": from_username,
            "to_user": to_username,
            "amount": str(amount),
            "description": description,
        })

        tx_data["tx_hash"] = compute_hash(tx_data)
        tx_data["from_user"] = User.get_or_create(username=from_username)[0] if from_username else None
        tx_data["to_user"] = User.get_or_create(username=to_username)[0]
        return Transaction(**tx_data)

    def __record_transaction(self, tx: Transaction):
        tx.save()

        from_username = None if tx.from_user is None else tx.from_user.username
        to_username = tx.to_user.username
        amount = Decimal(tx.amount)
        description = tx.description

        self.__update_balance(from_username, to_username, amount)
        ledger_logger.info(f"Transaction recorded {from_username} -> {to_username}: {amount}, {description}")

    def record_transaction(self, from_username: str | None, to_username: str, amount: Decimal | str | float,
                           description: str = None, timestamp: str = None) -> Transaction:
        tx = self.__create_transaction(from_username, to_username, amount, description, timestamp)
        self.__record_transaction(tx)
        return tx

    def record_deposit(self, from_username: str, amount: Decimal | str | float, description: str = None):
        self.record_transaction(from_username, self.__genesis_username, amount, description)

    def record_gain(self, to_username: str, amount: Decimal | str | float, description: str = None):
        self.record_transaction(self.__genesis_username, to_username, amount, description)

    def get_user_balance(self, username: str) -> Decimal:
        return self.__balances.get(username, 0)

    def get_user_max_balance(self, username: str) -> Decimal:
        return self.__max_balances.get(username, 0)

    def get_all_balances(self):
        return sorted(list(self.__balances.items()), key=lambda item: item[1], reverse=True)

    def get_all_max_balances(self):
        return sorted(list(self.__max_balances.items()), key=lambda item: item[1], reverse=True)

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
                tx.from_user.username if tx.from_user else None,
                tx.to_user.username,
                tx.amount,
                tx.description,
                tx.timestamp
            ])
        file.name = "transactions.csv"
        return file.getvalue()
