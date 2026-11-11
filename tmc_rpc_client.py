import base64
import hashlib
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from tmc_transaction import encode_transaction


class TMCClientError(Exception):
    """TMC RPC клиентинде ýüze çykýan ýalňyşlyk."""


class TMCRPCClient:
    def __init__(
        self,
        rpc_url="http://127.0.0.1:26657",
        timeout=10,
    ):
        self.rpc_url = rpc_url.rstrip("/")
        self.timeout = timeout

    def _request(self, endpoint, params=None):
        url = f"{self.rpc_url}/{endpoint}"

        if params:
            url += "?" + urlencode(params)

        request = Request(
            url,
            headers={"Accept": "application/json"},
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))

        except (HTTPError, URLError, TimeoutError) as exc:
            raise TMCClientError(
                f"CometBFT RPC bilen baglanyşyk şowsuz: {exc}"
            ) from exc

        except (ValueError, UnicodeDecodeError) as exc:
            raise TMCClientError(
                "RPC jogaby nädogry formatda."
            ) from exc

        if "error" in result:
            raise TMCClientError(str(result["error"]))

        return result.get("result", {})

    def get_status(self):
        return self._request("status")

    def get_account(self, address):
        if not isinstance(address, str) or not address.strip():
            raise ValueError("Hasap salgysy nädogry.")

        result = self._request(
            "abci_query",
            {
                "path": f"/account/{address}",
                "prove": "false",
            },
        )

        response = result.get("response", {})

        if response.get("code") != 0:
            return None

        value = response.get("value")

        if not value:
            return None

        try:
            decoded = base64.b64decode(value, validate=True)
            return json.loads(decoded.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise TMCClientError(
                "Hasap maglumatlaryny okamak mümkin däl."
            ) from exc

    def get_chain_state(self):
        result = self._request(
            "abci_query",
            {
                "path": "/state",
                "prove": "false",
            },
        )

        response = result.get("response", {})

        if response.get("code") != 0:
            raise TMCClientError(
                response.get("log", "Blockchain ýagdaýyny alyp bolmady.")
            )

        value = response.get("value")

        if not value:
            raise TMCClientError("Blockchain ýagdaýy boş.")

        try:
            decoded = base64.b64decode(value, validate=True)
            return json.loads(decoded.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise TMCClientError(
                "Blockchain ýagdaýynyň formaty nädogry."
            ) from exc

    def broadcast_transaction(self, transaction):
        raw_tx = encode_transaction(transaction)

        result = self._request(
            "broadcast_tx_sync",
            {
                "tx": "0x" + raw_tx.hex(),
            },
        )

        tx_hash = hashlib.sha256(raw_tx).hexdigest().upper()

        return {
            "hash": tx_hash,
            "code": result.get("code"),
            "log": result.get("log", ""),
            "data": result.get("data", ""),
        }

    def get_transaction(self, tx_hash):
        if not isinstance(tx_hash, str):
            raise ValueError("Tranzaksiýa hash nädogry.")

        normalized_hash = tx_hash.removeprefix("0x")

        if (
            len(normalized_hash) != 64
            or any(c not in "0123456789abcdefABCDEF"
                   for c in normalized_hash)
        ):
            raise ValueError("Tranzaksiýa hash nädogry.")

        return self._request(
            "tx",
            {
                "hash": "0x" + normalized_hash.upper(),
                "prove": "false",
            },
        )
