from datetime import datetime,  timedelta
import os
from email.message import EmailMessage
import smtplib
from enum import Enum
import time


def load_email_config():
    email_config_path = os.path.join('configs', 'email.json')
    with open(email_config_path, 'r') as f:
        email_setting = json.load(f)
    return email_setting


def email_test():
    email_setting = load_email_config()
    SETTINGS = {}
    SETTINGS.update(email_setting)

    msg = EmailMessage()
    msg["From"] = SETTINGS["email.sender"]
    msg["To"] = SETTINGS["email.receiver"]
    msg["Subject"] = 'Email Test'
    msg.set_content('Email Test')

    with smtplib.SMTP_SSL(
        SETTINGS["email.server"], SETTINGS["email.port"]
    ) as smtp:
        smtp.login(
            SETTINGS["email.username"], SETTINGS["email.password"]
        )
        smtp.send_message(msg)

def email_alert(content):
    email_setting = load_email_config()
    SETTINGS = {}
    SETTINGS.update(email_setting)

    try:
        content = content[:200] + content[-200:]
    except Exception as e:
        pass

    try:
        msg = EmailMessage()
        msg["From"] = SETTINGS["email.sender"]
        msg["To"] = SETTINGS["email.receiver"]
        msg["Subject"] = 'USDT'
        msg.set_content(str(content))

        with smtplib.SMTP_SSL(
            SETTINGS["email.server"], SETTINGS["email.port"]
        ) as smtp:
            smtp.login(
                SETTINGS["email.username"], SETTINGS["email.password"]
            )
            smtp.send_message(msg)
    except:
        pass

class VNLogStatus(Enum):
    NO_LOG = 0
    BLACK_WORD = 1
    IO_EXCEPT = 2
    SUCC = 3
    TRADE = 4
    START = 5
    TITLE = 6


def vnlog_checking(fifo_f):
    black_words = [
        '行情订阅失败',
        '错误',
        '失败',
        'Exception',
        'Error',
        'Traceback',
    ]
    key_word = 'TradeData'
    start_word = 'Arbi-Quant'
    title_word = '账户ID'

    status = []
    ctx = ''
    try:
        line = fifo_f.read()
        if line.strip() == '':
            return status, ctx
        print(line)
        for bw in black_words:
            if bw in line:
                print('black word', line)
                status.append(VNLogStatus.BLACK_WORD)
                ctx += ('VNLogStatus.BLACK_WORD\n'+line) 
        if key_word in line:
            status.append(VNLogStatus.TRADE)
            ctx += ('VNLogStatus.TRADE\n'+line)
        if start_word in line:
            status.append(VNLogStatus.START)
            ctx += ('VNLogStatus.START\n'+line)
        if title_word in line:
            status.append(VNLogStatus.TITLE)
            ctx += ('VNLogStatus.TITLE\n'+line)
    except IOError as e:
        return [VNLogStatus.IO_EXCEPT], 'VNLogStatus.FIFO_IO_EXCEPT\n' 
    except KeyboardInterrupt as e:
        raise 

    if status == []:
        return [VNLogStatus.SUCC], 'VNLogStatus.SUCC\n'
    else:
        return status, ctx


if __name__ == '__main__':
    fifo_path = 'terminal.fifo'
    TITLE = 'None'

    while True:
        time.sleep(0.001)
        if os.path.exists(fifo_path):
            break

    if not os.path.exists(fifo_path):
        print('not log ', fifo_path)
        ctx = 'VNLogStatus.NO_LOG\n'+fifo_path
        email_alert(ctx)
    
    fifo_f = open(fifo_path, 'r')

    datetime_last = datetime.now()

    while True:
        time.sleep(0.1)

        vnlogstatus, ctx = vnlog_checking(fifo_f)

        if VNLogStatus.TITLE in vnlogstatus:
            TITLE = ctx
        if VNLogStatus.START in vnlogstatus:
            ctx = "CTA 启动 \n {}\n".format(TITLE) + ctx
            email_alert(ctx)
            ctx = ''
        if VNLogStatus.NO_LOG in vnlogstatus \
            or VNLogStatus.BLACK_WORD in vnlogstatus  \
            or VNLogStatus.IO_EXCEPT in vnlogstatus:

            if abs(datetime.now() - datetime_last) < timedelta(seconds=10):
                continue
            datetime_last = datetime.now()

            ctx = "CTA 错误 \n {}\n".format(TITLE) + ctx
            email_alert(ctx)
            ctx = ''

        if VNLogStatus.TRADE in vnlogstatus:
            ctx = "CTA 成交 \n {}\n".format(TITLE) + ctx
            email_alert(ctx)
            ctx = ''

