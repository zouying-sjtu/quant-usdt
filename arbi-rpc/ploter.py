
import os
import sys
import json
import argparse
import multiprocessing
from time import sleep
from datetime import datetime, time
from logging import INFO

from vnpy.event import EventEngine
from vnpy.trader.setting import SETTINGS
from vnpy.trader.engine import MainEngine

# from vnpy.gateway.binances import BinancesGateway
# from vnpy.gateway.huobis import HuobisGateway

from modified import BinancesGateway
from modified import HuobisGateway

from vnpy.app.cta_strategy import CtaStrategyApp
from vnpy.app.cta_strategy.base import EVENT_CTA_LOG

from vnpy.rpc import RpcClient
from vnpy.rpc import RpcServer

from strategies.arbi_ploter_strategy import ArbiPloterStrategy
from ploter_server import run_server

SETTINGS["log.active"] = True
SETTINGS["log.level"] = INFO
SETTINGS["log.console"] = True
SETTINGS["log.file"] = True


def run_child(
        class_name, 
        gateway, 
        connect_setting,
        gateway_name, 
        config_child_settings
    ):
    """
        Running in the child process.
    """
    vt_symbol = config_child_settings['vt_symbol']
    fix_size = config_child_settings['fix_size']
    group_id = config_child_settings['group_id']
    price_add = config_child_settings['price_add']

    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)
    main_engine.add_gateway(gateway)
    cta_engine = main_engine.add_app(CtaStrategyApp)
    main_engine.write_log("Arbi-Quant on USDT Start")

    # cta_engine loading
    cta_engine.load_strategy_class_from_module(module_name='strategies')
    strategy_list = cta_engine.get_all_strategy_class_names()
    main_engine.write_log("\n Exist Strategy Classes {}".format(strategy_list))

    log_engine = main_engine.get_engine("log")
    event_engine.register(EVENT_CTA_LOG, log_engine.process_log_event)
    main_engine.write_log("Main Engine Register")

    main_engine.connect(connect_setting, gateway_name)
    main_engine.write_log("Gateway Connect {}".format(gateway_name))

    sleep(10)

    cta_engine.init_engine()
    main_engine.write_log("Gataway {} Init".format(gateway_name))

    # ArbiSingleStrategy or ArbiSingleTickStrategy
    cta_engine.strategies = {}
    cta_engine.add_strategy(
        class_name = class_name, 
        strategy_name = "arbi-{}-{}".format(group_id, vt_symbol), 
        vt_symbol = vt_symbol,
        setting = {
            "fixed_size": fix_size, 
            "xmin": 1, 
            "group_id":group_id,
            "price_add": price_add,
            "gateway_name": gateway_name,
        },
    )

    cta_engine.init_all_strategies()
    sleep(60)   # Leave enough time to complete strategy initialization
    main_engine.write_log("{} Waiting 60s".format(gateway_name))

    cta_engine.start_all_strategies()
    main_engine.write_log("{} All Strategies Start".format(gateway_name))

    while True:
        try:
            sleep(10)
            trading = True
        except KeyboardInterrupt as e:
            print('KeyboardInterrupt')
            print(e)
            trading = False
        
        if not trading:
            print("Not trading and Close")
            main_engine.close()
            sys.exit(0)

def run_parent(config_settings):
    """
    Running in the parent process.
    """
    print("# RUN parent")
    for k,v in config_settings.items():
        if type(v) != dict:
            print('{}:\t{}'.format(k,v))
        else:
            print('{}:'.format(k))
            for k_1, v_1 in v.items():
                print('\t{}:\t{}'.format(k_1, v_1))
    print('-'*10)

    child_process_0 = None
    child_process_1 = None
    child_server = None
    
    trading = True
    
    while True:
        if trading and child_server is None:
            print("# Starting Server")
            child_server = multiprocessing.Process(
                target=run_server, 
                args=(
                       config_settings,
                    ))
            child_server.start()
            print("# Started Server")
        if not trading and child_server is not None:
            if not child_server.is_alive():
                child_server = None
                print("# Closed Server")

        # Start child process in trading period
        if trading and child_process_0 is None:
            print("# Starting Client 0 ")
            class_name = config_settings['class_name']
            gateway_class = config_settings['gateways'][0]
            gateway_name = config_settings['gateway_names'][0]
            gateway_setting = config_settings['gateway_settings'][0]
            config_child_settings = {
                'vt_symbol': config_settings['vt_symbols'][0],
                'fix_size': config_settings['fix_sizes'][0],
                'group_id': config_settings['group_id'],
                'price_add': config_settings['price_add'],
            }
            child_process_0 = multiprocessing.Process(
                target=run_child, 
                args=(
                    class_name, gateway_class, gateway_setting, gateway_name, config_child_settings
                ))
            child_process_0.start()
            print("# Started Client 0 ")
            
        if not trading and child_process_0 is not None:
            if not child_process_0.is_alive():
                child_process_0 = None
                print("# Closed Client 0 ")

        if trading and child_process_1 is None:
            print("# Starting Client 1 ")
            class_name = config_settings['class_name']
            gateway_class = config_settings['gateways'][1]
            gateway_name = config_settings['gateway_names'][1]
            gateway_setting = config_settings['gateway_settings'][1]

            config_child_settings = {
                'vt_symbol': config_settings['vt_symbols'][1],
                'fix_size': config_settings['fix_sizes'][1],
                'group_id': config_settings['group_id'],
                'price_add': config_settings['price_add'],
            }

            child_process_1 = multiprocessing.Process(
                target=run_child, 
                args=(
                    class_name, gateway_class, gateway_setting, gateway_name, config_child_settings, 
                ))
            child_process_1.start()
            print("# Started Client 1 ")
            
        if not trading and child_process_1 is not None:
            if not child_process_1.is_alive():
                child_process_1 = None
                print("# Closed Client 1 ")

        sleep(5)


def init_ploter_dir():
    root = '.vntrader'
    ploter_dir = os.path.join(root, 'ploters')
    for dir_ in [root, ploter_dir]:
        if not os.path.exists(dir_):
            os.mkdir(dir_)


def get_candidates():
    cand = [
        ["ETHUSDT.BINANCE", "ETH-USDT.HUOBI"],
        ["XRPUSDT.BINANCE", "XRP-USDT.HUOBI"],
        ["BTCUSDT.BINANCE", "BTC-USDT.HUOBI"],
        ["BCHUSDT.BINANCE", "BCH-USDT.HUOBI"],
        ["EOSUSDT.BINANCE", "EOS-USDT.HUOBI"],
        ["LTCUSDT.BINANCE", "LTC-USDT.HUOBI"],
        ["ETCUSDT.BINANCE", "ETC-USDT.HUOBI"],
        ["LINKUSDT.BINANCE", "LINK-USDT.HUOBI"],
        ["XMRUSDT.BINANCE", "XMR-USDT.HUOBI"],
        ["DASHUSDT.BINANCE", "DASH-USDT.HUOBI"],
        ["ADAUSDT.BINANCE", "ADA-USDT.HUOBI"],
        ["ZECUSDT.BINANCE", "ZEC-USDT.HUOBI"],
        ["ATOMUSDT.BINANCE", "ATOM-USDT.HUOBI"],
        ["NEOUSDT.BINANCE", "NEO-USDT.HUOBI"],
    ]
    return cand


def default_config(vt_symbols):
    account_setting_path = os.path.join('configs', 'account.json')
    with open(account_setting_path, 'r') as f:
        account = json.load(f)
    binances_settting   = account['binances_settting']
    huobis_setting      = account['huobis_setting']

    class_name = 'ArbiPloterStrategy'
    config_settings = {
        'class_name': class_name, 
        'vt_symbols': vt_symbols,
        'gateway_names': ['BINANCES', 'HUOBIS'],
        'gateways': [BinancesGateway, HuobisGateway],
        'gateway_settings': [binances_settting, huobis_setting],
        'fix_sizes': [1, 1],
        'arbi_window': 100,
        'arbi_dev': 0.0,
        'arbi_high': 0.0,
        'arbi_low': 0.0,
        'price_add': 0.0,
        'group_id': 0,
        'fix_fluct': 0.0
    }
    return config_settings


if __name__ == "__main__":

    parser = argparse.ArgumentParser('argument for training')
    parser.add_argument('--func', type=str, default="bar", help='bar or tick')
    opt = parser.parse_args()

    init_ploter_dir()

    cand = get_candidates()
    vt_symbols = cand[0]

    config_settings = default_config(vt_symbols)

    run_parent(config_settings)