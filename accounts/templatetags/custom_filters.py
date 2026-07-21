import re

from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def mask_email_custom(email):
    """
    ۴ کاراکتر اول و آخر بخش قبل از @ را نشان می‌دهد، بقیه مخفی شود.
    """
    if not email or "@" not in email:
        return email

    local, domain = email.split("@")

    if len(local) <= 5:
        # اگر کمتر از 5 کاراکتر بود، همه نمایش داده شود
        masked_local = local
    else:
        # 4 کاراکتر اول + **** + آخرین کاراکتر
        masked_local = local[:3] + "*" * (len(local) - 5) + local[-1]

    return f"{masked_local}@{domain}"


@register.filter
def format_timeframe(value):
    if value >= 3600:
        hours = value // 3600
        return f"{hours} hours"
    elif value >= 60:
        minutes = value // 60
        return f"{minutes} minutes"
    else:
        return f"{value} seconds"


@register.filter(name='split')
def split(value, key):
    return value.split(key)


@register.filter
def highlight(text, search):
    if not search or not text:
        return text

    # استفاده از یک استایل ملایم‌تر به جای bg-warning
    # مثلا یک پس‌زمینه آبی بسیار روشن با متن تیره
    highlighted_style = 'background-color: rgba(59, 113, 202, 0.2); color: #285192; padding: 0 2px; border-radius: 2px;'

    highlighted = re.sub(
        f'({re.escape(search)})',
        f'<span style="{highlighted_style}">\\1</span>',
        str(text),
        flags=re.IGNORECASE
    )
    return mark_safe(highlighted)
