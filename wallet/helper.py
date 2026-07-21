# from decimal import Decimal
# import requests
#
# # assume `client = Tron()` already exists at module level
#
# USDT_CONTRACT = 'TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj'  # USDT TRC20
# USDT_DECIMALS = Decimal('1e6')  # USDT (TRC20) usually 6 decimals
#
#
# def _verify_usdt_trx_with_tronpy(tx_hash, expected_to_address, expected_amount):
#     """
#     تلاش برای گرفتن اطلاعات تراکنش با tronpy و اعتبارسنجی اینکه
#     - توکن USDT بوده
#     - گیرنده expected_to_address باشد
#     - مقدار on-chain برابر expected_amount (با دقت USDT_DECIMALS) باشد
#     در صورت موفقیت -> return (True, actual_amount_decimal)
#     در صورت خطا -> return (False, "error message")
#     """
#     try:
#         tx = client.get_transaction(tx_hash)  # ممکنه None باشد یا Exception
#     except Exception as e:
#         return False, f"خطا در تماس با گره Tron (tronpy): {e}"
#
#     if not tx:
#         return False, "تراکنش پیدا نشد."
#
#     # اطلاعات کامل‌تر (receipt/logs) از transaction info بگیریم
#     try:
#         tx_info = client.get_transaction_info(tx_hash)
#     except Exception:
#         tx_info = None
#
#     # روش‌های مختلف: اگر تراکنش trigger smart contract باشه، raw_data.contract[0] وجود داره
#     try:
#         raw = tx.get('raw_data', {}) if isinstance(tx, dict) else {}
#         contracts = raw.get('contract', []) if raw else []
#     except Exception:
#         contracts = []
#
#     # بررسی ساده: اگر قرارداد اجرا شده و آدرس قرارداد USDT باشه،
#     # سپس مقدار ورودی (data) را decode کنیم (transfer(address,uint256)).
#     # اما چون decode ممکنه پیچیده باشه، یک روش عملی‌تر: بررسی logs/contractResult/decodedEvents در tx_info
#     # بسیاری از نودها/TronGrid برگشتی شامل "log" یا "contractResult" هستند.
#     # تلاش برای استخراج مقدار از tx_info:
#     if tx_info:
#         # بررسی لاگ‌ها برای event transfer (topic مربوط به ERC20-like)
#         logs = tx_info.get('log', [])
#         # trc20 transfer ممکنه در log با مقادیر hex بیاد؛ تلاش ساده:
#         for lg in logs:
#             try:
#                 # lg ممکنه ساختار متفاوتی داشته باشه؛ بعضی‌ها فیلدهای 'address','topics','data' دارن
#                 addr = lg.get('address') or lg.get('contractAddress') or lg.get('contract')
#                 if addr and addr.lower() == USDT_CONTRACT.lower():
#                     # data ممکنه مقدار را برگرداند (hex)
#                     data = lg.get('data') or lg.get('decoded') or None
#                     # برخی API ها داده‌های decode شده در 'decoded' یا topics قرار می‌دهند.
#                     # اگر 'decoded' باشه و پارامترها قابل خواندن باشند:
#                     if isinstance(data, dict):
#                         # انتظار: {'to': 'T...', 'value': <int>}
#                         to = data.get('to') or data.get('recipient')
#                         value = data.get('value')
#                         if to and value:
#                             actual_amount = Decimal(value) / USDT_DECIMALS
#                             # مقایسه با expected_amount (Decimal)
#                             return True, actual_amount
#                     # اگر data رشته hex باشه، نمی‌کونیم آن را decode کنیم اینجا؛ ادامه به fallback
#             except Exception:
#                 continue
#
#     # fallback: بررسی contractResult یا contracts list
#     try:
#         # اگر در raw_data.contract وجود داشته باشه و نوع triggerSmartContract باشه:
#         if contracts:
#             for c in contracts:
#                 ctype = c.get('type')
#                 parameter = c.get('parameter', {})
#                 value = parameter.get('value', {})
#                 # contract_address ممکنه در اینجا باشد (hex)
#                 contract_address = value.get('contract_address') or value.get('contract')
#                 # آدرس قرارداد به فرمت base58 ممکنه نباشد؛ تبدیل نیاز باشه.
#                 # اگر contract_address equals USDT_CONTRACT (در برخی پاسخ‌ها به شکل base58) -> check
#                 # برای سادگی، اگر contract_address هست و ما فرض کنیم قرارداد USDT است، می‌پذیریم که transfer هست.
#                 # اما مقدار actual value را نمی‌توان همیشه از این بخش بیرون کشید؛ بنابراین fallback بعدی را امتحان می‌کنیم.
#             # اگر نیافتیم، به دنبال event های دیگر برویم
#     except Exception:
#         pass
#
#     # آخرین fallback: استفاده از Tronscan API (HTTP) برای دریافت info خوانا
#     try:
#         # استفاده از apilist.tronscan.org که پاسخ JSON خوانا میدهد
#         url = f"https://apilist.tronscan.org/api/transaction-info?hash={tx_hash}"
#         r = requests.get(url, timeout=10)
#         if r.status_code == 200:
#             info = r.json()
#             # برخی کلیدها: 'contractType', 'tokenTransferInfo' یا 'internalTransactions' یا 'tokenInfoList'
#             # بررسی token transfers
#             token_transer_list = info.get('tokenTransferInfo') or info.get('tokenInfoList') or info.get(
#                 'tokenTransfers') or []
#             for t in token_transer_list:
#                 # ساختار ممکن: {'tokenName':'Tether USD', 'tokenId':..., 'amount':..., 'toAddress':..., 'contractAddress':...}
#                 contract = t.get('tokenId') or t.get('contractAddress') or t.get('tokenAddress') or t.get('contract')
#                 to_addr = t.get('toAddress') or t.get('to') or t.get('to_address')
#                 amt = t.get('amount') or t.get('value') or t.get('quant') or None
#                 if not contract:
#                     # بعضی ساختارها contract in t['tokenInfo']['contractAddress']
#                     token_info = t.get('tokenInfo') or {}
#                     contract = token_info.get('contractAddress') or token_info.get('address')
#                 if contract and contract.lower() == USDT_CONTRACT.lower():
#                     # amount ممکنه به صورت integer (مثلاً 1000000 برای 1 USDT)
#                     if amt is None:
#                         continue
#                     try:
#                         actual_amount = Decimal(str(int(amt))) / USDT_DECIMALS
#                     except Exception:
#                         # گاهی amount به صورت استرینگ اعشار است
#                         try:
#                             actual_amount = Decimal(str(amt))
#                         except Exception:
#                             continue
#                     # مقایسه آدرس‌ها (to)
#                     if to_addr and (to_addr == expected_to_address or to_addr.endswith(expected_to_address)):
#                         return True, actual_amount
#             # اگر نیافتیم، خطا بده
#             return False, "تراکنش USDT معتبر یا متعلق به آدرس شما یافت نشد."
#         else:
#             return False, f"خطا در تماس با Tronscan API: وضعیت {r.status_code}"
#     except Exception as e:
#         return False, f"خطا در تماس HTTP با Tronscan/TronGrid: {e}"
