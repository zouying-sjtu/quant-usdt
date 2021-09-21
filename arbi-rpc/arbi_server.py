#coding=gbk

from genericpath import exists
import multiprocessing
import os
import argparse
import pdb
import sys
import json
from time import sleep
from datetime import date, datetime, time, timedelta
from logging import INFO
import logging
import numpy as np

from vnpy.event import EventEngine
from vnpy.gateway.binances.binances_gateway import TIMEDELTA_MAP
from vnpy.trader.setting import SETTINGS
from vnpy.trader.engine import MainEngine

# from vnpy.gateway.ctp import CtpGateway
from vnpy.gateway.binances import BinancesGateway
from vnpy.gateway.binances import BinancesGateway

from vnpy.app.cta_strategy import CtaStrategyApp
from vnpy.app.cta_strategy.base import EVENT_CTA_LOG

from vnpy.rpc import RpcClient
from vnpy.rpc import RpcServer


class TestServer(RpcServer):
    """
    Test RpcServer
    """
    def __init__(
        self, 
        vt_symbols,
        group_id, 
        fix_sizes,
        arbi_high,
        arbi_low,
        fix_fluct,
        move_bias
    ):
        """
        Constructor
        """
        super(TestServer, self).__init__()

        # strategy parameters
        self.arbi_high = arbi_high
        self.arbi_low = arbi_low
        self.fix_sizes = fix_sizes
        self.fix_fluct = fix_fluct
        self.move_bias = move_bias

        # strategy status
        self.spread_long_up = 0
        self.spread_long_mid = 0
        self.spread_long_down = 0

        self.spread_short_up = 0
        self.spread_short_mid = 0
        self.spread_short_down = 0

        self.not_match_count = 0
        self.match_count = 0

        self.first_queue = []
        self.second_queue = []

        self.trade_order_ids = []
        self.move_spead = np.zeros([30])
        # trade status
        self.init = False
        self.trading = False
        self.last_err_alerts = datetime.now() - timedelta(minutes=5)

        self.vt_symbols = vt_symbols
        self.leg1_symbol = vt_symbols[0]
        self.leg2_symbol = vt_symbols[1]
        self.group_id = group_id

        self.action = {k:{} for k in vt_symbols}
        self.target = {k:0 for k in vt_symbols}
        self.pos = {k:0 for k in vt_symbols}
        self.trade_prices = {k:{} for k in vt_symbols}

        self.round_size = list(str(min(self.fix_sizes))).count('0') + 2
        self.delta_match = timedelta(seconds=0, microseconds=350000)
        self.now_date = datetime.now().strftime("%Y-%m-%d")
        self.hug_price_time = datetime.now()

        root_dir = os.path.dirname(os.path.abspath(__file__))
        vntrader_dir = os.path.join(root_dir, '.vntrader')
        if os.path.exists(vntrader_dir):
            print(vntrader_dir)

        # logger
        self.log_dir = os.path.join(vntrader_dir, 'logers')
        self.log_server_dir =  os.path.join(self.log_dir, "{}".format(datetime.now().strftime("%Y-%m-%d")))
        for dir_ in [self.log_dir, self.log_server_dir]:
            if not os.path.exists(dir_):
                try:
                    os.mkdir(dir_)
                except Exception as e:
                    print(e)
        self._init_logger()

        # load status caches
        self.status_path = os.path.join(vntrader_dir, 'arbi_btc_strategy_data_{}.json'.format(self.group_id))
        self.load_status()

        # server register
        self.register(self.send_tick)
        self.register(self.get_action)
        self.register(self.send_status)
        self.register(self.on_start)
        self.register(self.on_pos)
        self.register(self.err_alert)
    
    def _init_logger(self):
        self.log_server_dir =  os.path.join(self.log_dir, "{}".format(datetime.now().strftime("%Y-%m-%d")))
        if not os.path.exists(self.log_server_dir):
            try:
                os.mkdir(self.log_server_dir)
            except Exception as e:
                print(e)

        self.log_file = os.path.join(self.log_server_dir, 'server-{}.log'.format(self.group_id))
        self.logger = logging.getLogger("server")
        self.logger.setLevel(level=logging.INFO)
        handler = logging.FileHandler(self.log_file)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        self.log_tick_file = os.path.join(self.log_server_dir, 'server-tick-{}.log'.format(self.group_id))
        self.logger_tick = logging.getLogger("server-tick")
        self.logger_tick.setLevel(level=logging.INFO)
        handler_tick = logging.FileHandler(self.log_tick_file)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler_tick.setFormatter(formatter)
        self.logger_tick.addHandler(handler_tick)

    def log(self, msg,  type='default'):
        if self.now_date != datetime.now().strftime("%Y-%m-%d"):
            self._init_logger()
            self.now_date = datetime.now().strftime("%Y-%m-%d")
        if type == 'default':
            self.logger.info(str(msg))
        elif type == 'tick':
            self.logger_tick.info(str(msg))

    def load_status(self):
        if not os.path.exists(self.status_path):
            return
        with open(self.status_path, 'r') as f:
            status = json.load(f)
        self.pos = status.get('pos', self.pos)
        self.target = status.get('target', self.target)
        self.log("# Load Cache")
        self.log("\tpos: {}".format(self.pos))
        self.log("\ttarget: {}".format(self.target))

    def dump_status(self):
        status = {
            'pos': self.pos,
            'target': self.target
        }
        with open(self.status_path, 'w') as f:
            json.dump(status, f, indent=2)
        return 0
        
    def get_pos(self, vt_symbol):
        if vt_symbol not in self.pos:
            raise Exception('vt_symbol not in pos')
        self.pos[vt_symbol] = round(self.pos[vt_symbol], self.round_size)
        return self.pos[vt_symbol]

    def get_target(self, vt_symbol):
        if vt_symbol not in self.target:
            raise Exception('vt_symbol not in target')
        self.target[vt_symbol] = round(self.target[vt_symbol], self.round_size)
        return self.target[vt_symbol]

    def update_pos(self, vt_symbol, pos):
        if vt_symbol not in self.pos:
            raise Exception('vt_symbol not in pos')
        self.pos[vt_symbol] = round(pos, self.round_size)
        self.log('update_pos {}'.format(self.pos))
        return 0

    def get_boll(self, write_log):
        
        self.spread_long_mid = 0
        self.spread_long_up = self.spread_long_mid + self.arbi_high
        self.spread_long_down = self.spread_long_mid + self.arbi_low

        self.spread_short_mid = 0
        self.spread_short_up = self.spread_short_mid  + self.arbi_high
        self.spread_short_down = self.spread_short_mid  + self.arbi_low

        if write_log:
            self.log('BOLL long: {} {} {} short: {} {} {}'.format(
                self.spread_long_mid, self.spread_long_up, self.spread_long_down,
                self.spread_short_mid, self.spread_short_up, self.spread_short_down), type='tick')

    def _fill_queue(self, tick, group_id):
        if group_id != self.group_id:
            raise Exception("check group id")
            
        vt_symbol = tick['vt_symbol']
        STORE_QUEUE = 100
        if vt_symbol == self.leg1_symbol:
            self.first_queue.append(tick)
        elif vt_symbol == self.leg2_symbol:
            self.second_queue.append(tick)
        
        if len(self.first_queue) > STORE_QUEUE:
            self.first_queue[-STORE_QUEUE:]
        if len(self.second_queue) > STORE_QUEUE:
            self.second_queue[-STORE_QUEUE:]

    def on_start(self):
        # already start
        if self.trading:
            return 0

        self.init = True
        self.trading = True
        self.round_size = list(str(min(self.fix_sizes))).count('0') + 2

        self.log("# Start:")
        self.log("\tgroup_id: {}".format(self.group_id))
        self.log("\tpos: {}".format(self.pos))
        self.log("\ttarget: {}".format(self.target))
        self.log("\tround_size: {}".format(self.round_size))

        return 0

    def silent(self):
        now_time = datetime.now().time()
        silent_times = [
            [time(7,59,30),     time(8,3,0)],
            [time(0,0,0),       time(0, 3,0)],
            [time(15,59,30),    time(16, 3,0)],
            [time(23,59,30),    time(23,59,59,999999)]
        ]
        for slient_time in silent_times:
            [start_time, end_time] = slient_time
            if now_time >= start_time and now_time <= end_time:
                self.last_err_alerts = datetime.now()
                return True
        return False

    def err_alert(self):
        if not self.trading:
            return
        self.last_err_alerts = datetime.now()
        self.log("# Err Alert: {}".format(self.last_err_alerts))
        self.action = {}
        self.target = {k:v for k,v in self.pos.items()}

    def get_err_alert(self):      

        if abs(self.last_err_alerts - datetime.now()) > timedelta(minutes=3):
            return False

        return True

    def target_shift(self):
        curr_leg_symbols = [self.leg1_symbol, self.leg2_symbol]
        for i in range(len(curr_leg_symbols)):
            leg_sbl = curr_leg_symbols[i]
            leg_pos = self.get_pos(leg_sbl)
            target_pos = self.get_target(leg_sbl)
            if leg_pos != target_pos:
                return True
        return False

    def huge_price_fluct(self, leg_tick):
        is_huge_fluct = False
        if leg_tick['ask_price'] == 0:
            is_huge_fluct =  True
        if leg_tick['bid_price'] == 0:
            is_huge_fluct =  True
        if abs(leg_tick['close_price'] - leg_tick['ask_price']) > self.fix_fluct:
            is_huge_fluct =  True
        if abs(leg_tick['close_price'] - leg_tick['bid_price']) > self.fix_fluct:
            is_huge_fluct =  True

        if is_huge_fluct:
            self.hug_price_time = datetime.now()
        else:
            if abs(self.hug_price_time - datetime.now()) < timedelta(seconds=30):
                is_huge_fluct = True

        if is_huge_fluct:
            self.log('\thuge fluct ask_price: {} {}'.format(leg_tick['ask_price'], leg_tick['bid_price']), type='tick')
        return is_huge_fluct

    def on_action(self, leg1_tick, leg2_tick, write_log=True):
        if self.silent():
            self.target = {k:v for k,v in self.pos.items()}
            return 0

        # price margin too large 
        if self.huge_price_fluct(leg1_tick):
            return 0
        if self.huge_price_fluct(leg2_tick):
            return 0

        trade_attemp = False
        # action decision
        curr_leg_ticks = [leg1_tick, leg2_tick]
        curr_leg_symbols = [self.leg1_symbol, self.leg2_symbol]
        for i in range(len(curr_leg_symbols)):
            leg_sbl = curr_leg_symbols[i]
            leg_tick = curr_leg_ticks[i]

            leg_pos = self.get_pos(leg_sbl)
            target_pos = self.get_target(leg_sbl)
            diff_pos = target_pos - leg_pos

            if diff_pos != 0:
                trade_attemp = True

            if leg_pos == 0:
                if diff_pos > 0:
                    self.action[leg_sbl] = {'action': 'buy',  'symbol': leg_sbl, 'target_pos': target_pos, 'price': leg_tick['ask_price'], 'direction': 'long'}
                elif diff_pos < 0:
                    self.action[leg_sbl] = {'action':'short', 'symbol': leg_sbl, 'target_pos': target_pos, 'price': leg_tick['bid_price'], 'direction': 'short'}
            else:
                if diff_pos > 0:
                    self.action[leg_sbl] = {'action':'cover', 'symbol': leg_sbl, 'target_pos': target_pos, 'price': leg_tick['ask_price'], 'direction': 'long'}
                elif diff_pos < 0:
                    self.action[leg_sbl] = {'action': 'sell', 'symbol': leg_sbl, 'target_pos': target_pos, 'price': leg_tick['bid_price'], 'direction': 'short'}

        if self.get_err_alert():
            self.action = {}
            self.target = {k:v for k,v in self.pos.items()}
            self.log('# Action: server trying get_err_alert')
            return 0

        if trade_attemp:
            self.log('server trying publish')
            self.publish("action", str(datetime.now()))
        
        return 0

    def send_tick(self, tick, group_id=0):
        '''
            First:            Second:
                ask: 102            ask: 101
                bid: 98             bid: 97

            long_spread:  buy  First sell Second   102 - 97:  5
            short_spread: sell First bug  Second   98 - 101: -3
        '''

        if group_id != self.group_id:
            return 0          

        self._fill_queue(tick, group_id)
        
        if len(self.first_queue) < 1 or len(self.second_queue) < 1:
            return 0

        leg1_tick = self.first_queue[-1]
        leg2_tick = self.second_queue[-1]

        # ignore delay tick
        first_end_time = datetime.strptime(leg1_tick['datetime'], "%Y-%m-%d %H:%M:%S.%f")
        second_end_time = datetime.strptime(leg2_tick['datetime'], "%Y-%m-%d %H:%M:%S.%f")
        max_t, min_t = max(first_end_time, second_end_time), min(first_end_time, second_end_time)
        if abs(min_t - max_t) > self.delta_match:
            self.not_match_count += 1
            return 0
        self.match_count += 1

        # fill spread
        spread_long = leg1_tick['ask_price'] - leg2_tick['bid_price']
        spread_short = leg1_tick['bid_price'] - leg2_tick['ask_price']
        
        move_bias = self.move_bias
        move_spead_data = (spread_long  + spread_short) / 2
        self.move_spead[:-1]  = self.move_spead[1:]
        self.move_spead[-1] = move_spead_data
        move_spead_mean  = self.move_spead.mean() 
        move_spead_std  = self.move_spead.std()

        if not self.trading:
            return 0
        
        write_log = False
        if first_end_time.second == 0 or spread_short >= self.spread_long_up or spread_long <= self.spread_short_down:
            write_log = True
        
        if not self.silent() and write_log:
            self.log('# Server: match ticks {} {}'.format(first_end_time, second_end_time), type='tick')
            self.log('\tserver spread: {} {} move_mean:{} move_std:{}'.format(spread_long, spread_short, move_spead_mean, move_spead_std), type='tick')
            self.log('\tpos: {} target: {}'.format(self.pos, self.target), type='tick')
            self.log('\tnot_match_count: {} match_count: {}'.format(self.not_match_count, self.match_count), type='tick')

        # get boll channel
        self.get_boll(write_log=write_log)

        # action decision
        leg1_pos, leg2_pos = self.get_pos(self.leg1_symbol), self.get_pos(self.leg2_symbol)
        pos_dif, pos_max = leg1_pos - leg2_pos, max(abs(leg1_pos), abs(leg2_pos))

        if pos_max == 0:
            if spread_short >= self.spread_long_up and (move_spead_mean + move_bias) >= self.spread_long_up:
                self.target[self.leg1_symbol] = -self.fix_sizes[0]
                self.target[self.leg2_symbol] = self.fix_sizes[1]
            elif spread_long <= self.spread_short_down and (move_spead_mean - move_bias) <= self.spread_short_down:
                self.target[self.leg1_symbol] = self.fix_sizes[0]
                self.target[self.leg2_symbol] = -self.fix_sizes[1]
        elif pos_max != 0 and pos_dif > 0:
            if spread_short >= self.spread_long_up and (move_spead_mean + move_bias) >= self.spread_long_up:
                self.target[self.leg1_symbol] = 0
                self.target[self.leg2_symbol] = 0
        elif pos_max != 0 and pos_dif < 0:
            if spread_long <= self.spread_short_down and (move_spead_mean - move_bias) <= self.spread_short_down:
                self.target[self.leg1_symbol] = 0
                self.target[self.leg2_symbol] = 0

        self.on_action(leg1_tick, leg2_tick, write_log=write_log)

        return 0

    def get_action(self):
        if not self.trading:
            return {}
        if not self.target_shift():
            return {}
        self.log("# Server Action: {}".format(self.action))
        self.log("\tpos: {} target: {}".format(self.pos, self.target))
        return self.action
    
    def on_pos(self):
        return self.pos

    def send_status(self, trade_status, group_id=0):
        self.log('# Server Update Pos')
        if group_id != self.group_id:
            raise Exception('group-id assign failed')

        vt_symbol = trade_status['vt_symbol']
        if vt_symbol not in self.vt_symbols:
            raise Exception('vt_symbol assign failed')

        trade_order_id = trade_status['trade_order_id']
        if trade_order_id in self.trade_order_ids:
            self.log('trade_order_id inside {}'.format(trade_order_id))
            return
        self.trade_order_ids = self.trade_order_ids[-500:]
        self.trade_order_ids.append(trade_order_id)

        price = trade_status['price']
        trade_pos = trade_status['trade_pos']
        origin_pos = self.get_pos(vt_symbol)
        self.update_pos(vt_symbol, origin_pos + trade_pos)

        self.trade_prices[vt_symbol] = {'price':  price,  'time': datetime.now()}

        try:
            trade_delta_time= self.trade_prices[self.leg1_symbol]['time'] - self.trade_prices[self.leg2_symbol]['time']
            trade_delta_price= self.trade_prices[self.leg1_symbol]['price'] - self.trade_prices[self.leg2_symbol]['price']
        except Exception as e:
            trade_delta_time = 0
            trade_delta_price = 0

        self.dump_status()
        self.log('# Server Trade')
        self.log('\tpos: {} target: {}'.format(self.pos, self.target))
        self.log('\tdelta_time: {} spread: {}'.format(trade_delta_time, trade_delta_price))
        return


def run_server(config_settings):  

    vt_symbols = config_settings['vt_symbols']
    group_id = config_settings['group_id']
    fix_sizes = config_settings['fix_sizes']
    arbi_high = config_settings['arbi_high']
    arbi_low = config_settings['arbi_low']
    fix_fluct = config_settings['fix_fluct']
    move_bias = config_settings['move_bias']

    rep_address = "tcp://*:2019"
    pub_address = "tcp://*:4102"
    
    ts = TestServer(
        vt_symbols,
        group_id, 
        fix_sizes,
        arbi_high,
        arbi_low,
        fix_fluct,
        move_bias
    )
    ts.start(
        rep_address,
        pub_address,
    )
    while 1:
        ts.publish("heart-beat", "")
        sleep(1)


