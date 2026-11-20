
import json

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction

from .forms import RegistrationForm

from wallet.blockchain_service import (
    register_signed_wallet_on_blockchain,
)
from wallet.models import Wallet

from tmc_transaction import (
    verify_transaction,
    address_from_public_key,
)

from tmc_rpc_client import TMCClientError


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = RegistrationForm(request.POST)

        if form.is_valid():
            try:
                # Brauzerden gelen gol çekilen tranzaksiýany alýarys.
                transaction_data = json.loads(
                    request.POST.get("wallet_transaction", "")
                )

                wallet_address = request.POST.get("wallet_address", "")
                wallet_public_key = request.POST.get("wallet_public_key", "")

                if not isinstance(transaction_data, dict):
                    raise ValueError("Nädogry tranzaksiýa maglumatlary.")

                if transaction_data.get("type") != "register_account":
                    raise ValueError("Tranzaksiýanyň görnüşi nädogry.")

                if not verify_transaction(transaction_data):
                    raise ValueError("Tranzaksiýanyň goly nädogry.")

                public_key_bytes = bytes.fromhex(wallet_public_key)

                expected_address = address_from_public_key(
                    public_key_bytes
                )

                if transaction_data.get("address") != expected_address:
                    raise ValueError("Gapjyk salgysy gabat gelenok.")

                if transaction_data.get("public_key") != wallet_public_key:
                    raise ValueError("Açyk açar gabat gelenok.")

                if wallet_address != expected_address:
                    raise ValueError("Gapjyk salgysy nädogry.")

            except (ValueError, TypeError, json.JSONDecodeError):
                form.add_error(
                    None,
                    "Gapjyk maglumatlaryny ýa-da goluny barlap bolmady."
                )

                return render(
                    request,
                    "accounts/register.html",
                    {"form": form},
                )

            # Ulanyjy we gapjyk maglumatlaryny atomar ýagdaýda saklaýarys.
            try:
                with transaction.atomic():
                    user = form.save()

                    wallet = Wallet.objects.create(
                        user=user,
                        address=expected_address,
                        public_key=wallet_public_key,
                        registration_status=(
                            Wallet.RegistrationStatus.PENDING
                        ),
                    )

            except IntegrityError:
                form.add_error(
                    None,
                    "Bu gapjyk salgysy ýa-da ulanyjy eýýäm hasaba alnan."
                )

                return render(
                    request,
                    "accounts/register.html",
                    {"form": form},
                )

            # Tranzaksiýany TMC toruna iberýäris.
            try:
                result = register_signed_wallet_on_blockchain(
                    transaction_data
                )

                wallet.registration_tx_hash = result["hash"]

                if result["code"] == 0:
                    wallet.registration_status = (
                        Wallet.RegistrationStatus.SUBMITTED
                    )

                    messages.success(
                        request,
                        "Gapjyk hasaba almak üçin TMC toruna iberildi."
                    )

                else:
                    wallet.registration_status = (
                        Wallet.RegistrationStatus.FAILED
                    )

                    messages.error(
                        request,
                        "Tranzaksiýa tor tarapyndan kabul edilmedi."
                    )

                wallet.save(
                    update_fields=[
                        "registration_status",
                        "registration_tx_hash",
                    ]
                )

            except TMCClientError:
                # Tor elýeterli bolmasa, gapjyk PENDING ýagdaýynda galýar.
                messages.warning(
                    request,
                    "Gapjyk döredildi, ýöne TMC toruna birikmek başartmady. "
                    "Hasaba almak soňra gaýtadan synanyşylar."
                )

            login(request, user)

            return redirect("dashboard")

    else:
        form = RegistrationForm()

    return render(
        request,
        "accounts/register.html",
        {"form": form},
    )


@login_required
def dashboard_view(request):
    return render(
        request,
        "accounts/dashboard.html",
    )
