## Quant-USDT
cross market arbitrary strategies with vnpy framework


# Trading
0. 为什么用RPC：希望能兼容多种系统、多种框架、引入GPU服务器等
1. 目前尝试了Binance和Huobi这2个交易所（感觉小交易所更有机会）
2. 目前尝试了如下3个品种，只能勉强cover住手续费 QAQ：
    a. BTC/USDT
    b. ETH/USDT
    c. NEO/USDT


# Start With:
1. 把自己账户信息填入：configs/account.json (仿照 account.bak.json)
2. 用 run_plot.sh 画出价差波形图，大致评估一下自己喜欢的品种对、所跨的市场、预设的参数
3. 把自己希望交易的参数填入：configs/params.json
4. 用 run_trade.sh 启动2个client和1个server，用于同时交易2个市场的货币
5. （可选）把自己邮箱信息填入：configs/email.json (仿照 email.bak.json)
6. （可选）用 run_alert.sh 启动1个7x24小时监督脚本，如果出错，发邮件通知


# Demo
1. python scripts/run_plot.sh
2. python scripts/run_trade.sh
3. python scripts/run_alert.sh


# P.S. 警告
1. 不能直接用于数字货币跨市套利，现数字货币手续费极高！
2. 若想在同一台电脑使用 >1 个配对，需要手动修改端口号（我有空改一下）
3. 需要配置代理，或者在境外使用，否则无法连接大部分交易服务器


# 合作与计划
1. 小众品种 + 小众交易所 （波动大）
2. 商品期货 （手续费低）
3. 跨品种 （优化和推断，ML类的方案）


# Contact 联系
1. 希望有大佬能指点下小弟，或者来一起玩耍
2. Author: Ying Zou & Lorne，975104083@qq.com

