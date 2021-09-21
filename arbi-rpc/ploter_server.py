#coding=gbk

import os
import pdb
import copy
import sys
import json
import argparse
import multiprocessing
import numpy as np

import logging
from logging import INFO
from time import sleep
from datetime import date, datetime, time, timedelta
import matplotlib.pyplot as plt
from matplotlib.pyplot import MultipleLocator

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

        self.not_match_count = 0
        self.match_count = 0

        self.first_queue = []
        self.second_queue = []
        self.finish = {k:0 for k in vt_symbols}

        self.move_spead = np.zeros([30])
        # trade status
        self.init = False
        self.trading = False

        self.vt_symbols = vt_symbols
        self.leg1_symbol = vt_symbols[0]
        self.leg2_symbol = vt_symbols[1]
        self.group_id = group_id

        self.delta_match = timedelta(seconds=0, microseconds=350000)
        self.hug_price_time = datetime.now()

        root_dir = os.path.dirname(os.path.abspath(__file__))
        vntrader_dir = os.path.join(root_dir, '.vntrader')
        if os.path.exists(vntrader_dir):
            print(vntrader_dir)

        # logger
        self.log_dir = os.path.join(vntrader_dir, 'ploters')
        self.log_server_dir =  os.path.join(self.log_dir, "{}_{}".format(self.leg1_symbol, self.leg2_symbol))
        for dir_ in [self.log_dir, self.log_server_dir]:
            if not os.path.exists(dir_):
                try:
                    os.mkdir(dir_)
                except Exception as e:
                    print(e)
        self._init_logger()

        # server register
        self.register(self.send_bar)
        self.register(self.on_start)

    
    def _init_logger(self):
        self.log_server_dir =  os.path.join(self.log_dir, "{}_{}".format(self.leg1_symbol, self.leg2_symbol))
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

        self.log_bar_file = os.path.join(self.log_server_dir, 'server-bar-{}.log'.format(self.group_id))
        self.logger_bar = logging.getLogger("server-bar")
        self.logger_bar.setLevel(level=logging.INFO)
        handler_bar = logging.FileHandler(self.log_bar_file)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        handler_bar.setFormatter(formatter)
        self.logger_bar.addHandler(handler_bar)


    def log(self, msg,  type='default'):

        if type == 'default':
            self.logger.info(str(msg))
        elif type == 'bar':
            self.logger_bar.info(str(msg))


    def _fill_queue(self, bar, group_id):
        if group_id != self.group_id:
            raise Exception("check group id")
            
        vt_symbol = bar['vt_symbol']

        if vt_symbol == self.leg1_symbol:
            self.first_queue.append(bar)
        elif vt_symbol == self.leg2_symbol:
            self.second_queue.append(bar)
        

    def ignore_timestamp(self, leg_time):
        ignore_times = [
            '07:59',
            '08:00',
            '08:01',
            '08:02',
            '08:03',
            '15:59',
            '16:00',
            '16:01',
            '16:02',
            '16:03',
            '23:59',
            '00:00',
            '00:01',
            '00:02',
            '00:03',
        ]
        leg_time = datetime.strptime(leg_time, "%Y-%m-%d %H:%M:%S.%f")
        leg_time = leg_time.strftime("%H:%M")
        if leg_time in ignore_times:
            return True
        return False


    def on_plot(self):

        f_ptr, s_ptr = 0, 0

        print("len(self.first_queue)", len(self.first_queue), "len(self.second_queue", len(self.second_queue))

        spread_data, spread_data_per = [], []
        avg_price = sum([b['close_price'] for b in self.first_queue[:100]])/100

        while f_ptr < len(self.first_queue) and s_ptr < len(self.second_queue):
            
            # send flag to plot
            leg1_bar = self.first_queue[f_ptr]
            leg2_bar = self.second_queue[s_ptr]

            # ignore delay bar
            first_end_time = datetime.strptime(leg1_bar['datetime'], "%Y-%m-%d %H:%M:%S.%f")
            second_end_time = datetime.strptime(leg2_bar['datetime'], "%Y-%m-%d %H:%M:%S.%f")

            if first_end_time < second_end_time:
                f_ptr += 1
            else:
                s_ptr += 1

            if self.ignore_timestamp(leg1_bar['datetime']):
                continue
            if self.ignore_timestamp(leg2_bar['datetime']):
                continue

            max_t, min_t = max(first_end_time, second_end_time), min(first_end_time, second_end_time)
            if abs(min_t - max_t) > self.delta_match:
                self.not_match_count += 1
                continue

            self.match_count += 1

            # fill spread
            move_spead_data = (leg1_bar['close_price'] - leg2_bar['close_price']) 
            move_spead_data_per = (leg1_bar['close_price'] - leg2_bar['close_price']) / avg_price * 10000

            self.move_spead[:-1]  = self.move_spead[1:]
            self.move_spead[-1] = move_spead_data
            move_spead_mean  = self.move_spead.mean() 
            move_spead_std  = self.move_spead.std()

            spread_data.append(move_spead_data)
            spread_data_per.append(move_spead_data_per)

            self.log('spread: {}\tmove_mean:{}\tmove_std:{}\ttime:{}_{}'.format(move_spead_data, move_spead_mean, move_spead_std, first_end_time, second_end_time), type='bar')

        spread_data_cp = copy.deepcopy(spread_data)
        spread_data_per_cp = copy.deepcopy(spread_data_per)

        spread_data.sort()
        spread_data_per.sort()

        print('spread_data min - max (%%)', 
            spread_data[0], 
            spread_data[10], 
            spread_data[20],  
            spread_data[-20], 
            spread_data[-10],  
            spread_data[-1], 
        )

        print('spread_data_per min - max (%%)', 
            spread_data_per[0], 
            spread_data_per[10], 
            spread_data_per[20],  
            spread_data_per[-20], 
            spread_data_per[-10],  
            spread_data_per[-1], 
        )

        title1 = '{} - {} %%'.format(round(spread_data_per[20], 2), round(spread_data_per[-20], 2))
        title2 = '{} - {}'.format(round(spread_data[20], 2), round(spread_data[-20], 2))

        self.plot_bar(title1, title2, spread_data_cp, spread_data_per_cp)
        print("match_count,  not_match_count",  self.match_count,  self.not_match_count)


    def on_start(self):
        # already start
        if self.trading:
            return 0

        self.init = True
        self.trading = True
        self.round_size = list(str(min(self.fix_sizes))).count('0') + 1

        self.log("# Start:")
        self.log("\tgroup_id: {}".format(self.group_id))
        self.log("\tround_size: {}".format(self.round_size))

        return 0


    def send_bar(self, bar, group_id=0):
        '''
            First:            Second:
                ask: 102            ask: 101
                bid: 98             bid: 97

            long_spread:  buy  First sell Second   102 - 97:  5
            short_spread: sell First bug  Second   98 - 101: -3
        '''
        
        if group_id != self.group_id:
            return 0          

        vt_symbol = bar['vt_symbol']

        if bar['finish'] == 1:
            self.finish[vt_symbol] = 1
        
        if self.finish[self.leg1_symbol] == 1 and self.finish[self.leg2_symbol] == 1:
            self.on_plot()
            self.log("# Finish Plot")
            print("# Finish Plot")
            exit(0)

        self._fill_queue(bar, group_id)

    def plot_bar(self, title1, title2, spread_data, move_spead_data_per):
        title1 = "{}_{}\n{}".format(self.leg1_symbol, self.leg2_symbol, title1)
        title2 = "percent %%\n{}".format(title2)

        spread_std = np.array(spread_data).std()
        spread_mean =  np.array(spread_data).mean()
        spread_top, spread_bottom = spread_mean + 3 * spread_std, spread_mean - 3 * spread_std
        spread_data = [max(min(v, spread_top), spread_bottom) for v in spread_data]

        print('spread_data', len(spread_data), min(spread_data), max(spread_data))

        # for spread_data
        ax1=plt.subplot(2,1,1)
        plt.plot(spread_data, color='r', label='spread_data', linewidth=0.2)
        plt.title(title1)
        plt.legend(fontsize=8)      
        
        print('move_spead_data_per', len(move_spead_data_per), min(move_spead_data_per), max(move_spead_data_per))

        # for spread_data
        ax2=plt.subplot(2,1,2)
        plt.plot(move_spead_data_per, color='b', label='spread_data_per', linewidth=0.2)
        plt.ylim(min(move_spead_data_per)-1, max(move_spead_data_per)+1)
        plt.title(title2)
        plt.legend(fontsize=8)  

        save_fig_path = os.path.join(self.log_server_dir, 'spread.png')
        plt.savefig(save_fig_path, dpi=1000)
        plt.close()



def run_server(config_settings):  

    vt_symbols = config_settings['vt_symbols']
    group_id = config_settings['group_id']
    fix_sizes = config_settings['fix_sizes']
    arbi_high = config_settings['arbi_high']
    arbi_low = config_settings['arbi_low']
    fix_fluct = config_settings['fix_fluct']

    rep_address = "tcp://*:2039"
    pub_address = "tcp://*:4302"
    
    ts = TestServer(
        vt_symbols,
        group_id, 
        fix_sizes,
        arbi_high,
        arbi_low,
        fix_fluct,
    )
    ts.start(
        rep_address,
        pub_address,
    )
    while 1:
        ts.publish("heart-beat", "")
        sleep(1)


