from django.contrib import admin
from .models import UserTicket, FAQCategory,FAQ
# Register your models here.

admin.site.register(UserTicket)
admin.site.register(FAQCategory)
admin.site.register(FAQ)
