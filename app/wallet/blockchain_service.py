from tmc_rpc_client import TMCRPCClient, TMCClientError
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from tmc_transaction import create_signed_registration_transaction


# CometBFT RPC klienti
_client = TMCRPCClient(
    rpc_url="http://127.0.0.1:26657",
    timeout=5,
)


def get_wallet_account(address):
    """
    TMC blokcheýninden gapjyk maglumatlaryny almak.
    """
    return _client.get_account(address)


def get_wallet_balance(address):
    """
    TMC gapjygynyň balansyny almak.
    """
    account = get_wallet_account(address)

    if account is None:
        return None

    return account["balance_minor"]


def get_network_status():
    """
    CometBFT torunyň ýagdaýyny almak.
    """
    return _client.get_status()


def get_chain_state():
    """
    TMC blokcheýniniň umumy ýagdaýyny almak.
    """
    return _client.get_chain_state()

def register_wallet_on_blockchain(private_key_hex):
    """
    TMC gapjygyny blokcheýn ulgamynda hasaba almak.
    """
    try:
        private_key_bytes = bytes.fromhex(private_key_hex)

        private_key = Ed25519PrivateKey.from_private_bytes(
            private_key_bytes
        )

        transaction = create_signed_registration_transaction(
            private_key
        )

        return _client.broadcast_transaction(transaction)

    except (ValueError, TMCClientError):
        raise
def sync_wallet_registration(wallet):
    """
    Gapjygyň TMC blokcheýninde hasaba alnandygyny barlamak.
    """
    if wallet.registration_status == "registered":
        return get_wallet_account(wallet.address)

    account = get_wallet_account(wallet.address)

    if account is None:
        return None

    # Hasap salgysynyň degişli açara degişlidigini barlamak
    if account.get("public_key") != wallet.public_key:
        raise TMCClientError(
            "Blokcheýndäki açar gapjyk maglumatlaryna gabat gelenok."
        )

    wallet.registration_status = Wallet.RegistrationStatus.REGISTERED
    wallet.save(update_fields=["registration_status"])

    return account