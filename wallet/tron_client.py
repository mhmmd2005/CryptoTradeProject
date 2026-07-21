# wallet/tron_client.py
import os

from tronpy import Tron
from tronpy.providers import HTTPProvider


def get_tron_client():
    api_key = os.getenv("TRONGRID_API_KEY")
    if not api_key:
        raise ValueError("TRONGRID_API_KEY not found in environment variables")

    # اتصال به شبکه Shasta (شبکه تستی اما واقعی)
    provider = HTTPProvider(endpoint_uri="https://api.shasta.trongrid.io")
    client = Tron(provider)
    client._default_headers = {"TRON-PRO-API-KEY": api_key}
    return client


# اتصال آماده برای import مستقیم
client = get_tron_client()


