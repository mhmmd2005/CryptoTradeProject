import os

from celery import Celery
from celery.schedules import schedule

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'CryptoTradeProject__.settings')

app = Celery('CryptoTradeProject__')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'check-deposits-every-5-sec': {
        'task': 'wallet.tasks.check_pending_deposits',
        'schedule': schedule(run_every=10),  # 10 ثانیه
    },
}

