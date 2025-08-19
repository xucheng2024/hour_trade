import time
import logging



import logging
from logging.handlers import RotatingFileHandler

def attempt_with_retries(func, attempts=3, delay=1, *args, **kwargs):
    for attempt in range(attempts):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logging.error("transfer:Error on attempt %d: %s", attempt + 1, e)
            time.sleep(delay)
    return None

def transfer_sub(from_acc,to_acc,subAccountAPI):

    attempts =3 
    for attempt in range(attempts):
        try:
            balance_details = subAccountAPI.get_account_balance(subAcct=from_acc)['data'][0]['details']
            break
        except Exception as e:
            logging.error(e)
            time.sleep(1)
    
    balance  = 0
    for each in balance_details:
        ccy = each['ccy']
        if ccy != 'USDT':continue
        balance = int(float(each['eq']))

    if balance < 1:return None

    result = subAccountAPI.subAccount_transfer(
        ccy="USDT",
        amt=balance,
        froms="18",
        to="18",
        fromSubAccount=from_acc,
        toSubAccount=to_acc
    )



def transfer_sub_all(to_acc,sub_AccountAPI):

    acc_lists = attempt_with_retries(sub_AccountAPI.get_subaccount_list, attempts=3, delay=1)
    if not acc_lists:
        logging.error("Failed to retrieve subaccount list after multiple attempts")
        return
    
    acc_data = acc_lists.get('data', [])
    time.sleep(0.2)
        
    for each_acc in acc_data:
        label = each_acc['label']
        if label == to_acc:continue
        
        balance_details = attempt_with_retries(
            sub_AccountAPI.get_account_balance,
            attempts=3,
            delay=1,
            subAcct=label
        )

        if not balance_details:
            logging.error("Failed to retrieve balance for %s", label)
            continue
        
        balance_details = balance_details.get('data', [])[0].get('details', [])
        balance = next((int(float(each['eq'])) for each in balance_details if each['ccy'] == 'USDT'), 0)

        if balance < 1:
            time.sleep(0.5)
            continue
        
        transfer_result = attempt_with_retries(
            sub_AccountAPI.subAccount_transfer,
            attempts=3,
            delay=1,
            ccy="USDT",
            amt=balance,
            froms="18",
            to="18",
            fromSubAccount=label,
            toSubAccount=to_acc
        )

        if not transfer_result:
            logging.error("Failed to transfer %s for %s", balance, label)
        else:
            time.sleep(1)



#main
# sub_apikey = "d7c59f82-447b-4700-a051-8f011750ba75"
# sub_secretkey = "86873D555F0401706057F68AD6FA9951"
# sub_passphrase = 'sunSh1ne!'
# flag = "0"

# sub_accountAPI = SubAccount.SubAccountAPI(sub_apikey, sub_secretkey, sub_passphrase, False, flag)

# transfer_sub_all('dailytrader',sub_accountAPI)


















