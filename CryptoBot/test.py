from binance.client import Client

API_KEY = 'fnGInvArAH6MgE018Ewjz6y8uUvlXJ1vNfGrWY4HKZWdx61mfeA7ZpBRu1sdgYRM'
API_SECRET = 'CUNMaiCFv9NKskbiUsiOHZj5BGQoR9bZNLO5mmwjFkwccQoRXsj6o9QZcWa4YnVz'

client = Client(API_KEY, API_SECRET)

try:
    # Fetch account information as a test
    account_info = client.get_account()
    print(account_info)
except Exception as e:
    print(f"Error: {e}")