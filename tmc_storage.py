
import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
DATA_DIR = PROJECT_DIR / "data"
DB_PATH = DATA_DIR / "tmc.db"


class TMCStorage:
    def __init__(self, db_path=DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        self.init_db()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row

        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def init_db(self):
        with self.connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    address TEXT PRIMARY KEY,
                    balance_minor INTEGER NOT NULL
                        CHECK (balance_minor >= 0),
                    nonce INTEGER NOT NULL DEFAULT 0
                        CHECK (nonce >= 0),
                    public_key TEXT
                )
            """)
            connection.execute("""
                CREATE TABLE IF NOT EXISTS chain_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    height INTEGER NOT NULL DEFAULT 0,
                    app_hash TEXT NOT NULL DEFAULT ''
                )
            """)

            connection.execute("""
                INSERT OR IGNORE INTO chain_state (
                    id,
                    height,
                    app_hash
                )
                VALUES (1, 0, '')
            """)

            # Check the existing database schema.
            columns = {
                row["name"]
                for row in connection.execute(
                    "PRAGMA table_info(accounts)"
                ).fetchall()
            }

            # Add public_key to databases created by an older version.
            if "public_key" not in columns:
                connection.execute(
                    """
                    ALTER TABLE accounts
                    ADD COLUMN public_key TEXT
                    """
                )

    def register_account(
        self,
        public_key,
        initial_balance_minor=0,
    ):
        if not isinstance(public_key, bytes) or len(public_key) != 32:
            raise ValueError("Invalid Ed25519 public key")

        address = (
            "tmc_"
            + hashlib.sha256(public_key).hexdigest()[:40]
        )

        self.create_account(
            address=address,
            balance_minor=initial_balance_minor,
            public_key=public_key.hex(),
        )

        return address

    def create_account(
        self,
        address,
        balance_minor=0,
        public_key=None,
    ):
        if not isinstance(address, str) or not address.strip():
            raise ValueError("Address must not be empty")

        if type(balance_minor) is not int or balance_minor < 0:
            raise ValueError(
                "Balance must be a non-negative integer"
            )

        if public_key is not None:
            if not isinstance(public_key, str):
                raise ValueError("Invalid public key")

            try:
                key_bytes = bytes.fromhex(public_key)
            except ValueError:
                raise ValueError("Invalid public key") from None

            if len(key_bytes) != 32:
                raise ValueError("Invalid Ed25519 public key")

            expected_address = (
                "tmc_"
                + hashlib.sha256(key_bytes).hexdigest()[:40]
            )

            if address != expected_address:
                raise ValueError(
                    "Public key does not match address"
                )

        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO accounts (
                    address,
                    balance_minor,
                    nonce,
                    public_key
                )
                VALUES (?, ?, 0, ?)
                """,
                (address, balance_minor, public_key),
            )

    def get_account(self, address):
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT
                    address,
                    balance_minor,
                    nonce,
                    public_key
                FROM accounts
                WHERE address = ?
                """,
                (address,),
            ).fetchone()

        if row is None:
            return None

        return dict(row)

    def transfer(
        self,
        sender,
        recipient,
        amount_minor,
        nonce,
    ):
        if not isinstance(sender, str) or not sender.strip():
            raise ValueError("Sender address must not be empty")

        if not isinstance(recipient, str) or not recipient.strip():
            raise ValueError("Recipient address must not be empty")

        if sender == recipient:
            raise ValueError("Cannot transfer to the same account")

        if type(amount_minor) is not int or amount_minor <= 0:
            raise ValueError("Amount must be a positive integer")

        if type(nonce) is not int or nonce <= 0:
            raise ValueError("Nonce must be a positive integer")

        with self.connect() as connection:
            sender_account = connection.execute(
                """
                SELECT balance_minor, nonce
                FROM accounts
                WHERE address = ?
                """,
                (sender,),
            ).fetchone()

            recipient_account = connection.execute(
                """
                SELECT balance_minor
                FROM accounts
                WHERE address = ?
                """,
                (recipient,),
            ).fetchone()

            if sender_account is None:
                raise ValueError("Sender account does not exist")

            if recipient_account is None:
                raise ValueError("Recipient account does not exist")

            if nonce != sender_account["nonce"] + 1:
                raise ValueError("Invalid nonce")

            if sender_account["balance_minor"] < amount_minor:
                raise ValueError("Insufficient balance")

            connection.execute(
                """
                UPDATE accounts
                SET balance_minor = balance_minor - ?,
                    nonce = ?
                WHERE address = ?
                """,
                (amount_minor, nonce, sender),
            )

            connection.execute(
                """
                UPDATE accounts
                SET balance_minor = balance_minor + ?
                WHERE address = ?
                """,
                (amount_minor, recipient),
            )

        return {
            "sender": sender,
            "recipient": recipient,
            "amount_minor": amount_minor,
            "nonce": nonce,
            "status": "success",
        }
    
    
    def transfer_batch(self, transfers):
        """Apply multiple transfers in one SQLite transaction."""
        if not isinstance(transfers, list):
            raise ValueError("Transfers must be a list")

        results = []

        with self.connect() as connection:
            for transfer in transfers:
                sender = transfer["sender"]
                recipient = transfer["recipient"]
                amount = transfer["amount_minor"]
                nonce = transfer["nonce"]

                if not isinstance(sender, str) or not sender.strip():
                    raise ValueError("Sender address must not be empty")

                if not isinstance(recipient, str) or not recipient.strip():
                    raise ValueError("Recipient address must not be empty")

                if sender == recipient:
                    raise ValueError("Cannot transfer to the same account")

                if type(amount) is not int or amount <= 0:
                    raise ValueError("Amount must be a positive integer")

                if type(nonce) is not int or nonce <= 0:
                    raise ValueError("Nonce must be a positive integer")

                sender_account = connection.execute(
                    """
                    SELECT balance_minor, nonce
                    FROM accounts
                    WHERE address = ?
                    """,
                    (sender,),
                ).fetchone()

                recipient_account = connection.execute(
                    """
                    SELECT balance_minor
                    FROM accounts
                    WHERE address = ?
                    """,
                    (recipient,),
                ).fetchone()

                if sender_account is None:
                    raise ValueError("Sender account does not exist")

                if recipient_account is None:
                    raise ValueError("Recipient account does not exist")

                if nonce != sender_account["nonce"] + 1:
                    raise ValueError("Invalid nonce")

                if sender_account["balance_minor"] < amount:
                    raise ValueError("Insufficient balance")

                connection.execute(
                    """
                    UPDATE accounts
                    SET balance_minor = balance_minor - ?,
                        nonce = ?
                    WHERE address = ?
                    """,
                    (amount, nonce, sender),
                )

                connection.execute(
                    """
                    UPDATE accounts
                    SET balance_minor = balance_minor + ?
                    WHERE address = ?
                    """,
                    (amount, recipient),
                )

                results.append({
                    "sender": sender,
                    "recipient": recipient,
                    "amount_minor": amount,
                    "nonce": nonce,
                    "status": "success",
                })

        return results

    def get_all_accounts(self):
        with self.connect() as connection:
            rows = connection.execute("""
                SELECT
                    address,
                    balance_minor,
                    nonce,
                    public_key
                FROM accounts
                ORDER BY address
            """).fetchall()

        return {
            row["address"]: dict(row)
            for row in rows
        }

    def get_chain_state(self):
        with self.connect() as connection:
            row = connection.execute("""
                SELECT height, app_hash
                FROM chain_state
                WHERE id = 1
            """).fetchone()

        return {
            "height": row["height"],
            "app_hash": row["app_hash"],
        }

    def save_committed_state(
        self,
        accounts,
        height,
        app_hash,
    ):
        if type(height) is not int or height < 0:
            raise ValueError("Blok beýikligi nädogry.")

        if not isinstance(app_hash, str):
            raise ValueError("Blok hash-y nädogry.")

        with self.connect() as connection:
            connection.execute("DELETE FROM accounts")

            connection.executemany("""
                INSERT INTO accounts (
                    address,
                    balance_minor,
                    nonce,
                    public_key
                )
                VALUES (?, ?, ?, ?)
            """, [
                (
                    address,
                    account["balance_minor"],
                    account["nonce"],
                    account["public_key"],
                )
                for address, account in sorted(accounts.items())
            ])

            connection.execute("""
                UPDATE chain_state
                SET height = ?, app_hash = ?
                WHERE id = 1
            """, (height, app_hash))