from tmc_transaction import verify_transaction, address_from_public_key

transaction = {
    "type": "register_account",
    "address": "tmc_897c19a1fa120751c7799869b0e7f0e79febfff9",
    "public_key": "79f9b32ee4e4818f3ce6085f32c603490233567ecb11c0d0db5d4774175af10e",
    "signature": "e8dff542a9bee24268be2f48bec4715b6cad27644661c1aef068ca20bb26d182e637ee128b42830e254ce972cef4aa6625057024e801c04ad1342da94a6bfd0c",
}

print("Address matches:", address_from_public_key(bytes.fromhex(transaction["public_key"])) == transaction["address"])
print("Signature valid:", verify_transaction(transaction))
