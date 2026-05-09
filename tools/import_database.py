import csv
import lib.database as database
from lib.database import User, Stats, Transaction
from lib.ledger import Ledger, compute_merkle_root, EMPTY_HASH


def read_csv(path: str):
    with open(path, newline='') as csvfile:
        reader = csv.reader(csvfile, delimiter=',', quotechar='"')
        for row in reader:
            yield row


def process_username(username: str):
    if username == "b":
        return "b"
    return username


user_ids = {
}

if __name__ == '__main__':
    for user_data in read_csv("../data/exported/main_user.csv"):
        user = User.create(
            id=user_ids[user_data[0]],
            username=process_username(user_data[0]),
            daily_prize_time=user_data[1],
            mine_attempt_time=user_data[2],
            galton_background_path=user_data[3]
        )

        print(user)

    for stats_data in read_csv("../data/exported/main_stats.csv"):
        stats = Stats.create(
            user=User.get(username=stats_data[1]),
            prizes=stats_data[2],
            mine=stats_data[3],
            gamble=stats_data[4],
            galton=stats_data[5],
            blackjack_win=stats_data[6],
            blackjack_all=stats_data[7]
        )
        print(stats)

    prev_hash = EMPTY_HASH
    transactions_reader = read_csv("../data/exported/main_transaction.csv")
    for block_data in read_csv("../data/exported/main_block.csv"):
        block_txs: list[Transaction] = []
        transaction = None
        for transaction_data in transactions_reader:
            from_user = database.get_user(process_username(transaction_data[3]))
            to_user = database.get_user(process_username(transaction_data[4]))
            assert to_user is not None
            transaction = Ledger.create_transaction(
                from_user_id=from_user.id if from_user else None,
                to_user_id=to_user.id,
                amount=int(float(transaction_data[5])),
                description=transaction_data[6],
                timestamp=transaction_data[2],
                fee=0
            )
            if transaction_data[1] != block_data[0]:
                break
            block_txs.append(transaction)

        merkle_root = compute_merkle_root([tx.tx_hash for tx in block_txs])
        miner_user = database.get_user(process_username(block_data[2]))
        assert miner_user is not None
        block = Ledger.create_block(
            miner=miner_user,
            merkle_root=merkle_root,
            height=int(block_data[0]),
            prev_hash=prev_hash,
            diff="00",
            base_reward=2000,
            total_fees=0,
            timestamp=block_data[1]
        )
        block.save(force_insert=True)

        for tx in block_txs:
            tx.block = block
            tx.save()
            print(tx)

        if transaction is None:
            print("-" * 30 + "NONE TRANSACTION" + "-" * 30)
            continue
        block_txs = [transaction]
        print(block)
