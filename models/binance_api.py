import json
import os
import numpy
import talib
from binance.client import Client
from models.config import Config
from binance.websockets import BinanceSocketManager
import logging.handlers

from models.mail import Mail

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
        self.rsi_overbought = 51
        self.rsi_oversold = 49
        self.rsi_period = 21
        self.config = Config()
        self.client = Client(self.config.get("Binance_api_key"), self.config.get("Binance_api_secret"))
        self.socket_manager = BinanceSocketManager(self.client)
        self.connection_key = self.socket_manager.start_kline_socket(self.config.get("Symbol"), self.process_message,
                                                                     interval=self.get_interval())

    def set_last_bought(self, close):
        """

        :param close:
        :return:
        """
        with open(os.path.join("last_bought.txt"), "w") as file:
            file.write(str(float(close)))

    def get_last_order_id(self):
        """

        :return:
        """
        if os.path.isfile(os.path.join("last_order_id.txt")):
            with open(os.path.join("last_order_id.txt"), "r") as file:
                return str(file.read())
        return ""

    def set_last_order_id(self, order_id):
        """

        :param close:
        :return:
        """
        with open(os.path.join("last_order_id.txt"), "w") as file:
            file.write(str(order_id))

    def get_last_bought(self):
        """

        :return:
        """
        if os.path.isfile(os.path.join("last_bought.txt")):
            with open(os.path.join("last_bought.txt"), "r") as file:
                return float(file.read())
        return 0.0

    def set_in_position(self, position):
        """

        :param position:
        :return:
        """
        with open(os.path.join("position.txt"), "w") as file:
            file.write(str(int(position)))

    def get_in_position(self):
        """

        :return:
        """
        if os.path.isfile(os.path.join("position.txt")):
            with open(os.path.join("position.txt"), "r") as file:
                return bool(int(file.read()))
        return False

    def start_socket(self):
        """

        :return:
        """
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
            if order["side"] == "BUY":
                self.set_last_bought(order["price"])
                self.set_in_position(True)
                self.send_buy_filled_mail(order["price"], order["origQty"])
        if order["status"] == "CANCELLED":
            self.set_last_order_id("")
            if order["side"] == "SELL":
                self.send_sell_cancelled_mail(order["price"], order["origQty"])
            if order["side"] == "BUY":
                self.send_buy_cancelled_mail(order["price"], order["origQty"])

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

                if len(self.closes) >= 500:
                    debug_logger.debug("old close values: {0}".format(json.dumps(self.closes)))
                    debug_logger.debug("removing close value: {0}".format(self.closes[0]))
                    self.closes.remove(0)
                    debug_logger.debug("new close values: {0}".format(json.dumps(self.closes)))

                debug_logger.debug("appending close value: {0}".format(close))
                self.closes.append(close)

                if len(self.closes) > self.rsi_period:
                    np_closes = numpy.array(self.closes)
                    rsi = talib.RSI(np_closes, self.rsi_period)
                    last_rsi = rsi[-1]
                    debug_logger.debug("RSI {}".format(last_rsi))

                    if self.get_last_order_id() != "":
                        self.check_last_order_status()

                    if last_rsi > self.rsi_overbought and self.get_last_bought() < close and self.get_last_order_id() == "":
                        if self.get_in_position():
                            debug_logger.debug(
                                " **************************** SELL: {} **************************** ".format(close))
                            self.sell(close)
                        else:
                            debug_logger.debug("it is overbought but we dont own anything so nothing to do")

                    if last_rsi < self.rsi_oversold and self.get_last_order_id() == "":
                        if self.get_in_position():
                            debug_logger.debug("it is oversold, but you already own it, nothing to do")
                        else:
                            debug_logger.debug(
                                " **************************** BUY: {} **************************** ".format(close))
                            self.buy(close)

    def sell(self, close):
        """

        :param close:
        :return:
        """
        price, quantity = self.get_sell_value(close)
        order = self.client.create_order(
            symbol=self.config.get("Symbol"),
            side=self.client.SIDE_SELL,
            type=self.client.ORDER_TYPE_LIMIT,
            timeInForce=self.client.TIME_IN_FORCE_GTC,
            quantity=quantity,
            price=price)
        self.set_last_order_id(order["orderId"])
        self.send_sell_mail(close)
        debug_logger.debug(json.dumps(order))

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
        price, quantity = self.get_buy_value(close)
        order = self.client.create_order(
            symbol=self.config.get("Symbol"),
            side=self.client.SIDE_BUY,
            type=self.client.ORDER_TYPE_LIMIT,
            timeInForce=self.client.TIME_IN_FORCE_GTC,
            quantity=quantity,
            price=price)
        self.set_last_order_id(order["orderId"])
        self.send_buy_mail(close)
        debug_logger.debug(json.dumps(order))

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
        message += "Preis: {0}".format(price)
        message += "Menge: {0}".format(quantity)
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
        message += "Preis: {0}".format(price)
        message += "Menge: {0}".format(quantity)
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
        message += "Preis: {0}".format(price)
        message += "Menge: {0}".format(quantity)
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
        message += "Preis: {0}".format(price)
        message += "Menge: {0}".format(quantity)
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
        message += "Preis: {0}".format(price)
        message += "Menge: {0}".format(quantity)
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
        message += "Preis: {0}".format(price)
        message += "Menge: {0}".format(quantity)
        mail = Mail()
        mail.send_mail(subject, message)
