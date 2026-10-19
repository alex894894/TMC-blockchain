
import asyncio
import logging

from abci.server import Server
from tmc_app import TMCApp


async def main():
    logging.basicConfig(level=logging.INFO)

    app = TMCApp()
    server = Server(app)

    await server.start(host="0.0.0.0", port=26658)
    await server


if __name__ == "__main__":
    asyncio.run(main())
