from pathlib import Path

# pyABCI kitaphanasyndaky RequestQuery modelini tapmak
request_file = Path(
    "/usr/local/lib/python3.11/site-packages/"
    "abci/proto/tendermint/abci/request.py"
)

source = request_file.read_text(encoding="utf-8")

old = "    data: Annotated[bytes, Field(1)]"
new = "    data: Annotated[bytes, Field(1)] = b''"

if old not in source:
    if new in source:
        print("RequestQuery modeli eýýäm düzedilen.")
    else:
        raise RuntimeError("RequestQuery üçin zerur setir tapylmady.")
else:
    source = source.replace(old, new, 1)
    request_file.write_text(source, encoding="utf-8")
    print("RequestQuery modeli üstünlikli düzedildi.")
