import os
import logging
from datetime import date, datetime, time, timedelta
from vnpy.app.cta_strategy import (
    CtaTemplate,
    StopOrder,
    TickData,
    BarData,
    TradeData,
    OrderData,
    BarGenerator,
    ArrayManager,
)
from vnpy.app.cta_strategy.base import EngineType

from time import sleep
from vnpy.rpc import RpcClient
from vnpy.trader.constant import Direction


class TestClient(RpcClient):
    """
    Test RpcClient
    """

    def __init__(self, strategy):
        """
        Constructor
        """
        super(TestClient, self).__init__()
        self.strategy = strategy
        self.last_action_time = datetime.now() - timedelta(minutes=3)

    def callback(self, topic, data):
        """
        Realize callable function
        """
        pass    

        
class ArbiPloterStrategy(CtaTemplate):
    """"""
    author = "zy"
    classname = 'ArbiPloterStrategy'

    fixed_size = 0.0001
    xmin = 1
    group_id = 0
    price_add = 0
    INIT_PERIOD = 5
    gateway_name = ""
    
    parameters = ["fixed_size", "xmin", "group_id", "price_add", "gateway_name"]
    variables = []

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
        self.bg = BarGenerator(self.on_bar, self.xmin)
        self.vt_symbol = vt_symbol
        self.cta_engine = cta_engine
        self.strategy_name = strategy_name

        req_address = "tcp://localhost:2039"
        sub_address = "tcp://localhost:4302"

        self.tc = TestClient(self)
        try:
            self.tc.subscribe_topic("")
            self.tc.start(
                req_address,
                sub_address,
            )
        except Exception as e:
            print(e)
            assert 0

        self.daily_trade_count_max = 20
        self.last_action_second = 0
        self.send_flag = False
        self.trading_last_time = datetime.now()
        
        self.now_date = datetime.now().strftime("%Y-%m-%d")


    def on_init(self):
        """
        Callback when strategy is inited.
        """
        super().on_init()
        self.write_log("# On Init {}".format(self.strategy_name))
        self.load_bar(self.INIT_PERIOD)

    def on_start(self):
        """
        Callback when strategy is started.
        """
        super().on_start()

        self.on_bar(self.last_bar, finish_flag=1)
        try:
            self.tc.on_start()
        except Exception as e:
            print(e)
        self.write_log("# On Start {}".format(self.strategy_name))


    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        super().on_stop()
        self.write_log("# On Sto {}".format(self.strategy_name))

        
    def on_bar(self, bar: BarData, finish_flag = 0):
        self.last_bar = bar

        bar_stru = {
            'datetime': bar.datetime.strftime("%Y-%m-%d %H:%M:%S.%f"),
            'ask_price': bar.close_price,
            'bid_price': bar.close_price,
            'close_price': bar.close_price,
            'vt_symbol': self.vt_symbol,
            'group_id': self.group_id,
            'finish': finish_flag
        }

        try:
            self.tc.send_bar(bar_stru, self.group_id)
        except Exception as e:
            print(e)

        self.send_flag = False
        