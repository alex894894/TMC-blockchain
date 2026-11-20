
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction

from .forms import RegistrationForm

import json
import re

from django.db import IntegrityError, transaction

from wallet.models import Wallet
from wallet.blockchain_service import register_signed_wallet_on_blockchain

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
                # Ulanyjyny maglumatlar bazasynda saklaýarys.
                with transaction.atomic():
                    user = form.save()

            except IntegrityError:
                form.add_error(
                    None,
                    "Ulanyjy maglumatlaryny saklamak başartmady."
                )

                return render(
                    request,
                    "accounts/register.html",
                    {"form": form},
                )

            # Täze ulanyjyny ulgama girizýäris.
            login(request, user)

            messages.success(
                request,
                "Hasabyňyz üstünlikli döredildi."
            )

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


@login_required
def wallet_view(request):
    if request.method == "POST":
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

            if not re.fullmatch(r"[0-9a-f]{64}", wallet_public_key):
                raise ValueError("Açyk açaryň formaty nädogry.")

            if not verify_transaction(transaction_data):
                raise ValueError("Tranzaksiýanyň goly nädogry.")

            expected_address = address_from_public_key(
                bytes.fromhex(wallet_public_key)
            )

            if transaction_data.get("address") != expected_address:
                raise ValueError("Tranzaksiýa salgysy gabat gelenok.")

            if transaction_data.get("public_key") != wallet_public_key:
                raise ValueError("Açyk açar gabat gelenok.")

            if wallet_address != expected_address:
                raise ValueError("Gapjyk salgysy nädogry.")

        except (ValueError, TypeError, json.JSONDecodeError):
            messages.error(
                request,
                "Gapjyk maglumatlaryny ýa-da goluny barlap bolmady."
            )
            return redirect("wallet")

        # Ulanyjynyň öňki gapjygyny barlaýarys.
        try:
            with transaction.atomic():
                wallet = Wallet.objects.select_for_update().filter(
                    user=request.user
                ).first()

                if wallet is not None:
                    if wallet.address and wallet.address != expected_address:
                        messages.error(
                            request,
                            "Bu ulanyja eýýäm başga gapjyk birikdirilen."
                        )
                        return redirect("wallet")

                    if (
                        wallet.public_key
                        and wallet.public_key != wallet_public_key
                    ):
                        messages.error(
                            request,
                            "Gapjygyň açyk açary gabat gelenok."
                        )
                        return redirect("wallet")

                    if (
                        wallet.registration_status
                        == Wallet.RegistrationStatus.REGISTERED
                    ):
                        messages.info(
                            request,
                            "Bu gapjyk eýýäm TMC torunda hasaba alnan."
                        )
                        return redirect("wallet")

                    wallet.address = expected_address
                    wallet.public_key = wallet_public_key

                    wallet.save(
                        update_fields=["address", "public_key"]
                    )

                else:
                    wallet = Wallet.objects.create(
                        user=request.user,
                        address=expected_address,
                        public_key=wallet_public_key,
                        registration_status=(
                            Wallet.RegistrationStatus.PENDING
                        ),
                    )

        except IntegrityError:
            messages.error(
                request,
                "Bu gapjyk salgysy başga ulanyja degişli."
            )
            return redirect("wallet")

        # Gol çekilen tranzaksiýany TMC toruna iberýäris.
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
                    "Hasaba alyş tranzaksiýasy TMC toruna iberildi."
                )

            else:
                wallet.registration_status = (
                    Wallet.RegistrationStatus.FAILED
                )

                messages.error(
                    request,
                    "Tranzaksiýa TMC tory tarapyndan kabul edilmedi."
                )

            wallet.save(
                update_fields=[
                    "registration_status",
                    "registration_tx_hash",
                ]
            )

        except TMCClientError:
            wallet.registration_status = (
                Wallet.RegistrationStatus.PENDING
            )
            wallet.save(update_fields=["registration_status"])

            messages.warning(
                request,
                "TMC toruna birikmek başartmady. "
                "Soňra gaýtadan synanyşyň."
            )

        return redirect("wallet")

    # Ulanyjynyň gapjyk maglumatlaryny görkezýäris.
    wallet = Wallet.objects.filter(user=request.user).first()

    return render(
        request,
        "accounts/wallet.html",
        {"wallet": wallet},
    )

