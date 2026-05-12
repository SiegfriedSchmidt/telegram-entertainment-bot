from typing import BinaryIO

from lib.database import Transaction
from lib.ledger.chain_manager import ChainManager
from lib.ledger.state_manager import StateManager
from lib.ledger.tx_manager import TxManager, MONEY_TYPE
from lib.ledger.validator import LedgerError


class Ledger:
    def __init__(self, base_block_reward: int, difficulty=2):
        self._state = StateManager()
        self._tx = TxManager(self._state)
        self._chain = ChainManager(
            self._state,
            self._tx,
            base_block_reward,
            difficulty
        )

        self._genesis_id: int | None = None

    @property
    def fee_percentage(self) -> int:
        return self._tx.fee_percentage

    @fee_percentage.setter
    def fee_percentage(self, val: int) -> None:
        self._tx.set_fee_percentage(val)

    @property
    def genesis_id(self):
        return self._genesis_id

    @genesis_id.setter
    def genesis_id(self, val: int) -> None:
        if self._genesis_id is not None:
            raise LedgerError("Genesis ID is immutable")
        self._genesis_id = val
        self._chain.set_genesis_id(val)
        self._tx.set_genesis_id(val)

    def get_user_balance(self, user_id: int):
        return self._state.get_user_balance(user_id)

    def get_user_max_balance(self, user_id: int):
        return self._state.get_user_max_balance(user_id)

    def get_user_total_gain(self, user_id: int):
        return self._state.get_user_total_gain(user_id)

    def get_all_balances(self):
        return self._state.get_all_balances()

    def get_all_max_balances(self):
        return self._state.get_all_max_balances()

    def get_all_total_gains(self):
        return self._state.get_all_total_gains()

    def load_and_verify_chain(self, genesis_username: str):
        return self._chain.load_and_verify_chain(genesis_username)

    def mine_block(self, miner_user_id: int = None, nonce: int = None):
        return self._chain.mine_block(miner_user_id, nonce)

    def record_transaction(self, from_user_id: int, to_user_id: int, amount: MONEY_TYPE, description: str):
        return self._tx.record_transaction(from_user_id, to_user_id, amount, description)

    def record_deposit(self, from_user_id: int, amount: MONEY_TYPE, description: str):
        return self._tx.record_deposit(from_user_id, amount, description)

    def record_gain(self, to_user_id: int, amount: MONEY_TYPE, description: str):
        return self._tx.record_gain(to_user_id, amount, description)

    def delete_pending_transactions(self):
        return self._tx.delete_pending_transactions()

    def revert_tx(self, tx: Transaction):
        return self._tx.revert_tx(tx)

    def import_transactions_csv(self, file: BinaryIO):
        return self._tx.import_transactions_csv(file)

    def export_transactions_csv(self):
        return self._tx.export_transactions_csv()
