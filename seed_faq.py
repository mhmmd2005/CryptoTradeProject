import os

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'CryptoTradeProject__.settings')
django.setup()

from UserPanel.models import FAQCategory, FAQ


def seed_data():
    data = {
        "Getting Started": [
            ("How do I get started?",
             "Log in to your dashboard. First, your identity verification (KYC) must be approved. Once approved, you can access all platform features. For step‑by‑step guidance, please see other questions in this section."),
            ("How can I customize my dashboard?",
             "Click the gear icon at the bottom right of the page to adjust widgets, color schemes, and the layout of elements according to your preference."),
            ("Can I change the theme (dark/light)?",
             "Yes, click the moon/sun icon in the top bar to switch between light and dark mode."),
        ],
        "Trading & Bets": [
            ("Can I trade without making an initial deposit?",
             "No, you need a positive wallet balance to place any trade. The minimum bet amount is displayed for each round."),
            ("What is the minimum and maximum bet amount?",
             "The bet amount range depends on the round and is shown in the 'Position Center' section when you select a currency and timeframe."),
            ("How is profit calculated?",
             "When you win, your original stake plus 95% profit is returned. From that profit, a fee between 1% and 5% (depending on the round) is deducted. The exact amount can be seen in the 'History & Logs' section after settlement."),
            ("Can I place multiple bets on the same symbol at the same time?",
             "No, only one bet per card is allowed per cycle. After the previous bet is settled, you can place a new one."),
            ("What determines whether I win or lose?",
             "Only the price change at the end of each cycle decides the outcome. If the final price is higher than the entry price (for an 'up' bet) or lower (for a 'down' bet), you win. If prices are equal, your entire stake is refunded.")
        ],
        "Notifications": [
            ("Why are some notifications archived?",
             "To keep your notifications page clean and organized, notifications you have read can be archived."),
            ("Can I receive notifications via email?",
             "Yes, you can enable this option in the Notifications settings page."),
        ],
        "Account & Profile": [
            ("How do I change my password?",
             "Go to 'Security Settings', select 'Change Password', and enter your new password."),
            ("What are the steps for identity verification (KYC)?",
             "To use platform features, you must upload your information and documents in the 'Verification' section. Document review usually takes up to 24 hours."),
        ],
        "Support & FAQ": [
            ("How can I contact support?",
             "You can submit your issue through the ticket system (Support tickets > submit New Ticket)."),
            ("What is the response time for tickets?",
             "Regular tickets are answered within 24 hours on business days. Urgent tickets are prioritized and handled as quickly as possible."),
        ],
        "Wallet & Transactions": [
            ("How do I top up my wallet?",
             "Go to the 'Wallet' section, click 'Deposit', and enter the desired amount."),
            ("What is the minimum withdrawal amount?",
             "Withdrawals start from as little as $1. You can request any amount up to your current balance, and it will be processed immediately after approval."),
            ("How long do withdrawal transactions take?",
             "Withdrawal time depends on the amount and whether 2FA is active (full details are available in the withdrawal section of the Wallet page)."),
            ("Is identity verification required for withdrawals?",
             "Yes, all withdrawals require completed identity verification (KYC).")
        ]
    }

    print("در حال همگام‌سازی FAQ با دیتابیس...")

    # 1. حذف دسته‌بندی‌هایی که در دیکشنری جدید نیستند
    existing_cats = set(FAQCategory.objects.values_list('title', flat=True))
    new_cats = set(data.keys())
    for cat in existing_cats - new_cats:
        FAQCategory.objects.filter(title=cat).delete()
        print(f"🗑 دسته‌بندی حذف شد: {cat}")

    # 2. به‌روزرسانی یا ایجاد دسته‌بندی‌ها و سوالات
    for cat_name, questions in data.items():
        category, _ = FAQCategory.objects.get_or_create(title=cat_name)

        # لیست سوالات جدید برای این دسته
        new_questions = {q for q, _ in questions}
        # حذف سوالاتی که در دیکشنری نیستند
        FAQ.objects.filter(category=category).exclude(question__in=new_questions).delete()

        # ایجاد یا به‌روزرسانی سوالات
        for q, a in questions:
            obj, created = FAQ.objects.update_or_create(
                category=category,
                question=q,
                defaults={'answer': a}
            )
            print(f"  {'➕' if created else '🔄'} {q[:40]}...")

    print("✅ همگام‌سازی کامل شد.")


if __name__ == "__main__":
    seed_data()
