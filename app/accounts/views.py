from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required

from .forms import RegistrationForm

from wallet.services import create_wallet
from wallet.blockchain_service import register_wallet_on_blockchain
from wallet.models import Wallet

from tmc_rpc_client import TMCClientError


def register_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = RegistrationForm(request.POST)

        if form.is_valid():
            user = form.save()

            try:
                wallet, private_key = create_wallet(user)

            except Exception:
                user.delete()
                raise

            # Hususy açary wagtlaýyn sessiýada saklamak
            request.session["new_wallet_private_key"] = private_key

            try:
                result = register_wallet_on_blockchain(private_key)

                if result["code"] == 0:
                    wallet.registration_status = (
                        Wallet.RegistrationStatus.SUBMITTED
                    )
                    wallet.registration_tx_hash = result["hash"]
                    wallet.save(
                        update_fields=[
                            "registration_status",
                            "registration_tx_hash",
                        ]
                    )

                    messages.success(
                        request,
                        "Gapjyk hasaba almak üçin tora iberildi."
                    )

                else:
                    wallet.registration_status = (
                        Wallet.RegistrationStatus.FAILED
                    )
                    wallet.registration_tx_hash = result["hash"]
                    wallet.save(
                        update_fields=[
                            "registration_status",
                            "registration_tx_hash",
                        ]
                    )

                    messages.error(
                        request,
                        "Tranzaksiýa tor tarapyndan kabul edilmedi."
                    )

            except TMCClientError:
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
