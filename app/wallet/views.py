from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404

from .models import Wallet
from .blockchain_service import (
    get_wallet_account,
    get_network_status,
    sync_wallet_registration,
)
from tmc_rpc_client import TMCClientError


@login_required
def wallet_dashboard(request):
    wallet = get_object_or_404(
        Wallet,
        user=request.user
    )

    balance = None
    nonce = None
    network = None
    blockchain_error = None

    try:
        account = sync_wallet_registration(wallet)
        network = get_network_status()      

        if account is not None:
            balance = account["balance_minor"] / 100
            nonce = account["nonce"]

    except TMCClientError:
        blockchain_error = (
            "TMC blokcheýn ulgamy bilen baglanyşyk ýok."
        )

    return render(
        request,
        "wallet/dashboard.html",
        {
            "wallet": wallet,
            "balance": balance,
            "nonce": nonce,
            "network": network,
            "blockchain_error": blockchain_error,
        }
    )
