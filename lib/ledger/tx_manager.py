import csv
import math
from lib.ledger.helpers import compute_hash
from lib.ledger.state_manager import StateManager
from lib.ledger.validator import BalanceError
from io import StringIO
from typing import BinaryIO
from datetime import datetime
from lib.database import db, Transaction
from lib.logger import ledger_logger
import lib.database as database

MONEY_TYPE = int | str | float


class TxManager:
    def __init__(self, state: StateManager):
        self._state = state
        self.fee_percentage = 0
        self.genesis_id = 0

    def set_genesis_id(self, genesis_id: int) -> None:
        self.genesis_id = genesis_id

    def set_fee_percentage(self, fee_percentage: int) -> None:
        self.fee_percentage = fee_percentage

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

    def save_tx(self, tx: Transaction):
        self._state.apply_tx(tx)
        ledger_logger.info(
            f"Transaction recorded {tx.from_user} -> {tx.to_user}: {tx.amount}, fee: {tx.fee}, {tx.description}"
        )
        tx.save()

    def calc_fee(self, amount: MONEY_TYPE, deduct_fee=True) -> tuple[int, int]:
        amount = int(amount)
        if deduct_fee:
            full_amount = amount
            amount = int(int(full_amount) / (1 + self.fee_percentage))
            fee = full_amount - amount
        else:
            fee = int(math.ceil(int(amount) * self.fee_percentage))
        return amount, fee

    def record_transaction(self, from_user_id: int, to_user_id: int, amount: MONEY_TYPE,
                           description: str = None, timestamp: str = None, fee: MONEY_TYPE = None,
                           deduct_fee=False) -> Transaction:
        if fee is None:
            amount, fee = self.calc_fee(amount, deduct_fee)

        tx = self.create_transaction(from_user_id, to_user_id, amount, description, timestamp, fee)
        self.save_tx(tx)
        return tx

    def record_deposit(self, from_user_id: int, amount: MONEY_TYPE, description: str = None):
        self.record_transaction(from_user_id, self.genesis_id, amount, description, deduct_fee=True)

    def record_gain(self, to_user_id: int, amount: MONEY_TYPE, description: str = None):
        self.record_transaction(self.genesis_id, to_user_id, amount, description, deduct_fee=True)

    def delete_pending_transactions(self) -> int:
        self._state.apply_tx(database.get_pending_transactions(ascending=False), revert=True)
        return database.delete_pending_transactions()

    def revert_tx(self, tx: Transaction):
        self._state.apply_tx(tx, revert=True)
        tx.delete_instance()

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
