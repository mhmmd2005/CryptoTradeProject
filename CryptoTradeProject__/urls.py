"""
URL configuration for CryptoTradeProject__ project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

# ایمپورت کردن handler برای مدیریت خطا
from django.conf.urls import handler403

urlpatterns = [
    path('core-admin-system', admin.site.urls), # جنگو ادمین اصلی
    path('', include('accounts.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('', include('wallet.urls')),
    path('adminPanel/', include('adminPanel.urls')),
    path('', include('UserPanel.urls')),
    path('', include('Prediction.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # تغییر این خط: به جای STATIC_ROOT از پوشه اصلی استاتیک استفاده کن
    urlpatterns += static(settings.STATIC_URL, document_root=settings.BASE_DIR / 'static')

# این خط باید به فایلی اشاره کند که تابع error_403_view در آن تعریف شده
# اگر تابع را در adminPanel/views.py نوشتی، آدرس زیر درست است:
handler403 = 'adminPanel.views.error_403_view'