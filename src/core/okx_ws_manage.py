import base64
import hmac
import hashlib
import json
import time
from datetime import datetime,timedelta
import os
import random

import websocket
import threading
import requests


import sqlite3

import pandas as pd
import numpy as np

from okx.Trade import TradeAPI
from okx.MarketData import MarketAPI
from okx.Account import AccountAPI

import okx_strategy


import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)
import logging
from logging.handlers import RotatingFileHandler


m_logger = logging.getLogger()
m_logger.setLevel(logging.WARNING) 
m_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s') 
m_file_handler = logging.FileHandler('/Users/mac/Downloads/stocks/ex_okx/okx_ws_manage.log') 
m_file_handler = RotatingFileHandler(
    '/Users/mac/Downloads/stocks/ex_okx/okx_ws_manage.log', 
    maxBytes=100*1024*1024,  # 100 MB
    backupCount=3  # keep up to 3 backup files
)
m_file_handler.setFormatter(m_formatter)
m_logger.addHandler(m_file_handler)

flag = "0" 
# Master API credentials from environment
master_apikey = os.getenv('OKX_API_KEY', '')
master_secretkey = os.getenv('OKX_SECRET', '')
master_passphrase = os.getenv('OKX_PASSPHRASE', '')

if not all([master_apikey, master_secretkey, master_passphrase]):
    m_logger.error("OKX API credentials not found in environment variables")


def get_announcements(api_key, secret_key, passphrase, ann_type=None, page=1):
    url = "https://www.okx.com/api/v5/support/announcements"
    

    # Get the current timestamp in ISO format with milliseconds
    timestamp = datetime.utcnow().isoformat(timespec='milliseconds') + 'Z'
    method = 'GET'
    request_path = '/api/v5/support/announcements'
    prehash = timestamp + method + request_path +''
    signature = hmac.new(secret_key.encode(), prehash.encode(), hashlib.sha256).digest()
    signature =base64.b64encode(signature).decode()

    # Prepare the headers
    headers = {
        'OK-ACCESS-KEY': api_key,
        'OK-ACCESS-SIGN': signature,
        'OK-ACCESS-TIMESTAMP': timestamp,
        'OK-ACCESS-PASSPHRASE': passphrase
    }

    # Make the GET request
    response = requests.get(url, headers=headers)

    # Check if the request was successful
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error: {response.status_code}, {response.text}")
        return None





def prepare():

    global candle_dict
    global is_candle_clear
    global cryptos
    global conn

    num_crypto = len(cryptos)

    now = datetime.now()


    if is_candle_clear['1H'] is None or is_candle_clear['1H'] != now.hour:
        is_candle_clear['1H'] = now.hour
        candle_dict['1H'] = pd.DataFrame(columns=candle_dict['1H'].columns)


    if is_candle_clear['1D'] is None or is_candle_clear['1D'] != now.date:
        is_candle_clear['1D'] = now.date
        candle_dict['1D'] = pd.DataFrame(columns=candle_dict['1D'].columns)

def update_tick(df,data):
    try:
        new_row = data[0]
        df.loc[new_row['instId']] = new_row
    except Exception as e:
        logging.error("update_tick:%s",e)


def update_candle(df,instId,data):
    try:
        new_row = data[0]
        df.loc[instId] = new_row
    except Exception as e:
        logging.error("update_candle:%s",e)

def sign(key : str, secret : str, passphrase : str):

    ts = str(int(datetime.now().timestamp()))
    args = dict(apiKey=key, passphrase=passphrase, timestamp=ts)
    sign = ts + 'GET' + '/users/self/verify'
    mac = hmac.new(bytes(secret, encoding='utf8'), bytes(sign, encoding='utf-8'), digestmod='sha256')
    args['sign'] = base64.b64encode(mac.digest()).decode(encoding='utf-8')
    return args

def send(ws, op : str, args : list):

    subs = {"op": op, "args": args}
    ws.send(json.dumps(subs))

def send_ping(ws):
    while True:
        time.sleep(20)  # Ping every 20 seconds
        try:
            ws.send("ping")
        except websocket.WebSocketConnectionClosedException:
            break

def connect_websocket(url,on_message,on_open):

    while True:
        try:
            # Create WebSocket connection
            ws = websocket.WebSocketApp(
                url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open
            )
            
            ping_thread = threading.Thread(target=send_ping, args=(ws,))
            ping_thread.start()
            ws.run_forever()
        except Exception as e:
            logging.error("WS Connection failed:", e)
            logging.error("Retrying in 5 seconds...")
            time.sleep(5)


def tick_message(ws, msg_string):

    global last_prices_df
    if msg_string == 'pong':return

    try:
        m = json.loads(msg_string)
        ev = m.get('event')
        data = m.get('data')

        if ev == 'error':
            logging.error("Error:%s", msg_string)
        elif ev in ['subscribe', 'unsubscribe']:
            logging.info("subscribe/unsubscribe:%s", msg_string)
        elif ev == 'login':
            logging.info('Ur Logged in')
            msg = {
                "op": "subscribe",
                "args": [{'channel':'orders', 'instType':'SPOT'}]
            }
            ws.send(json.dumps(msg))
        elif data:
            update_tick(last_prices_df,data)

    except Exception as e:
        logging.error("tick message:%s,%s",msg_string,e)
        


def candle_message(ws, msg_string):

    global candle_dict

    if msg_string == 'pong':return

    try:
        m = json.loads(msg_string)
        ev = m.get('event')
        data = m.get('data')

        if ev == 'error':
            logging.error("Error:%s", msg_string)
        elif ev in ['subscribe', 'unsubscribe']:
            logging.info("subscribe/unsubscribe:%s", msg_string)
        elif ev == 'login':
            logging.warning('Ur Logged in')
            msg = {
                "op": "subscribe",
                "args": [{'channel':'orders', 'instType':'SPOT'}]
            }
            ws.send(json.dumps(msg))
        elif data:
            channel = m.get('arg').get('channel')
            instId = m.get('arg').get('instId')

            key = channel[6:]
            update_candle(candle_dict[key],instId,data)
            # print(key,instId,data)

    except Exception as e:
        logging.error("candle message:%s,%s",msg_string,e)
        

def on_error(ws, error):
    logging.warning(f"Error: {error}")

def on_close(ws):
    logging.warning("### Closed ###")

def tick_open(ws):
    logging.warning("### Opened ###")
    global cryptos

    msg = {"op": "subscribe", "args": [{"channel": "tickers", "instId": instID} for instID in cryptos]}
    ws.send(json.dumps(msg))

def candle_open(ws):
    logging.warning("### Opened ###")
    global cryptos

    intervals = [ '1H','1D']
    msg_dict = {interval: {"op": "subscribe", "args": []} for interval in intervals}    
    
    for instID in cryptos:
        for interval in intervals:
            msg_dict[interval]["args"].append({"channel": f"candle{interval}", "instId": instID})

    for message in msg_dict.values():
        ws.send(json.dumps(message))


base_dir = '/Users/mac/Downloads/stocks/ex_okx/'

# Load cryptos
cryptos_file = os.path.join(base_dir, 'src/config', 'cryptos_selected.json')
with open(cryptos_file, 'r') as file:
    cryptos = json.load(file)



last_prices_df = pd.DataFrame(columns=['instId', 'last', 'lastSz', 'askPx', 'askSz', 'bidPx',
    'bidSz', 'open24h', 'high24h', 'low24h', 'sodUtc0', 'sodUtc8',
    'volCcy24h', 'vol24h', 'ts'])
last_prices_df.set_index('instId', inplace=True)

tick_url = 'wss://ws.okx.com:8443/ws/v5/public'   
tick_thread = threading.Thread(target=connect_websocket, args=(tick_url,tick_message,tick_open))
tick_thread.start()


candle_dict = {key: None for key in ['1H','1D']}
for each in candle_dict:
    candle_dict[each]=pd.DataFrame(columns = ['instId',"ts", "o", "h", "l", "c", "vol", "volCcy", "volCcyQuote", "confirm"])
    candle_dict[each].set_index('instId', inplace=True)

candle_url = 'wss://ws.okx.com:8443/ws/v5/business'
candle_thread = threading.Thread(target=connect_websocket, args=(candle_url,candle_message,candle_open))
candle_thread.start()


is_candle_clear =  {key: None for key in ['1H','1D']}




initial_attempts =3
for initial_attempt in range(initial_attempts):
    try:
        marketDataAPI =  MarketAPI(flag=flag)

        master_accountAPI = AccountAPI(master_apikey, master_secretkey, master_passphrase, False, flag)
        master_tradeAPI = TradeAPI(master_apikey, master_secretkey, master_passphrase, False, flag)
        marketDataAPI =  MarketAPI(flag=flag)


        break
    except Exception as e:
        m_logger.error("api initial:%s",e)
        time.sleep(1)



conn = sqlite3.connect('/Users/mac/Downloads/stocks/ex_okx/okx.db')

time.sleep(60)

while True:
 
    if random.random() < 0.05:

        announcements = get_announcements(master_apikey, master_secretkey, master_passphrase, page=1)
        announcements = announcements['data'][0]['details']
        today_start = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)

        for ann in announcements:
            if today_start <= int(ann['pTime']) and ann['annType']=='announcements-delistings':
                while True:
                    os.system("afplay /System/Library/Sounds/Glass.aiff")



    prepare()


    okx_strategy.dw_1h(candle_dict['1H'],master_tradeAPI,conn,marketDataAPI,last_prices_df)
    # okx_strategy.dw_1d(candle_dict['1D'],master_tradeAPI,conn,marketDataAPI,last_prices_df)



conn.close()

