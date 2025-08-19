import sqlite3
import pandas as pd


conn = sqlite3.connect('/Users/mac/Downloads/stocks/ex_okx/okx.db')

cur = conn.cursor()


# stmt = '''UPDATE orders
# SET state = 'sold out'
# WHERE instId == 'SHIB-USDT';'''
# cur.execute(stmt)

# conn.commit()
# cur.close()
# conn.close()

cur.execute('''DROP TABLE IF EXISTS orders''')

cur.execute('''CREATE TABLE IF NOT EXISTS orders
               (instId TEXT,
                flag TEXT,
                ordId TEXT,
                create_time REAL,
                orderType TEXT,
                state TEXT,
                price TEXT,
                size TEXT,
                sell_time REAL,
                side TEXT)''')



cur.execute('''DROP TABLE IF EXISTS candle_1D''')
# cur.execute('''CREATE TABLE IF NOT EXISTS candle_1D (
#                 instId TEXT,
#                 ts INTEGER,
#                 o REAL,
#                 h REAL,
#                 l REAL,
#                 c REAL,
#                 vol REAL,
#                 volCcy REAL,
#                 volCcyQuote REAL,
#                 confirm INTEGER)''')

cur.execute('''DROP TABLE IF EXISTS candle_1H''')
# cur.execute('''CREATE TABLE IF NOT EXISTS candle_1H (
#                 instId TEXT,
#                 ts INTEGER,
#                 o REAL,
#                 h REAL,
#                 l REAL,
#                 c REAL,
#                 vol REAL,
#                 volCcy REAL,
#                 volCcyQuote REAL,
#                 confirm INTEGER)''')


cur.execute('''DROP TABLE IF EXISTS candle_15m''')
# cur.execute('''CREATE TABLE IF NOT EXISTS candle_15m (
#                 instId TEXT,
#                 ts INTEGER,
#                 o REAL,
#                 h REAL,
#                 l REAL,
#                 c REAL,
#                 vol REAL,
#                 volCcy REAL,
#                 volCcyQuote REAL,
#                 confirm INTEGER)''')


conn.commit()
cur.close()
conn.close()


# conn = sqlite3.connect('example.db')

# cur = conn.cursor()

# cur.execute('SELECT * FROM orders')
# rows = cur.fetchall()

# conn.close()

# df = pd.DataFrame(rows, columns=['insId', 'flag', 'ordId', 'create_time', 'orderType', 'state', 'price', 'size', 'sell_time'])

# TRUNCATE TABLE your_table_name;
# df.to_sql('candle_data', conn, if_exists='append', index=False)
# conn.close()

