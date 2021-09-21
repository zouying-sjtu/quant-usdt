#coding=gbk
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
        if topic == 'heart-beat':
            return
        
        vt_symbol =  str(self.strategy.vt_symbol)
        
        if topic == 'action':
            if abs(self.last_action_time - datetime.now()) > timedelta(seconds=10):
                print(f"client received topic:{topic}, data:{data}, vt_symbol:{vt_symbol}")
                try:
                    self.strategy.on_action()
                    self.last_action_time = datetime.now()
                except Exception as e:
                    print("Exception in callback", e)
        

class ArbiSingleTickStrategy(CtaTemplate):
    """"""
    author = "zy"
    classname = 'ArbiSingleTickStrategy'

    fixed_size = 0.0001
    xmin = 1
    group_id = 0
    price_add = 0
    INIT_PERIOD = 3
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

        req_address = "tcp://localhost:2019"
        sub_address = "tcp://localhost:4102"

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

        self.daily_trade_count_max = 200
        self.last_action_second = 0
        self.send_flag = False
        self.trading_last_time = datetime.now()
        
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        vntrader_dir = os.path.join(root_dir, '.vntrader')
        self.log_dir = os.path.join(vntrader_dir, 'logers')
        self.log_server_dir =  os.path.join(self.log_dir, "{}".format(datetime.now().strftime("%Y-%m-%d")))
        for dir_ in [self.log_dir, self.log_server_dir]:
            if not os.path.exists(dir_):
                try:
                    os.mkdir(dir_)
                except Exception as e:
                    print(e)
        self._init_logger()

        self.now_date = datetime.now().strftime("%Y-%m-%d")
        self.datetimes_cache = []

    def silent(self):
        now_time = datetime.now().time()
        silent_times = [
            [time(7,59,0),     time(8,3,30)],
            [time(0,0,0),       time(0, 3,30)],
            [time(15,59,0),    time(16, 3,30)],
            [time(23,59,0),    time(23,59,59,999999)]
        ]
        for slient_time in silent_times:
            [start_time, end_time] = slient_time
            if now_time >= start_time and now_time <= end_time:
                self.last_err_alerts = datetime.now()
                return True
        return False

    def get_err_alert(self):
        gateway_name = self.gateway_name
        gateway = self.cta_engine.main_engine.get_gateway(gateway_name)
        if gateway is None:
            self.log_info('gateway is None: {}'.format(gateway_name))
        err = gateway.get_err_alert()
        if err:
            self.log_info('get_err_alert: {} err:{}'.format(gateway_name, err))
            try:
                self.tc.err_alert()
            except Exception as e:
                print(e)
        return err

    def _init_logger(self):
        self.log_server_dir =  os.path.join(self.log_dir, "{}".format(datetime.now().strftime("%Y-%m-%d")))
        if not os.path.exists(self.log_server_dir):
            try:
                os.mkdir(self.log_server_dir)
            except Exception as e:
                print(e)

        self.log_file = os.path.join(self.log_server_dir, 'client-{}-{}.log'.format(self.group_id, self.vt_symbol))
        self.logger = logging.getLogger("client-{}-{}".format(self.group_id, self.vt_symbol))
        self.logger.setLevel(level=logging.INFO)
        handler = logging.FileHandler(self.log_file)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        self.log_tick_file = os.path.join(self.log_server_dir, 'client-tick-{}-{}.log'.format(self.group_id, self.vt_symbol))
        self.logger_tick = logging.getLogger("client-tick-{}-{}".format(self.group_id, self.vt_symbol))
        self.logger_tick.setLevel(level=logging.INFO)
        handler_tick = logging.FileHandler(self.log_tick_file)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler_tick.setFormatter(formatter)
        self.logger_tick.addHandler(handler_tick)

    def log_info(self, msg,  type='default'):
        try:
            if self.now_date != datetime.now().strftime("%Y-%m-%d"):
                self._init_logger()
                self.now_date = datetime.now().strftime("%Y-%m-%d")
            if type == 'default':
                self.logger.info(str(msg))
            elif type == 'tick':
                self.logger_tick.info(str(msg))
        except Exception as e:
            print(e)

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
        try:
            self.tc.on_start()
            server_pos = self.tc.on_pos()
            self.pos = server_pos[self.vt_symbol]
        except Exception as e:
            print(e)
        self._init_logger()
        self.write_log("# On Start {}".format(self.strategy_name))

    def on_stop(self):
        """
        Callback when strategy is stopped.
        """
        super().on_stop()
        self.write_log("# On Stopֹ {}".format(self.strategy_name))

    def on_tick(self, tick: TickData):
        """
        Callback of new tick data update.
        """
        second = int(tick.datetime.strftime("%S"))

        if tick is not None:
            self.bg.update_tick(tick)

        ask_price = tick.ask_price_2 if tick is not None else 0
        bid_price = tick.bid_price_2 if tick is not None else 0
        close_price = (ask_price + bid_price) / 2 
        tick_stru = {
            'datetime': tick.datetime.strftime("%Y-%m-%d %H:%M:%S.%f"),
            'ask_price': ask_price,
            'bid_price': bid_price,
            'close_price': close_price,
            'vt_symbol': self.vt_symbol,
            'group_id': self.group_id
        }

        if tick_stru['datetime'] in self.datetimes_cache:
            return
        else:
            self.datetimes_cache.append(tick_stru['datetime'])
            self.datetimes_cache = self.datetimes_cache[-500:]


        if datetime.now().second == 0:
            err = self.get_err_alert()
            self.log_info('send tick: {} {} gateway-err: {}'.format(tick_stru['datetime'], tick_stru['close_price'], err), type='tick')
                    
        try:
            self.tc.send_tick(tick_stru, self.group_id)
        except Exception as e:
            print(e)


    def on_bar(self, bar: BarData):
        self.cancel_all()

        if self.trading:
            self.log_info('client: {} {} {} {} {}'.format(self.group_id, self.vt_symbol, bar.datetime, bar.close_price, self.pos))

        if bar.datetime.strftime("%H:%M") == "09:00":
            self.daily_trade_count_max = 200

        self.send_flag = False


    def on_action(self):
        print('strategy.on_action()')

        self.log_info('# On Action')

        if not self.trading:
            return

        if self.send_flag:
            self.log_info('\tsend_flag')
            return

        err = self.get_err_alert()
        if err:
            self.log_info('\tprevent err-gateway from client')
            return

        actions = {}
        try:
            actions = self.tc.get_action()
        except Exception as e:
            self.log_info('Exception: client on_action {}'.format(e))
            print('Exception: client on_action ', e)   

        if actions == {} :
            self.log_info('\tactions == {}')
            return

        self.log_info("\t # get action: {}".format(actions), type = 'tick')

        action = actions[self.vt_symbol]
        if action == {}:
            self.log_info("\t# warning : {}".format(actions), type = 'tick')
            return 

        price = action['price']
        target_pos = action['target_pos']
        current_pos = self.pos

        # target_pos == self.pos
        self.log_info('target_pos == self.pos {} {}'.format(target_pos, self.pos))
        if abs(target_pos - self.pos) < 1e-8:
            return

        DEBUG = False
        if DEBUG:
            trade_status = {
                'vt_symbol': self.vt_symbol,
                'trade_order_id': "{}-{}".format(self.vt_symbol, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                'price': price, 
                'trade_pos': target_pos - current_pos
            }
            print('DEBUG send-status', trade_status)
            try:
                self.tc.send_status(trade_status, self.group_id)
            except Exception as e:
                print(e)
            self.pos = target_pos
            self.daily_trade_count_max -= 1
            return
        
        if self.daily_trade_count_max < 0:
            self.log_info('daily_trade_count_max {}'.format(self.daily_trade_count_max))
            return

        if self.silent():
            self.log_info("\tsilent from client")
            return

        if abs(self.trading_last_time - datetime.now()) < timedelta(seconds=15):
            self.log_info("\ttrading_last_time from client")
            return

        pos_diff = target_pos - current_pos
        volume = abs(pos_diff)
        print('volume', volume)
        if pos_diff > 0:
            price = price + self.price_add
            print(datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"), action)
            self.log_info('# Trade {} \n {}'.format(datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"), action))
            if current_pos < 0:
                self.cover(price, volume)
            else:
                self.buy(price, volume)
            self.send_flag = True
            self.trading_last_time = datetime.now()
        elif pos_diff < 0:
            price = price - self.price_add
            print(datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"), action)
            self.log_info('# Trade {} \n {}'.format(datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"), action))
            if current_pos > 0:
                self.sell(price, volume)
            else:
                self.short( price, volume)
            self.send_flag = True
            self.trading_last_time = datetime.now()


    def on_order(self, order: OrderData):
        """
        Callback of new order data update.
        """
        print(order)
        self.log_info("# Order #")
        self.log_info(str(order))
        self.log_info("# Order #")
        super().on_order(order)
        
    def on_trade(self, trade: TradeData):
        """
        Callback of new trade data update.
        """
        super().on_trade(trade)
        print(trade)
        self.log_info("# Trade #")
        self.log_info(str(trade))
        self.log_info("# Trade #")

        if trade.direction == Direction.LONG:
            trade_pos = trade.volume
        elif trade.direction == Direction.SHORT:
            trade_pos = - trade.volume

        trade_status = {
            'vt_symbol': self.vt_symbol,
            'trade_order_id': '{}-{}'.format(self.vt_symbol, trade.tradeid),
            'price': trade.price, 
            'trade_pos': trade_pos
        }

        try:
            self.tc.send_status(trade_status, self.group_id)
        except Exception as e:
            print(e)
            self.tc.send_status(trade_status, self.group_id)

        self.daily_trade_count_max -= 1
        self.put_event()

    def on_stop_order(self, stop_order: StopOrder):
        """
        Callback of stop order update.
        """
        super().on_stop_order(stop_order)

        