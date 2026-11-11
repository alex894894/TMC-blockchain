from django.contrib import admin
from .models import Wallet


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "address",
        "created_at",
    )

    search_fields = (
        "user__username",
        "address",
    )

    readonly_fields = (
        "created_at",
    )
