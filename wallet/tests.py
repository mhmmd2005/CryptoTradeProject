

# from cryptography.fernet import Fernet
# key = Fernet.generate_key()
# print(key.decode())
# from django.core.management.utils import get_random_secret_key
#
# print(get_random_secret_key())
#

# from tronpy import Tron
# from tronpy.providers import HTTPProvider
#
# # اتصال به Nile Testnet
# client = Tron(provider=HTTPProvider(endpoint_uri="https://nile.trongrid.io"))
#
# wallet_address = "TUXsHCMzMF3aAMmSgJMYoRoPd4aYv1N8Tn"  # جایگزین با آدرس واقعی
#
# try:
#     balance = client.get_account_balance(wallet_address)
#     print(f"Balance of {wallet_address}: {balance} TRX")
# except Exception as e:
#     print(f"Account not found or error: {e}")
# from utils.transaction import print_wallet_transactions
#
# wallet_address = "TUXsHCMzMF3aAMmSgJMYoRoPd4aYv1N8Tn"
# print_wallet_transactions(wallet_address)

# from binance.client import Client
#
# client = Client()
#
# price = client.get_symbol_ticker(symbol="BTCUSDT")
# print(price)
