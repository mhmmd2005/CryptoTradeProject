from django.contrib import admin
from dashboard.models import UserProfile,ProfileApprovalStatus
# Register your models here.

admin.site.register(UserProfile)
admin.site.register(ProfileApprovalStatus)