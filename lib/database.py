from datetime import datetime, timedelta
from typing import Optional, cast
# noinspection PyUnresolvedReferences
from playhouse.mysql_ext import JSONField
from lib.config_reader import config
from lib.logger import peewee_logger
from lib.init import database_file_path
from lib.models import StatsType
from lib.storage import storage
from lib.utils.general_utils import used_today, from_iso, get_name, clean_username
from peewee import *

db = SqliteDatabase(database_file_path)


class BaseModel(Model):
    class Meta:
        database = db


class User(BaseModel):
    id = IntegerField(unique=True, primary_key=True)
    username = CharField(null=True)
    daily_prize_time = DateTimeField(default=datetime(1980, 1, 1))
    mine_attempt_time = DateTimeField(default=datetime(1980, 1, 1))
    galton_background_path = CharField(max_length=256, null=True)

    def __str__(self):
        return get_name(str(self.username), str(self.id))


class Stats(BaseModel):
    user = ForeignKeyField(User, unique=True, backref="stats")
    prizes = IntegerField(default=0)
    mine = IntegerField(default=0)
    gamble = IntegerField(default=0)
    galton = IntegerField(default=0)
    blackjack_win = IntegerField(default=0)
    blackjack_all = IntegerField(default=0)


class Block(BaseModel):
    height = IntegerField(unique=True, primary_key=True)
    timestamp = DateTimeField()
    miner = ForeignKeyField(User, backref='blocks')
    merkle_root = CharField(max_length=64)
    nonce = IntegerField()
    prev_hash = CharField(max_length=64)
    block_hash = CharField(max_length=64, unique=True)

    extra = JSONField(null=True, default=dict)

    def __str__(self):
        return f'Block: {self.height}, miner: {self.miner}, nonce: {self.nonce}, hash: {self.block_hash[:16]}..., timestamp: {from_iso(str(self.timestamp))}'

    class Meta:
        indexes = (
            (('height',), True),
        )


class Transaction(BaseModel):
    number = AutoField()
    block = ForeignKeyField(Block, null=True, backref='transactions')  # NULL = pending
    timestamp = DateTimeField()
    from_user = ForeignKeyField(User, null=True, backref='sent')  # NULL = coinbase
    to_user = ForeignKeyField(User, backref='received')
    amount = BigIntegerField(constraints=[Check('amount > 0')])
    fee = BigIntegerField(default=0)
    description = TextField(null=True)
    tx_hash = CharField(max_length=64, unique=True)

    def __str__(self):
        return (
            f'{self.number}. {"pending" if self.block is None else f"block {self.block.height}"} - '
            f'{self.from_user if self.from_user else "Coinbase"} -> {self.to_user}, {self.amount}, {self.description}'
        )

    class Meta:
        indexes = (
            (('block', 'timestamp'), False),
        )


db.connect()

# create tables
db.create_tables([User, Stats, Block, Transaction])

peewee_logger.info("Connected to database.")
peewee_logger.disabled = True


def get_user(name_or_id: str | int) -> User | None:
    if isinstance(name_or_id, int) or name_or_id.isdigit():
        return User.get_or_none(id=int(name_or_id))
    else:
        return User.get_or_none(username=clean_username(name_or_id))


def create_user(user_id: int, username: str | None) -> User:
    user = User.get_or_create(id=user_id)[0]
    if user.username != username:
        user.username = username
        user.save()
    return user


def get_user_or_exception(user_id: int) -> User:
    user: User | None = User.get_or_none(id=user_id)
    if user is None:
        raise RuntimeError(f'User {user_id} does not exist!')
    return user


def cast_datetime(dtf: DateTimeField) -> datetime:
    return cast(datetime, cast(object, dtf))  # Ridiculous btw


def get_user_stats(user_or_id: int | User) -> Stats | None:
    if isinstance(user_or_id, int):
        user = User.get_or_none(user_or_id)
    else:
        user = user_or_id

    if user is None:
        return None
    return user.stats.first()


def reset_daily_prize_time_for_user(user_id: int) -> None:
    user: User | None = User.get_or_none(id=user_id)
    if user is None:
        return

    user.daily_prize_time = datetime(1980, 1, 1)
    user.save()


def get_daily_amount_for_user(user_id: int) -> int:
    user = User.get_or_none(id=user_id)
    if user is None:
        return 0

    total = (
        Transaction
        .select(fn.SUM(Transaction.amount).alias('daily_total'))
        .where(
            (Transaction.to_user == user) &
            (Transaction.description.startswith('Daily'))
        )
        .scalar()
    )

    return int(total) if total is not None else 0


def get_galton_background_path(user_id: int) -> str | None:
    user = User.get_or_none(id=user_id)
    if user is None:
        return None
    return user.galton_background_path


def set_galton_background_path(user_id: int, path: str) -> None:
    user: User = get_user_or_exception(user_id)
    user.galton_background_path = path
    user.save()


def get_total_daily_amount() -> int:
    total_all_daily = (
            Transaction
            .select(fn.SUM(Transaction.amount))
            .where(Transaction.description.startswith('Daily'))
            .scalar() or 0
    )

    return int(total_all_daily)


def get_total_stats():
    totals = (
        Stats
        .select(
            fn.SUM(Stats.prizes).alias('prizes'),
            fn.SUM(Stats.mine).alias('mine'),
            fn.SUM(Stats.gamble).alias('gamble'),
            fn.SUM(Stats.galton).alias('galton'),
            fn.SUM(Stats.blackjack_win).alias('blackjack_win'),
            fn.SUM(Stats.blackjack_all).alias('blackjack_all'),
        )
        .scalar(as_dict=True)
    )
    return {k: (v or 0) for k, v in totals.items()}


def get_user_blocks_count(user_id: int) -> int:
    user = User.get_or_none(id=user_id)
    if user is None:
        return 0

    return user.blocks.count()


def get_total_users_blocks_count(genesis_user_id: int) -> int:
    genesis_user = User.get_or_none(id=genesis_user_id)
    if genesis_user is None:
        return -1
    return Block.select().where(Block.miner != genesis_user).count()


def update_user_stats(user_or_id: int | User, stat_type: StatsType, increment: int = 1):
    if isinstance(user_or_id, int):
        user: User = get_user_or_exception(user_or_id)
    elif isinstance(user_or_id, User):
        user = user_or_id
    else:
        raise TypeError("user_or_name must be str or User!")

    stats = Stats.get_or_create(user=user)[0]
    match stat_type:
        case StatsType.prizes:
            stats.prizes += increment
        case StatsType.mine:
            stats.mine += increment
        case StatsType.gamble:
            stats.gamble += increment
        case StatsType.galton:
            stats.galton += increment
        case StatsType.blackjack_win:
            stats.blackjack_win += increment
            stats.blackjack_all += increment
        case StatsType.blackjack_all:
            stats.blackjack_all += increment

    stats.save()


def is_available_daily_prize(user_id: int) -> bool:
    user = get_user_or_exception(user_id)
    if not used_today(cast_datetime(user.daily_prize_time), config.day_start_time):
        user.daily_prize_time = datetime.now()
        update_user_stats(user, StatsType.prizes)
        user.save()
        return True
    return False


def is_unavailable_mine_attempt(user_id: int) -> int:
    user = get_user_or_exception(user_id)
    now = datetime.now()
    delta = timedelta(seconds=storage.mine_block_user_timeout) - (now - cast_datetime(user.mine_attempt_time))
    seconds_left = int(delta.total_seconds())
    if seconds_left <= 0:
        user.mine_attempt_time = now
        update_user_stats(user, StatsType.mine)
        user.save()
        return 0
    return seconds_left


def get_user_transactions(user_id: int, limit: Optional[int] = None) -> list[Transaction]:
    return list(
        Transaction
        .select()
        .where((Transaction.from_user.user_id == user_id) | (Transaction.to_user.user_id == user_id))
        .order_by(Transaction.number.desc())
        .limit(limit)
    )


def get_transactions(offset: Optional[int] = None, limit: Optional[int] = None, ascending=False, biggest=False) -> list[
    Transaction]:
    transactions = (
        Transaction
        .select()
        .order_by(
            Transaction.amount.desc() if biggest else
            (Transaction.number.asc() if ascending else Transaction.number.desc())
        )
        .offset(offset)
        .limit(limit)
    )
    users = User.select()
    return prefetch(transactions, users)


def get_pending_transactions(limit: Optional[int] = None, ascending=False) -> list[Transaction]:
    return list(
        Transaction
        .select()
        .where(Transaction.block.is_null())
        .order_by(Transaction.number.asc() if ascending else Transaction.number.desc())
        .limit(limit)
    )


def delete_pending_transactions() -> int:
    return Transaction.delete().where(Transaction.block.is_null()).execute()


def get_block_transactions(block: Block, limit: Optional[int] = None, ascending=False) -> list[Transaction]:
    return list(
        block.transactions.
        order_by(Transaction.number.asc() if ascending else Transaction.number.desc()).
        limit(limit)
    )


def get_block(height: int) -> Block | None:
    return Block.get_or_none(height=height)


def get_transactions_count() -> int:
    return Transaction.select().count()


def get_user_blocks(user_id: int, offset: Optional[int] = None, limit: Optional[int] = None, ascending=False) -> list[
    Block]:
    return list(
        Block
        .select()
        .where(Block.miner == user_id)
        .order_by(Block.height.asc() if ascending else Block.height.desc())
        .offset(offset)
        .limit(limit)
    )


def get_blocks(offset: Optional[int] = None, limit: Optional[int] = None, ascending=False) -> list[Block]:
    return list(
        Block
        .select()
        .order_by(Block.height.asc() if ascending else Block.height.desc())
        .offset(offset)
        .limit(limit)
    )


def get_blocks_count() -> int:
    return Block.select().count()


if __name__ == '__main__':
    ...
