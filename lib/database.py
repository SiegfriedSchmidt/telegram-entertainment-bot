from datetime import datetime, timedelta
from typing import Optional
from lib.config_reader import config
from lib.logger import peewee_logger
from lib.init import database_file_path
from lib.models import StatsType
from lib.storage import storage
from lib.utils.utils import used_today
from peewee import *

db = SqliteDatabase(database_file_path)


class BaseModel(Model):
    class Meta:
        database = db


class User(BaseModel):
    username = CharField(unique=True, primary_key=True)
    daily_prize_time = DateTimeField(default=datetime(1980, 1, 1))
    mine_attempt_time = DateTimeField(default=datetime(1980, 1, 1))


class Stats(BaseModel):
    user = ForeignKeyField(User, unique=True, backref="stats")
    prizes = IntegerField(default=0)
    mine = IntegerField(default=0)
    gamble = IntegerField(default=0)
    galton = IntegerField(default=0)


class Block(BaseModel):
    height = IntegerField(unique=True, primary_key=True)
    timestamp = DateTimeField()
    miner = ForeignKeyField(User, backref='blocks')
    merkle_root = CharField(max_length=64)
    nonce = IntegerField()
    prev_hash = CharField(max_length=64)
    block_hash = CharField(max_length=64, unique=True)

    def __str__(self):
        return f'Block: {self.height}, miner: {self.miner}, nonce: {self.nonce}, hash: {self.block_hash[:16]}...'

    class Meta:
        indexes = (
            (('height',), True),
        )


class Transaction(BaseModel):
    number = AutoField()
    block = ForeignKeyField(Block, null=True, backref='transactions')  # None = pending
    timestamp = DateTimeField()
    from_user = ForeignKeyField(User, null=True, backref='sent')
    to_user = ForeignKeyField(User, backref='received')
    amount = DecimalField(decimal_places=64, constraints=[Check('amount > 0')])
    description = TextField(null=True)
    tx_hash = CharField(max_length=64, unique=True)

    def __str__(self):
        return f'{self.number}. {"pending" if self.block is None else f"block {self.block}"} - {self.from_user} -> {self.to_user}, {self.amount}, {self.description}'

    class Meta:
        indexes = (
            (('block', 'timestamp'), False),
        )


db.connect()
# db.drop_tables([User, Stats, Block, Transaction])
db.create_tables([User, Stats, Block, Transaction])

peewee_logger.info("Connected to database.")
peewee_logger.disabled = True


def is_user_exists(username: str) -> bool:
    return User.get_or_none(username=username) is not None


def get_user_stats(username: str) -> Stats | None:
    user = User.get_or_none(username=username)
    if user is None:
        return None
    return user.stats.first()


def reset_daily_prize_time_for_user(username: str) -> None:
    user: User | None = User.get_or_none(username=username)
    if user is None:
        return

    user.daily_prize_time = datetime(1980, 1, 1)
    user.save()


def get_daily_amount_for_user(username: str) -> int:
    user = User.get_or_none(username=username)
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
        )
        .scalar(as_dict=True)
    )
    return {k: (v or 0) for k, v in totals.items()}


def get_user_blocks_count(username: str) -> int:
    user = User.get_or_none(username=username)
    if user is None:
        return 0

    return user.blocks.count()


def get_total_users_blocks_count(genesis_username: str) -> int:
    genesis_user = User.get_or_none(username=genesis_username)
    if genesis_user is None:
        return -1
    return Block.select().where(Block.miner != genesis_user).count()


def update_user_stats(user_or_name: str | User, stat_type: StatsType, increment: int = 1):
    if isinstance(user_or_name, str):
        user: User = User.get_or_create(username=user_or_name)[0]
    elif isinstance(user_or_name, User):
        user = user_or_name
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

    stats.save()


def is_available_daily_prize(username: str) -> bool:
    user = User.get_or_create(username=username)[0]
    if not used_today(user.daily_prize_time, config.day_start_time):
        user.daily_prize_time = datetime.now()
        update_user_stats(user, StatsType.prizes)
        user.save()
        return True
    return False


def is_unavailable_mine_attempt(username: str) -> int:
    user = User.get_or_create(username=username)[0]
    now = datetime.now()
    delta = timedelta(seconds=storage.mine_block_user_timeout) - (now - user.mine_attempt_time)
    seconds_left = int(delta.total_seconds())
    if seconds_left <= 0:
        user.mine_attempt_time = now
        update_user_stats(user, StatsType.mine)
        user.save()
        return 0
    return seconds_left


def get_user_transactions(username: str, limit: Optional[int] = None) -> list[Transaction]:
    return list(
        Transaction
        .select()
        .where((Transaction.from_user.username == username) | (Transaction.to_user.username == username))
        .order_by(Transaction.number.desc())
        .limit(limit)
    )


def get_transactions(limit: Optional[int] = None, ascending=False) -> list[Transaction]:
    transactions = (
        Transaction
        .select()
        .order_by(Transaction.number.asc() if ascending else Transaction.number.desc())
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


def get_blocks(limit: Optional[int] = None, ascending=False) -> list[Block]:
    return list(
        Block
        .select()
        .order_by(Block.height.asc() if ascending else Block.height.desc())
        .limit(limit)
    )


def get_blocks_count() -> int:
    return Block.select().count()
