
import hashlib
import json

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from tmc_constants import MAX_INTEGER

DOMAIN = b"TMC-TRANSACTION-V1\x00"


def generate_keypair():
    """Create an Ed25519 private/public key pair."""
    private_key = Ed25519PrivateKey.generate()

    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    return private_key, public_key


def address_from_public_key(public_key):
    """Derive a prototype TMC address from a public key."""
    if not isinstance(public_key, bytes) or len(public_key) != 32:
        raise ValueError("Invalid Ed25519 public key")

    digest = hashlib.sha256(public_key).hexdigest()
    return "tmc_" + digest[:40]


def canonical_json(data):
    """Serialize transaction fields deterministically."""
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def transaction_signing_bytes(transaction):
    """Return exactly the bytes that must be signed."""
    fields = {
        "type": transaction["type"],
        "sender": transaction["sender"],
        "recipient": transaction["recipient"],
        "amount_minor": transaction["amount_minor"],
        "nonce": transaction["nonce"],
        "public_key": transaction["public_key"],
    }

    return DOMAIN + canonical_json(fields)


def create_signed_transaction(
    private_key,
    recipient,
    amount_minor,
    nonce,
):
    """Create and sign a TMC transfer transaction."""
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("Invalid private key")

    if not isinstance(recipient, str) or not recipient.strip():
        raise ValueError("Recipient must not be empty")

    if type(amount_minor) is not int or not 0 < amount_minor <= MAX_INTEGER:
        raise ValueError("Töleg möçberi nädogry.")

    if type(nonce) is not int or not 0 < nonce <= MAX_INTEGER:
        raise ValueError("Nonce bahasy nädogry.")

    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    transaction = {
        "type": "transfer",
        "sender": address_from_public_key(public_key),
        "recipient": recipient,
        "amount_minor": amount_minor,
        "nonce": nonce,
        "public_key": public_key.hex(),
    }

    signature = private_key.sign(
        transaction_signing_bytes(transaction)
    )

    transaction["signature"] = signature.hex()
    return transaction


def verify_transaction(transaction):
    """Validate transaction structure, sender address and signature."""
    try:
        if not isinstance(transaction, dict):
            return False

        expected_fields = {
            "type",
            "sender",
            "recipient",
            "amount_minor",
            "nonce",
            "public_key",
            "signature",
        }

        if set(transaction.keys()) != expected_fields:
            return False

        if transaction["type"] != "transfer":
            return False

        if not isinstance(transaction["sender"], str):
            return False

        if not isinstance(transaction["recipient"], str):
            return False

        if not transaction["sender"].strip():
            return False

        if not transaction["recipient"].strip():
            return False

        if type(transaction["amount_minor"]) is not int:
            return False

        if not 0 < transaction["amount_minor"] <= MAX_INTEGER:
            return False

        if type(transaction["nonce"]) is not int:
            return False

        if not 0 < transaction["nonce"] <= MAX_INTEGER:
            return False

        if not isinstance(transaction["public_key"], str):
            return False

        if not isinstance(transaction["signature"], str):
            return False

        public_key_bytes = bytes.fromhex(transaction["public_key"])
        signature_bytes = bytes.fromhex(transaction["signature"])

        if len(public_key_bytes) != 32:
            return False

        if len(signature_bytes) != 64:
            return False

        # Açaryň we goluň hexadecimal görnüşini barlamak.
        if transaction["public_key"] != public_key_bytes.hex():
            return False

        if transaction["signature"] != signature_bytes.hex():
            return False

        expected_sender = address_from_public_key(public_key_bytes)

        if transaction["sender"] != expected_sender:
            return False

        public_key = Ed25519PublicKey.from_public_bytes(
            public_key_bytes
        )

        public_key.verify(
            signature_bytes,
            transaction_signing_bytes(transaction),
        )

        return True

    except (
        ValueError,
        TypeError,
        KeyError,
        InvalidSignature,
    ):
        return False


def transaction_id(transaction):
    """Calculate an identifier for a valid signed transaction."""
    if not verify_transaction(transaction):
        raise ValueError("Cannot identify an invalid transaction")

    signature = bytes.fromhex(transaction["signature"])
    return hashlib.sha256(
        transaction_signing_bytes(transaction) + signature
    ).hexdigest()


def apply_signed_transfer(storage, transaction):
    if not verify_transaction(transaction):
        raise ValueError("Invalid transaction signature")

    sender_account = storage.get_account(
        transaction["sender"]
    )

    if sender_account is None:
        raise ValueError("Sender account does not exist")

    if sender_account["public_key"] != transaction["public_key"]:
        raise ValueError(
            "Public key is not registered to sender"
        )

    return storage.transfer(
        sender=transaction["sender"],
        recipient=transaction["recipient"],
        amount_minor=transaction["amount_minor"],
        nonce=transaction["nonce"],
    )


def encode_transaction(transaction):
    """Convert a transaction dictionary into canonical JSON bytes."""
    if not isinstance(transaction, dict):
        raise ValueError("Transaction must be a dictionary")

    return canonical_json(transaction)


def decode_transaction(raw):
    """Decode and validate the canonical transaction representation."""
    if not isinstance(raw, bytes):
        raise ValueError("Transaction data must be bytes")

    if not raw or len(raw) > 16_384:
        raise ValueError("Invalid transaction size")

    try:
        transaction = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("Invalid transaction JSON") from None

    if not isinstance(transaction, dict):
        raise ValueError("Transaction must be a JSON object")

    # Require one canonical byte representation for each transaction.
    if encode_transaction(transaction) != raw:
        raise ValueError("Transaction JSON is not canonical")

    if not verify_transaction(transaction):
        raise ValueError("Invalid transaction signature")

    return transaction


def apply_block_transactions(storage, transactions):
    """Validate and atomically apply a block's transfers."""
    if not isinstance(transactions, list):
        raise ValueError("Transactions must be a list")

    transfers = []

    # Validate every signature before changing account balances.
    for transaction in transactions:
        if not verify_transaction(transaction):
            raise ValueError("Invalid transaction signature")

        sender_account = storage.get_account(
            transaction["sender"]
        )

        if sender_account is None:
            raise ValueError("Sender account does not exist")

        if sender_account["public_key"] != transaction["public_key"]:
            raise ValueError(
                "Public key is not registered to sender"
            )

        transfers.append({
            "sender": transaction["sender"],
            "recipient": transaction["recipient"],
            "amount_minor": transaction["amount_minor"],
            "nonce": transaction["nonce"],
        })

    return storage.transfer_batch(transfers)
