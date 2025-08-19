import requests
import json
import hmac
import hashlib
import base64
import os
import math
import time
from datetime import datetime, timedelta

import sqlite3

import pandas as pd
import numpy as np

from okx.Trade import TradeAPI
from okx.MarketData import MarketAPI
from okx.Account import AccountAPI

import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)
import logging


# def pre_buy(instId,marketDataAPI):
#     count = 0

#     while True:
#         try:

#             result = marketDataAPI.get_ticker(
#                 instId=instId
#             )

#             last = float(result['data'][0]['last'])
#             bidPx = float(result['data'][0]['bidPx'])
#             logging.warning("prebuy:%s,%s,%s",instId,last,bidPx)
#         except Exception as e:
#             logging.error("rkt pre_buy:%s,%s",instId,e)
#             count = count + 1
       
#         if count>3 or last <= bidPx:
#             return bidPx

#         time.sleep(0.2)

# def pre_sell(instId,marketDataAPI):

#     candle_attempts = 3
#     for candle_attempt in range(candle_attempts):
#         try:
#             result = marketDataAPI.get_candlesticks(
#                 instId=instId,
#                 bar = '15m'
#             )
#             break
#         except Exception as e:
#             logging.error("sp sell candle:%s",e)
#             time.sleep(1)

#     cur_candle = result['data'][0]
#     cur_open = float(cur_candle[1])
#     cur_high = float(cur_candle[2])
#     cur_low = float(cur_candle[3])
#     cur_close = float(cur_candle[4])
#     last_candle = result['data'][1]
#     last_open = float(last_candle[1])
#     last_high = float(last_candle[2])
#     last_low = float(last_candle[3])
#     last_close = float(last_candle[4])

#     if cur_low < last_low: return -1
#     else:
#         return 1


def format_number(number):
    number = float(number)
    if number>100:number = int(number)
    elif number > 1:number = int(number *100)/100
    else:
        digit = int(-math.log(number,10)+1)
        scale_factor = (10**digit) * 100
        number = int(number * scale_factor) / scale_factor
        decimal_places = digit+2
        formatted_number = f"{number:.{decimal_places}f}"
        return formatted_number
    
    return f"{number}"



def buy_market(instId,size,tradeAPI,strategy,conn,minutes):
    
    size = format_number(size)
    max_attempts = 3

    failed_flag = 0

    for attempt in range(max_attempts):
        try:
            result = tradeAPI.place_order(
                    instId=instId,
                    tdMode="cash",
                    side="buy",
                    ordType="market",
                    sz=size,
                    tgtCcy='base_ccy'
                )
            
            result_msg = result['data'][0]['sMsg']
            logging.warning("%s buy mrk:%s,%s,%s",strategy,instId,size,result_msg)
            if "failed" in result_msg:
                time.sleep(1)
                failed_flag = 1
                continue
            failed_flag = 0
            break          
        except Exception as e:
            logging.error("%s buy mrk:%s,%s,%s",strategy,instId,size,e)
            failed_flag =1
    
    if failed_flag>0:return
    cur = conn.cursor()
    for attempt in range(max_attempts):
        try:
            now = datetime.now()
            ordId = result['data'][0]['ordId']
            flag = strategy
            create_time = int(now.timestamp()*1000)
            orderType = 'mrk'
            state = ''
            price = ''
            size = ''
            
            sell_time = int((now+timedelta(minutes=minutes)).timestamp()*1000)
            side = 'buy'

            if ordId is None: return
            cur.execute('''INSERT INTO orders (instId, flag, ordId, create_time, orderType, state, price, size, sell_time,side)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,?)''', (instId, flag, ordId, create_time, orderType, state, price, size, sell_time,side))
            conn.commit()

            logging.warning("%s buy mrk:db:%s,%s,%s",strategy,instId,ordId)

            break
        except Exception as e:
            logging.error("%s buy mrk:db:%s,%s,%s",strategy,instId,ordId,e)

    cur.close()
    return instId,ordId



def buy_limit(instId,buy_price,size,tradeAPI,strategy,conn,minutes):
    
    buy_price = format_number(buy_price)
    size = format_number(size)
    max_attempts = 3
    failed_flag = 0

    for attempt in range(max_attempts):
        try:
            result =tradeAPI.place_order(
                    instId=instId,
                    tdMode="cash",
                    side="buy",
                    ordType="limit",
                    px=buy_price,
                    sz=size
                )
            result_msg = result['data'][0]['sMsg']
            main_msg = result['msg']

            logging.warning("%s buy limit:%s,%s,%s,%s,%s",strategy,instId,buy_price,size,result_msg,main_msg)
            

            if "failed" in result_msg:
                failed_flag = 1
                continue
            failed_flag = 0
            break          
        except Exception as e:
            logging.warning("%s buy limit:%s,%s,%s,%s",strategy,instId,buy_price,size,e)
            failed_flag = 1
    
    if failed_flag>0:return
    cur = conn.cursor()
    for attempt in range(max_attempts):
        try:
            now = datetime.now()
            ordId = result['data'][0]['ordId']

            if ordId is None: return


            flag = strategy
            create_time = int(now.timestamp()*1000)
            orderType = 'limit'
            state = ''
            price = ''
            size = ''
            sell_time = int((now+timedelta(minutes=minutes)).timestamp()*1000)
            side = 'buy'

            cur.execute('''INSERT INTO orders (instId, flag, ordId, create_time, orderType, state, price, size, sell_time,side)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,?)''', (instId, flag, ordId, create_time, orderType, state, price, size, sell_time,side))
            conn.commit()
            logging.warning("%s buy limit:db:%s,%s,%s",strategy,instId,ordId)

            break
        except Exception as e:
            logging.warning("%s buy limit db:%s,%s,%s",strategy,instId,ordId,e)
    cur.close()
    return instId,ordId



def sell_market(instId,ordId,size,tradeAPI,strategy,conn):
    size = format_number(size)
    max_attempts = 3
    failed_flag = 0

    for attempt in range(max_attempts):
        try:

            result = tradeAPI.place_order(
                instId=instId,
                tdMode="cash",
                side="sell",
                ordType="market",
                sz=size,
                tgtCcy='base_ccy'

            )

            result_msg = result['data'][0]['sMsg']
            logging.warning("%s sell mrk:%s,%s,%s",strategy,instId,size,result_msg)  

            if "failed" in result_msg:
                failed_flag = 1
                continue
            
            failed_flag = 0
            break              
        except Exception as e:
            logging.error("%s sell mrk:%s,%s,%s",strategy,instId,size,e)
            failed_flag = 1

    if failed_flag>0:return
    cur = conn.cursor()
    for attempts in range(max_attempts):
        try:
            new_state = 'sold out'

            sql_statement = """
            UPDATE orders
            SET state = ?
            WHERE instId = ? AND ordId = ?;
            """
            cur.execute(sql_statement, (new_state,instId, ordId))  
            conn.commit() 
            logging.warning("%s sell mrk:db:%s,%s,%s",strategy,instId,ordId)

            break
        except Exception as e:
            logging.error("%s sell mrk db:%s,%s,%s",strategy,instId,ordId,e)
       
    cur.close()
    return instId,ordId


