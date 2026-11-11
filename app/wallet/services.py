from cryptography.hazmat.primitives import serialization

from tmc_transaction import (
    generate_keypair,
    address_from_public_key,
)

from .models import Wallet


def create_wallet(user):    
    private_key, public_key = generate_keypair()
    
    public_key_hex = public_key.hex()
   
    address = address_from_public_key(public_key)
    
    private_key_hex = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    ).hex()
    
    wallet = Wallet.objects.create(
        user=user,
        address=address,
        public_key=public_key_hex,
    )

    return wallet, private_key_hex
