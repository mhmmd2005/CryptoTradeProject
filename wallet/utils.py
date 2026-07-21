import requests

wallet_address = "TUXsHCMzMF3aAMmSgJMYoRoPd4aYv1N8Tn"
url = f"https://apilist.tronscan.org/api/account/transaction?sort=-timestamp&count=20&address={wallet_address}"

res = requests.get(url).json()
for tx in res['data']:
    print(tx['hash'], tx['contractType'], tx.get('amount', 0))
