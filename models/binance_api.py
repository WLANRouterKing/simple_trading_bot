import json
import os
import pandas as pd
import numpy
import talib
from binance.helpers import *
from binance.client import Client
from models.config import Config
from binance.websockets import BinanceSocketManager
import logging.handlers
from models.mail import Mail
import matplotlib.pyplot as plt

debug_logger = logging.getLogger('debug.log')
debug_logger.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s || [%(filename)s:%(lineno)s - %(funcName)20s() ] - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S')
rotating_file_handler = logging.handlers.RotatingFileHandler(filename='debug.log')
rotating_file_handler.setFormatter(formatter)
debug_logger.addHandler(rotating_file_handler)


class BinanceAPI:
    """
    Verwaltet Methoden für die Zugriffe auf die Binance API
    """

    # noinspection PyTypeChecker
    def __init__(self):
        self.closes = []
        self.rsi_overbought = 70
        self.rsi_oversold = 15
        self.rsi_period = 21
        self.config = Config()
        self.client = Client(self.config.get("Binance_api_key"), self.config.get("Binance_api_secret"))
        self.socket_manager = BinanceSocketManager(self.client)
        self.connection_key = self.socket_manager.start_kline_socket(self.config.get("Symbol"), self.process_message,
                                                                     interval=self.get_interval())

    def write_file(self, path, content):
        """

        :param path:
        :param content:
        :return:
        """
        with open(path, "w") as file:
            file.write(content)

    def read_file(self, path):
        """

        :param path:
        :return:
        """
        if os.path.isfile(path):
            with open(path, "r") as file:
                return str(file.read())
        return ""

    def set_last_bought(self, close):
        """
        writes the last bought value into a text file
        :param close:
        :return:
        """
        self.write_file(os.path.join("last_bought.txt"), str(float(close)))

    def get_last_order_id(self):
        """

        :return:
        """
        return self.read_file(os.path.join("last_order_id.txt"))

    def set_last_order_id(self, order_id):
        """

        :param order_id:
        :return:
        """
        self.write_file(os.path.join("last_order_id.txt"), str(order_id))

    def get_last_bought(self):
        """

        :return:
        """
        if (self.read_file(os.path.join("last_bought.txt"))) != "":
            return float(self.read_file(os.path.join("last_bought.txt")))
        return 0.0

    def set_in_position(self, position):
        """

        :param position:
        :return:
        """
        self.write_file(os.path.join("position.txt"), str(int(position)))

    def get_in_position(self):
        """

        :return:
        """
        if self.read_file(os.path.join("position.txt")) != "":
            return bool(int(self.read_file(os.path.join("position.txt"))))
        return 0

    def start_socket(self):
        """

        :return:
        """
        dataframe = self.get_candles()
        for close in dataframe['close']:
            self.closes.append(close)
        self.socket_manager.start()
        debug_logger.debug("socket started")

    def restart_socket(self):
        """

        :return:
        """
        debug_logger.debug("restarting socket")
        self.socket_manager.stop_socket(self.connection_key)
        self.start_socket()
        debug_logger.debug("socket restarted")

    def check_last_order_status(self):
        order_id = self.get_last_order_id()
        order = self.client.get_order(symbol=self.config.get("Symbol"), orderId=order_id)
        if order["status"] == "FILLED":
            self.set_last_order_id("")
            if order["side"] == "SELL":
                self.set_in_position(False)
                self.set_last_bought(0.0)
                self.send_sell_filled_mail(order["price"], order["origQty"])
                debug_logger.debug(
                    "************************************ Verkauforder ausgeführt: {0} Menge: {1} ************************************".format(
                        order["price"], order["origQty"]))
            if order["side"] == "BUY":
                self.set_last_bought(order["price"])
                self.set_in_position(True)
                self.send_buy_filled_mail(order["price"], order["origQty"])
                debug_logger.debug(
                    "************************************ Kauforder ausgeführt: {0} Menge: {1} ************************************".format(
                        order["price"], order["origQty"]))
        if order["status"] == "CANCELLED":
            self.set_last_order_id("")
            if order["side"] == "SELL":
                self.send_sell_cancelled_mail(order["price"], order["origQty"])
                debug_logger.debug(
                    "************************************ Verkauforder abgebrochen: {0} Menge: {1} ************************************".format(
                        order["price"], order["origQty"]))
            if order["side"] == "BUY":
                self.send_buy_cancelled_mail(order["price"], order["origQty"])
                debug_logger.debug(
                    "************************************ Kauforder abgebrochen: {0} Menge: {1} ************************************".format(
                        order["price"], order["origQty"]))

    def process_message(self, msg):
        """

        :param msg:
        :return:
        """
        if msg['e'] == 'error':
            debug_logger.debug("".format(msg['e']))
            self.restart_socket()
        else:
            json_message = msg
            candle = json_message["k"]
            is_candle_closed = candle["x"]
            close = float(candle["c"])

            if is_candle_closed:
                should_sell = 0
                should_buy = 0
                debug_logger.debug(
                    "--------------------------------------------------------------------------------------------------------------------------------------")
                self.closes.append(close)

                while len(self.closes) > 800:
                    self.closes.pop(0)

                np_closes = numpy.array(self.closes)
                # Calculate the MACD and Signal Line indicators
                # Calculate the Short Term Exponential Moving Average
                ShortEMA = talib.EMA(np_closes, 9)
                # Calculate the Long Term Exponential Moving Average
                LongEMA = talib.EMA(np_closes, 18)
                # Calculate the Moving Average Convergence/Divergence (MACD)
                MACD = ShortEMA - LongEMA
                # Calcualte the signal line
                signal = talib.EMA(MACD, 5)
                upperband, middleband, lowerband = talib.BBANDS(np_closes, timeperiod=18, nbdevup=2, nbdevdn=2,
                                                                matype=0)
                upperband_crossed = numpy.where((np_closes > upperband), 1, 0)
                lowerband_crossed = numpy.where((np_closes < lowerband), 1, 0)
                max_price = numpy.amax(np_closes)
                lowest_price = numpy.amin(np_closes)
                average_price = numpy.average(np_closes)

                last_upperband_crossed = upperband_crossed[-1]
                last_lowerband_crossed = lowerband_crossed[-1]
                last_macd = MACD[-1]
                last_signal = signal[-1]

                if self.get_last_order_id() != "":
                    self.check_last_order_status()

                if last_macd > last_signal:
                    should_buy += 1

                if last_lowerband_crossed:
                    should_buy += 1

                if close > lowest_price and close < average_price:
                    should_buy += 1

                if close < max_price and close > average_price:
                    should_sell += 1

                if last_macd < last_signal:
                    should_sell += 1

                if last_upperband_crossed:
                    should_sell += 1

                debug_logger.debug("last_upperband_crossed {}".format(last_upperband_crossed))
                debug_logger.debug("last_lowerband_crossed {}".format(last_lowerband_crossed))
                debug_logger.debug("last_macd {}".format(last_macd))
                debug_logger.debug("last_signal {}".format(last_signal))
                debug_logger.debug("buy {}".format(should_buy))
                debug_logger.debug("sell {}".format(should_sell))

                if should_sell == 3 and self.get_last_bought() + 10 < close and self.get_last_order_id() == "":
                    if self.get_in_position():
                        self.sell(close)
                    else:
                        debug_logger.debug("it is overbought but we dont own anything so nothing to do")

                if should_buy == 3 and self.get_last_order_id() == "":
                    if self.get_in_position():
                        debug_logger.debug("it is oversold, but you already own it, nothing to do")
                    else:
                        self.buy(close)

    def get_order_type(self):
        order_type = self.config.get("OrderType")
        if order_type == "0":
            order_type = self.client.ORDER_TYPE_MARKET
        if order_type == "1":
            order_type = self.client.ORDER_TYPE_LIMIT
        return order_type

    def backtest(self):
        dataframe = self.get_historical_candles()
        dates = list()
        for close in dataframe["close"]:
            self.closes.append(close)

        while len(self.closes) > 8000:
            self.closes.pop(0)

        for date in dataframe['datetime']:
            dates.append(date)

        while len(dates) > 8000:
            dates.pop(0)

        np_closes = numpy.array(self.closes)
        # Calculate the MACD and Signal Line indicators
        # Calculate the Short Term Exponential Moving Average
        ShortEMA = talib.EMA(np_closes, 9)
        # Calculate the Long Term Exponential Moving Average
        LongEMA = talib.EMA(np_closes, 18)
        # Calculate the Moving Average Convergence/Divergence (MACD)
        MACD = ShortEMA - LongEMA
        # Calcualte the signal line
        signal = talib.EMA(MACD, 5)
        upperband, middleband, lowerband = talib.BBANDS(np_closes, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
        upperband_crossed = numpy.where((np_closes > upperband), 1, 0)
        lowerband_crossed = numpy.where((np_closes < lowerband), 1, 0)
        max_price = numpy.amax(np_closes)
        lowest_price = numpy.amin(np_closes)
        average_price = numpy.average(np_closes)

        last_bought = self.get_last_bought()
        in_position = self.get_in_position()

        bought = list()
        sold = list()

        last_upperband_crossed = False
        last_lowerband_crossed = False

        for i in range(0, len(np_closes)):
            should_sell = 0
            should_buy = 0
            buy = False
            sell = False

            last_macd = MACD[i]
            last_signal = signal[i]

            if upperband_crossed[i] and not last_upperband_crossed:
                last_upperband_crossed = True
                last_lowerband_crossed = False

            if lowerband_crossed[i] and not last_lowerband_crossed:
                last_upperband_crossed = False
                last_lowerband_crossed = True

            close = np_closes[i]

            if last_macd > last_signal:
                should_buy += 1

            if last_lowerband_crossed:
                should_buy += 1

            if close > lowest_price and close < average_price:
                should_buy += 1

            if close < max_price and close > average_price:
                should_sell += 1

            if last_macd < last_signal:
                should_sell += 1

            if last_upperband_crossed:
                should_sell += 1

            print(
                "--------------------------------------------------------------------------------------------------------------------------------------")
            print("last_upperband_crossed {}".format(last_upperband_crossed))
            print("last_lowerband_crossed {}".format(last_lowerband_crossed))
            print("last_macd {}".format(last_macd))
            print("last_signal {}".format(last_signal))
            print("unterer preisbereich {}".format(close > lowest_price and close < average_price))
            print("oberer preisbereich {}".format(close < max_price and close > average_price))
            print("buy {}".format(should_buy))
            print("sell {}".format(should_sell))

            if should_sell == 3 and last_bought + 5 < close:
                if in_position:
                    print("****************** sell *********************")
                    sold.append(close)
                    in_position = False
                    last_bought = 0.0
                    sell = True

            if should_buy == 3:
                if not in_position:
                    print("****************** buy *********************")
                    bought.append(close)
                    in_position = True
                    last_bought = close
                    buy = True

            if not sell:
                sold.append(numpy.nan)
            if not buy:
                bought.append(numpy.nan)

        plt.figure(1)
        plt.subplot(311)
        plt.plot(dates, upperband, color='yellow')
        plt.plot(dates, middleband, color='black')
        plt.plot(dates, lowerband, color='green')
        plt.plot(dates, sold, color='red', marker='o')
        plt.plot(dates, bought, color='green', marker='o')
        plt.plot(dates, np_closes, color='blue')
        plt.subplot(313)
        plt.plot(dates, MACD, label="macd", color='red')
        plt.plot(dates, signal, label="signal", color='green')
        plt.show()

    def sell(self, close):
        """

        :param close:
        :return:
        """
        try:
            price, quantity = self.get_sell_value(close)
            order = self.client.create_order(
                symbol=self.config.get("Symbol"),
                side=self.client.SIDE_SELL,
                type=self.get_order_type(),
                timeInForce=self.client.TIME_IN_FORCE_GTC,
                quantity=quantity,
                price=price)
            self.set_last_order_id(order["orderId"])
            self.send_sell_mail(close)
            debug_logger.debug(
                " **************************** SELL: {} **************************** ".format(close))
            print(" **************************** SELL: {} **************************** ".format(close))
            debug_logger.debug(json.dumps(order))
        except Exception as error:
            debug_logger.debug(error)
            mail = Mail()
            mail.send_mail("Fehler", error)
            return False

    def get_sell_value(self, close):
        """

        :param close:
        :return:
        """
        new_close = close + ((close / 100) / 10)
        quantity = float(self.config.get("Quantity"))
        new_quantity = quantity - ((quantity / 100) / 10)
        return round(new_close, 2), round(new_quantity, 8)

    def buy(self, close):
        """

        :param close:
        :return:
        """
        try:
            price, quantity = self.get_buy_value(close)
            order = self.client.create_order(
                symbol=self.config.get("Symbol"),
                side=self.client.SIDE_BUY,
                type=self.get_order_type(),
                timeInForce=self.client.TIME_IN_FORCE_GTC,
                quantity=quantity,
                price=price)
            self.set_last_order_id(order["orderId"])
            self.send_buy_mail(close)
            debug_logger.debug(
                " **************************** BUY: {} **************************** ".format(close))
            print(" **************************** BUY: {} **************************** ".format(close))
            debug_logger.debug(json.dumps(order))
        except Exception as error:
            debug_logger.debug(error)
            mail = Mail()
            mail.send_mail("Fehler", error)
            return False

    def get_buy_value(self, close):
        """

        :param close:
        :return:
        """
        new_close = close - ((close / 100) / 10)
        quantity = float(self.config.get("Quantity"))
        new_quantity = quantity + ((quantity / 100) / 10)
        return round(new_close, 2), round(new_quantity, 8)

    def get_interval(self):
        """

        :return:
        """
        interval_seconds = int(self.config.get("Interval"))

        if interval_seconds == 60:
            return self.client.KLINE_INTERVAL_1MINUTE
        if interval_seconds == 180:
            return self.client.KLINE_INTERVAL_3MINUTE
        if interval_seconds == 300:
            return self.client.KLINE_INTERVAL_5MINUTE
        if interval_seconds == 900:
            return self.client.KLINE_INTERVAL_15MINUTE
        if interval_seconds == 1800:
            return self.client.KLINE_INTERVAL_30MINUTE
        if interval_seconds == 3600:
            return self.client.KLINE_INTERVAL_1HOUR
        if interval_seconds == 4 * 3600:
            return self.client.KLINE_INTERVAL_4HOUR
        if interval_seconds == 24 * 3600:
            return self.client.KLINE_INTERVAL_1DAY

    def get_price_for_symbol(self):
        """

        :return:
        """
        return self.client.get_avg_price(symbol=self.config.get("Symbol"))

    def send_buy_mail(self, close):
        """

        :param close:
        :return:
        """
        price, quantity = self.get_buy_value(close)
        subject = "Tradingbot: Kaufe"
        message = "Ich setze eine Kauforder:"
        message += "Preis: {0}</br>".format(price)
        message += "Menge: {0}</br>".format(quantity)
        mail = Mail()
        mail.send_mail(subject, message)

    def send_buy_filled_mail(self, price, quantity):
        """

        :param price:
        :param quantity:
        :return:
        """
        subject = "Tradingbot: Gekauft"
        message = "Kauforder erfolgreich:"
        message += "Preis: {0}</br>".format(price)
        message += "Menge: {0}</br>".format(quantity)
        mail = Mail()
        mail.send_mail(subject, message)

    def send_buy_cancelled_mail(self, price, quantity):
        """

        :param price:
        :param quantity:
        :return:
        """
        subject = "Tradingbot: Kauf abgebrochen"
        message = "Die letzte Kauforder wurde abgebrochen:"
        message += "Preis: {0}</br>".format(price)
        message += "Menge: {0}</br>".format(quantity)
        mail = Mail()
        mail.send_mail(subject, message)

    def send_sell_mail(self, close):
        """

        :param close:
        :return:
        """
        price, quantity = self.get_sell_value(close)
        subject = "Tradingbot: Verkaufe"
        message = "Ich setze eine Verkauforder:"
        message += "Preis: {0}</br>".format(price)
        message += "Menge: {0}</br>".format(quantity)
        mail = Mail()
        mail.send_mail(subject, message)

    def send_sell_filled_mail(self, price, quantity):
        """

        :param price:
        :param quantity:
        :return:
        """
        subject = "Tradingbot: Verkauft"
        message = "Die letzte Verkauforder war erfolgreich:"
        message += "Preis: {0}</br>".format(price)
        message += "Menge: {0}</br>".format(quantity)
        mail = Mail()
        mail.send_mail(subject, message)

    def send_sell_cancelled_mail(self, price, quantity):
        """

        :param price:
        :param quantity:
        :return:
        """
        subject = "Tradingbot: Verkauf abgebrochen"
        message = "Die letzte Verkauforder wurde abgebrochen:"
        message += "Preis: {0}</br>".format(price)
        message += "Menge: {0}</br>".format(quantity)
        mail = Mail()
        mail.send_mail(subject, message)

    def get_candles(self):
        record = self.client.get_klines(symbol=self.config.get("Symbol"), interval=self.get_interval())
        myList = []

        try:
            for item in record:
                n_item = []
                int_ts = int(item[0] / 1000)
                # nur neue timestamps anhängen

                n_item.append(int_ts)  # open time
                n_item.append(float(item[1]))  # open
                n_item.append(float(item[2]))  # high
                n_item.append(float(item[3]))  # low
                n_item.append(float(item[4]))  # close
                n_item.append(float(item[5]))  # volume
                n_item.append(int(item[6] / 1000))  # close_time
                n_item.append(float(item[7]))  # quote_assetv
                n_item.append(int(item[8]))  # trades
                n_item.append(float(item[9]))  # taker_b_asset_v
                n_item.append(float(item[10]))  # taker_b_quote_v
                n_item.append(datetime.fromtimestamp(n_item[0]))
                myList.append(n_item)
        except Exception as error:
            debug_logger.debug(error)

        new_ohlc = pd.DataFrame(myList, columns=['open_time', 'open', 'high', 'low',
                                                 'close', 'volume', 'close_time', 'quote_assetv', 'trades',
                                                 'taker_b_asset_v',
                                                 'taker_b_quote_v', 'datetime'])

        return new_ohlc

    def get_historical_candles(self):
        record = self.client.get_historical_klines(self.config.get("Symbol"), self.get_interval(), "1 week ago UTC")
        myList = []

        try:
            for item in record:
                n_item = []
                int_ts = int(item[0] / 1000)
                # nur neue timestamps anhängen

                n_item.append(int_ts)  # open time
                n_item.append(float(item[1]))  # open
                n_item.append(float(item[2]))  # high
                n_item.append(float(item[3]))  # low
                n_item.append(float(item[4]))  # close
                n_item.append(float(item[5]))  # volume
                n_item.append(int(item[6] / 1000))  # close_time
                n_item.append(float(item[7]))  # quote_assetv
                n_item.append(int(item[8]))  # trades
                n_item.append(float(item[9]))  # taker_b_asset_v
                n_item.append(float(item[10]))  # taker_b_quote_v
                n_item.append(datetime.fromtimestamp(n_item[0]))
                myList.append(n_item)
        except Exception as error:
            debug_logger.debug(error)

        new_ohlc = pd.DataFrame(myList, columns=['open_time', 'open', 'high', 'low',
                                                 'close', 'volume', 'close_time', 'quote_assetv', 'trades',
                                                 'taker_b_asset_v',
                                                 'taker_b_quote_v', 'datetime'])

        return new_ohlc
