
from .models import Wallet
from tmc_rpc_client import TMCRPCClient, TMCClientError

from tmc_transaction import (
    verify_transaction,
)


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


def register_signed_wallet_on_blockchain(transaction):
    """
    Brauzerde gol çekilen tranzaksiýany barlap,
    TMC toruna ibermek.
    """

    if not isinstance(transaction, dict):
        raise ValueError("Nädogry tranzaksiýa maglumatlary.")

    if transaction.get("type") != "register_account":
        raise ValueError("Tranzaksiýanyň görnüşi nädogry.")

    if not verify_transaction(transaction):
        raise ValueError("Tranzaksiýanyň goly nädogry.")

    return _client.broadcast_transaction(transaction)


def sync_wallet_registration(wallet):
    """
    Gapjygyň TMC blokcheýninde hasaba alnandygyny barlamak.
    """
    if wallet.registration_status == Wallet.RegistrationStatus.REGISTERED:
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
