#!/usr/bin/env python3
from models.binance_api import BinanceAPI
from models.binance_api import debug_logger

binance_api = BinanceAPI()

if __name__ == '__main__':
    debug_logger.debug(
        "**************************************** TRADING BOT STARTED ****************************************")
    binance_api.start_socket()
