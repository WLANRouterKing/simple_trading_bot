#!/usr/bin/env python3
from models.binance_api import BinanceAPI

binance_api = BinanceAPI()

if __name__ == '__main__':
    binance_api.start_socket()
