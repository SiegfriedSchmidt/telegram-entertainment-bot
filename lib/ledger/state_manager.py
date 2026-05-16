from contextlib import contextmanager
from lib.database import Transaction, User
from lib.ledger.validator import BalanceError
import lib.database as database


class FreezeHandle:
    def __init__(self, state: 'StateManager', user_id: int, amount: int):
        self._state = state
        self.user_id = user_id
        self.amount = amount
        self._released = False

    def release(self) -> None:
        if not self._released:
            self._state.release_handle(self)
            self._released = True

    def __del__(self):
        self.release()


class StateManager:
    def __init__(self):
        self.__balances: dict[int, int] = dict()
        self.__max_balances: dict[int, int] = dict()
        self.__total_gain: dict[int, int] = dict()

    def clear(self):
        self.__balances.clear()
        self.__max_balances.clear()
        self.__total_gain.clear()

    def __update_balance(self, tx: Transaction) -> None:
        if tx.from_user:
            deduction = tx.amount + tx.fee
            available = self.__balances.get(tx.from_user.id, 0)
            if available < deduction:
                raise BalanceError(f"Insufficient balance! {available} < {deduction}")
            self.__balances[tx.from_user.id] = available - deduction

        if tx.to_user.id not in self.__balances:
            self.__balances[tx.to_user.id] = tx.amount
            self.__total_gain[tx.to_user.id] = tx.amount
            self.__max_balances[tx.to_user.id] = self.__balances[tx.to_user.id]
        else:
            self.__balances[tx.to_user.id] += tx.amount
            self.__total_gain[tx.to_user.id] += tx.amount
            self.__max_balances[tx.to_user.id] = max(self.__max_balances[tx.to_user.id], self.__balances[tx.to_user.id])

    def apply_tx(self, val: Transaction | list[Transaction], revert=False) -> None:
        if isinstance(val, Transaction):
            txs = [val]
        else:
            txs = val

        if revert:
            for tx in txs:
                self.__balances[tx.from_user.id] += tx.fee
                self.__update_balance(Transaction(from_user=tx.to_user, to_user=tx.from_user, amount=tx.amount))
        else:
            for tx in txs:
                self.__update_balance(tx)

    def freeze(self, user_id: int, amount: int) -> FreezeHandle:
        if amount <= 0:
            return FreezeHandle(self, user_id, 0)

        available = self.get_user_balance(user_id)
        if available < amount:
            raise BalanceError(f"Insufficient balance! {available} < {amount}")

        self.__balances[user_id] = available - amount
        return FreezeHandle(self, user_id, amount)

    def release_handle(self, handle: FreezeHandle) -> None:
        self.__balances[handle.user_id] = self.get_user_balance(handle.user_id) + handle.amount

    @contextmanager
    def frozen_balance(self, user_id: int, amount: int):
        handle = self.freeze(user_id, amount)
        try:
            yield handle
        except Exception:
            handle.release()
            raise
        finally:
            handle.release()

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
