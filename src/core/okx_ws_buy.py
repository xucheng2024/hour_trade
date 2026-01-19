import asyncio
import base64
import hmac
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import websocket
import websockets
import threading
from logging.handlers import RotatingFileHandler
from okx.Trade import TradeAPI

# Only use file logging if directory exists (for local development)
# In Railway/Vercel, prefer stdout logging
try:
    log_dir = Path("/Users/mac/Downloads/stocks/ex_okx")
    if log_dir.exists() and log_dir.is_dir():
        log_file = log_dir / "okx_ws_buy.log"
        logging.basicConfig(
            filename=str(log_file),
            format='%(asctime)s - %(levelname)s - %(message)s',
            level=logging.WARNING
        )
        handler = RotatingFileHandler(
            filename=str(log_file),
            maxBytes=100*1024*1024,
            backupCount=3
        )
        logging.getLogger().addHandler(handler)
    else:
        # Fall back to stdout logging
        logging.basicConfig(
            format='%(asctime)s - %(levelname)s - %(message)s',
            level=logging.WARNING
        )
except (OSError, PermissionError):
    # Fall back to stdout logging
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s',
        level=logging.WARNING
    )


def sign(key : str, secret : str, passphrase : str):

    ts = str(int(datetime.now().timestamp()))
    args = dict(apiKey=key, passphrase=passphrase, timestamp=ts)
    sign = ts + 'GET' + '/users/self/verify'
    mac = hmac.new(bytes(secret, encoding='utf8'), bytes(sign, encoding='utf-8'), digestmod='sha256')
    args['sign'] = base64.b64encode(mac.digest()).decode(encoding='utf-8')
    return args

def send(ws, op : str, args : list):

    subs = dict(op=op, args=args)
    ws.send(json.dumps(subs))

def process_data(data):
    
    global buy_low_points

    for each in data:
        instId = each['instId']
        lastPx = float(each['lastPx'])
        # fillPx = float(each['fillPx'])
        state = each['state']
        side = each['side']

        if 'filled' not in state or side != 'buy':exit()

        buy_price = float(buy_low_points['instId'])
        if buy_price > lastPx:
            money = 300
            size = money/buy_price

            attempts = 3
            for attempt in range(attempts):
                try:
                    
                    # result = tradeAPI.place_order(
                    #             instId=instId,
                    #             tdMode="cash",
                    #             side="buy",
                    #             ordType="limit",
                    #             px=buy_price,
                    #             sz=size
                    #         )
                    logging.warning("try to buy %s @ %s",instId,buy_price)
                    break
                except Exception as e:
                    logging.error(e)

        time.sleep(10)
        # get_order_list_attempts = 3
        # for get_order_list_attempt in range(get_order_list_attempts):
        #     try:
        #         limit_result = tradeAPI.get_order_list(
        #             instType="SPOT",
        #             ordType="limit"
        #         )
        #         break
        #     except Exception as e:
        #         logging.error(e)
        #         continue


        # limit_orders = limit_result['data']      

        # for limit_order in limit_orders:
        #     l_instId = limit_order['instId']
        #     l_id = limit_order['ordId']
            
        #     logging.warning('begin cancel limit orders')

        #     cancel_order_attempts = 3
        #     for cancel_order_attempt in range(cancel_order_attempts):

        #         try:
        #             result = tradeAPI.cancel_order(instId=l_instId, ordId=l_id)
        #             break  
        #         except Exception as e:
        #             logging.error(e)

        #     logging.warning('end cancel limit orders')


def connect_websocket():
    global debug

    url = 'wss://ws.okx.com:8443/ws/v5/private'
    if debug:
        url = 'wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999'
   
    while True:
        try:
            # Create WebSocket connection
            ws = websocket.WebSocketApp(url,
                                        on_message=on_message,
                                        on_error=on_error,
                                        on_close=on_close,
                                        on_open=on_open)
            def send_ping():
                while True:
                    time.sleep(20)  # Send ping message every 5 seconds
                    try:
                        ws.send("ping")  # Send empty message, equivalent to sending ping message
                    except websocket.WebSocketConnectionClosedException:
                        break

            # Create and start thread for sending ping messages
            ping_thread = threading.Thread(target=send_ping)
            ping_thread.start()
            # Run WebSocket
            ws.run_forever()
        except Exception as e:
            print("Connection failed:", e)
            print("Retrying in 5 seconds...")
            time.sleep(5)


def on_message(ws, msg_string):

    global buy_low_points
    global updated_flag
    global dir
    global file_name
    global debug

    try:
        m = json.loads(msg_string)
        ev = m.get('event')
        data = m.get('data')

        if ev == 'error':
            logging.error("Error ", msg_string)
        elif ev in ['subscribe', 'unsubscribe']:
            logging.warning("subscribe/unsubscribe ", msg_string)
        elif ev == 'login':
            logging.warning('Ur Logged in')
            msg = {
                "op": "subscribe",
                "args": [{'channel':'orders', 'instType':'SPOT'}]
            }
            ws.send(json.dumps(msg))
        # elif ev == 'channel-conn-cont':
        #     pass
        elif data:

            current_time = datetime.now()
            hourly_time = current_time.replace(minute=0, second=0, microsecond=0).timestamp()
            last_upd_time =os.path.getmtime(file_name)

            if last_upd_time < hourly_time: 
                updated_flag = 0
                logging.error("okx_1H_low_pos.json not ready!")
                return

            if updated_flag == 0:
                try:
                    with open(file_name, 'r') as file:
                        buy_low_points = json.load(file)
                        updated_flag =1
                except Exception as e:
                    logging.error(e)
                    return
            
            if debug:process_data(data)
            else:
                threading.Thread(target=process_data, args=(data,)).start()

    except Exception as e:
        logging.error(e)
        

def on_error(ws, error):
    logging.warning(f"Error: {error}")

def on_close(ws):
    logging.warning("### Closed ###")

def on_open(ws):
    logging.warning("### Opened ###")
    login_args : dict = sign(API_KEY, API_SECRET, API_PASSPHARSE)

    msg = {
      "op": "login",
      "args": [login_args]
    }

    ws.send(json.dumps(msg))

# def azz_ws():
#     global debug

#     url = 'wss://ws.okx.com:8443/ws/v5/private'
#     if debug:
#         url = 'wss://wspap.okx.com:8443/ws/v5/private?brokerId=9999'

#     for ws in websockets.connect(url):
#         print("Connected " + datetime.now().isoformat())
#         try:

#             login_args : dict = sign(API_KEY, API_SECRET, API_PASSPHARSE)
#             send(ws, 'login', [login_args])

#             for msg_string in ws:
#                 try:

#                     m = json.loads(msg_string)
#                     ev = m.get('event')
#                     data = m.get('data')

#                     if ev == 'error':
#                         print("Error ", msg_string)
#                     elif ev in ['subscribe', 'unsubscribe']:
#                         print("subscribe/unsubscribe ", msg_string)
#                     elif ev == 'login':
#                         print('Ur Logged in')
#                         send(ws, 'subscribe', [
#                             dict(channel='orders', instType='SPOT')                        ])
#                     elif data:

#                         global buy_low_points
#                         global updated_flag
#                         global dir
#                         global file_name

#                         current_time = datetime.now()
#                         hourly_time = current_time.replace(minute=0, second=0, microsecond=0).timestamp()
#                         last_upd_time =os.path.getmtime(file_name)

#                         if last_upd_time < hourly_time: 
#                             updated_flag = 0
#                             logging.error("okx_1H_low_pos.json not ready!")
#                             exit()
                            
    
#                         if updated_flag == 0:
#                             try:
#                                 with open(file_name, 'r') as file:
#                                     buy_low_points = json.load(file)
#                                     updated_flag =1
#                             except Exception as e:
#                                 logging.error(e)
#                                 exit()
                        
#                         if debug:process_data(data)
#                         else:
#                             threading.Thread(target=process_data, args=(data,)).start()

#             except Exception as e:
#                 logging.error(e)








debug = False  # Set to True for testnet

# Load API credentials from environment
API_KEY = os.getenv('OKX_API_KEY', '')
API_SECRET = os.getenv('OKX_SECRET', '')
API_PASSPHARSE = os.getenv('OKX_PASSPHRASE', '')
flag = 1 if os.getenv('OKX_TESTNET', 'false').lower() == 'true' else 0

if not all([API_KEY, API_SECRET, API_PASSPHARSE]):
    logging.error("OKX API credentials not found in environment variables")



if __name__ == '__main__':
    # Use relative path from project root, fallback to hardcoded path for local dev
    try:
        base_dir = Path(__file__).parent.parent.parent
        dir = str(base_dir) + '/'
    except Exception:
        # Fallback for local development
        dir = '/Users/mac/Downloads/stocks/ex_okx/'
    file_name = dir +'okx_1H_low_pos.json'
    with open(file_name, 'r') as file:
        buy_low_points = json.load(file)
    
    initial_attempts =3
    for initial_attempt in range(initial_attempts):
        try:
            tradeAPI = TradeAPI(API_KEY, API_SECRET, API_PASSPHARSE, False, flag)
            break
        except Exception as e:
            logging.error(e)
            time.sleep(1)

    updated_flag = 0
    
    # azz_ws()
    connect_websocket()
