from models.binance_api import BinanceAPI
from models.config import Config
import backtrader as bt

from datetime import datetime

config = Config()
binance_api = BinanceAPI()


class MyStrategy(bt.Strategy):

    def __init__(self):
        self.rsi = bt.ind.RSI(period=21)

    def next(self):
        if self.rsi < 30 and not self.position:
            self.buy(size=0.2)

        if self.rsi > 70 and self.position:
            self.close()


class RSIStrategy(bt.Strategy):

    def __init__(self):
        self.rsi = bt.ind.RSI(period=18)
        self.sma1, self.sma2 = bt.ind.EMA(period=55), bt.ind.EMA(period=21)
        self.crossover = bt.ind.CrossOver(self.sma1, self.sma2)

    def next(self):
        if self.rsi < 30 and self.crossover > 0 and not self.position:
            self.buy(size=1)

        if self.rsi > 70 and self.position:
            self.close()


cerebro = bt.Cerebro()
dataframe = binance_api.get_candles_for_symbol()
data = bt.feeds.PandasData(dataname=dataframe, datetime='datetime')
cerebro.adddata(data)
cerebro.addstrategy(MyStrategy)
# cerebro.addstrategy(SmaCross)
cerebro.run()
cerebro.plot()
