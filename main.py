import logging
import sqlite3
import asyncio
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes

# 🔐 توكن البوت ومعرف المدير
TOKEN = "7427215837:AAFWgPPm1_pF9fEjUI87nwlVJA-So41FvyQ"
ADMIN_ID = 5843673266  # معرف المدير

# 🛠️ إعدادات السجل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 📦 إعداد قاعدة البيانات
def init_db():
    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()

        # جدول المستخدمين مع جميع الأعمدة المطلوبة
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            referrer INTEGER,
            investment INTEGER DEFAULT 0,
            balance INTEGER DEFAULT 0,
            last_profit_date DATE,
            investment_start_date DATE,
            investment_days INTEGER DEFAULT 0,
            total_referrals INTEGER DEFAULT 0,
            referral_bonus INTEGER DEFAULT 0,
            referral_link TEXT,
            total_earned INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # جدول المدفوعات
        c.execute('''CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            method TEXT,
            proof BLOB,
            status TEXT DEFAULT 'pending',
            admin_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP
        )''')

        # جدول الأرباح اليومية
        c.execute('''CREATE TABLE IF NOT EXISTS daily_profits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            profit_amount INTEGER,
            investment_amount INTEGER,
            package_type TEXT,
            profit_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # جدول الإشعارات
        c.execute('''CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message TEXT,
            notification_type TEXT DEFAULT 'general',
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # جدول السحوبات
        c.execute('''CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            method TEXT,
            account_info TEXT,
            status TEXT DEFAULT 'pending',
            admin_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP
        )''')

        # جدول الإحالات
        c.execute('''CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referred_id INTEGER,
            referral_bonus INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # جدول إعدادات النظام
        c.execute('''CREATE TABLE IF NOT EXISTS system_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setting_name TEXT UNIQUE,
            setting_value TEXT,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # جدول السجلات
        c.execute('''CREATE TABLE IF NOT EXISTS system_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            details TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # إضافة الأعمدة المفقودة للجداول الموجودة
        try:
            # إضافة الأعمدة المفقودة في جدول users
            c.execute('ALTER TABLE users ADD COLUMN first_name TEXT')
        except sqlite3.OperationalError:
            pass

        try:
            c.execute('ALTER TABLE users ADD COLUMN referral_link TEXT')
        except sqlite3.OperationalError:
            pass

        try:
            c.execute('ALTER TABLE users ADD COLUMN total_earned INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass

        try:
            c.execute('ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1')
        except sqlite3.OperationalError:
            pass

        try:
            c.execute('ALTER TABLE users ADD COLUMN join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP')
        except sqlite3.OperationalError:
            pass

        try:
            # إضافة الأعمدة المفقودة في جدول payments
            c.execute('ALTER TABLE payments ADD COLUMN amount INTEGER')
        except sqlite3.OperationalError:
            pass

        try:
            c.execute('ALTER TABLE payments ADD COLUMN admin_notes TEXT')
        except sqlite3.OperationalError:
            pass

        try:
            c.execute('ALTER TABLE payments ADD COLUMN processed_at TIMESTAMP')
        except sqlite3.OperationalError:
            pass

        # إدراج إعدادات النظام الافتراضية
        default_settings = [
            ('referral_bonus_percentage', '10', 'نسبة مكافأة الإحالة بالمئة'),
            ('min_withdrawal_amount', '1000', 'الحد الأدنى للسحب بالدينار'),
            ('withdrawal_fee_percentage', '2', 'رسوم السحب بالمئة'),
            ('daily_profit_time', '12:00', 'وقت توزيع الأرباح اليومية'),
            ('support_username', 'ribeh_support', 'معرف الدعم الفني'),
            ('bot_status', 'active', 'حالة البوت')
        ]

        for setting_name, setting_value, description in default_settings:
            c.execute('''INSERT OR IGNORE INTO system_settings (setting_name, setting_value, description) 
                        VALUES (?, ?, ?)''', (setting_name, setting_value, description))

        conn.commit()

# 🔘 القائمة الرئيسية المحسنة
main_menu = [
    ["📦 الباقات", "💼 ملفي الشخصي"],
    ["💳 إيداع", "💸 سحب الأموال"],
    ["🧾 إثبات الدفع", "📋 مدفوعاتي"],
    ["🔗 رابط الإحالة", "👥 إحالاتي"],
    ["📊 إحصائيات الأرباح", "🔔 الإشعارات"],
    ["💬 الدعم الفني", "🏠 الصفحة الرئيسية"]
]

# 🚀 بدء البوت مع معالجة الإحالات
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    reply_markup = ReplyKeyboardMarkup(main_menu, resize_keyboard=True)

    # معالجة الإحالة إذا وجدت
    referral_processed = False
    if context.args and context.args[0].startswith('ref_'):
        referral_code = context.args[0].replace('ref_', '')
        referral_processed = process_referral(referral_code, user.id)

    # رسالة الترحيب
    welcome_message = f"""🎉 مرحبًا بك {user.first_name} في بوت Ribeh الاستثماري!

💼 **نظام استثماري موثوق وآمن**
📈 **أرباح يومية مضمونة**
🔗 **نظام إحالة متطور**
💰 **سحب فوري للأرباح**

اختر من القائمة أدناه للبدء:"""

    if referral_processed:
        welcome_message += "\n\n🎁 تم تسجيلك عبر رابط إحالة! ستحصل على مكافآت إضافية عند الاستثمار."

    await update.message.reply_text(welcome_message, reply_markup=reply_markup)

    # حفظ المستخدم مع معلومات إضافية
    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()
        c.execute('''INSERT OR IGNORE INTO users (user_id, username, first_name) 
                    VALUES (?, ?, ?)''', (user.id, user.username, user.first_name))

        # إنشاء رابط إحالة إذا لم يكن موجوداً
        c.execute("SELECT referral_link FROM users WHERE user_id = ?", (user.id,))
        if not c.fetchone()[0]:
            generate_referral_link(user.id)

        conn.commit()

    # تسجيل العملية
    log_user_action(user.id, 'start_bot', f'بدء استخدام البوت - الإحالة: {referral_processed}')

# 📦 الباقات
async def show_packages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # قائمة الباقات مع الأزرار
    packages_menu = [
        ["💰 2000 دج", "💰 6000 دج", "💰 10000 دج"],
        ["💰 15000 دج", "💰 20000 دج", "💰 25000 دج"],
        ["💰 30000 دج", "💰 40000 دج", "💰 60000 دج"],
        ["🔙 العودة للقائمة الرئيسية"]
    ]

    reply_markup = ReplyKeyboardMarkup(packages_menu, resize_keyboard=True)

    packages_text = """
💼 الباقات الاستثمارية المتاحة:

اختر الباقة المناسبة لك:

💰 2000 دج - عائد يومي: 50 دج
💰 6000 دج - عائد يومي: 150 دج  
💰 10000 دج - عائد يومي: 250 دج
💰 15000 دج - عائد يومي: 400 دج
💰 20000 دج - عائد يومي: 550 دج
💰 25000 دج - عائد يومي: 700 دج
💰 30000 دج - عائد يومي: 850 دج
💰 40000 دج - عائد يومي: 1200 دج
💰 60000 دج - عائد يومي: 1800 دج

⏰ مدة جميع الاستثمارات: 40 يوم
📈 عائد إضافي بنسبة 25% من رأس المال

اضغط على الباقة التي تريدها:
"""
    await update.message.reply_text(packages_text, reply_markup=reply_markup)

# 👤 الملف الشخصي
async def show_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = update.effective_user
    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()
        c.execute("""
            SELECT investment, balance, investment_start_date, investment_days 
            FROM users WHERE user_id = ?
        """, (user_id,))
        result = c.fetchone()

        if result:
            invested, balance, start_date, days = result
        else:
            invested = balance = days = 0
            start_date = None

        # إجمالي الأرباح ومكافآت الإحالة
        c.execute("""
            SELECT SUM(profit_amount) FROM daily_profits WHERE user_id = ?
        """, (user_id,))
        total_profits = c.fetchone()[0] or 0

        # معلومات الإحالة
        c.execute("""
            SELECT total_referrals, referral_bonus 
            FROM users WHERE user_id = ?
        """, (user_id,))
        referral_info = c.fetchone()
        total_referrals = referral_info[0] if referral_info else 0
        referral_bonus = referral_info[1] if referral_info else 0

        # تحديد نوع الباقة
        package_type = "لا يوجد"
        daily_profit = 0
        remaining_days = 0

        if invested == 2000:
            package_type = "🥉 المبتدئين"
            daily_profit = 50
            remaining_days = max(0, 45 - days)
        elif invested == 10000:
            package_type = "🥈 المتقدمين"
            daily_profit = 250
            remaining_days = max(0, 40 - days)
        elif invested == 15000:
            package_type = "المتقدم +"
            daily_profit = 400
            remaining_days = max(0, 40 - days)
        elif invested == 20000:
            package_type = "المحترف"
            daily_profit = 550
            remaining_days = max(0, 40 - days)
        elif invested == 25000:
            package_type = "المحترف +"
            daily_profit = 700
            remaining_days = max(0, 40 - days)
        elif invested == 30000:
            package_type = "الخبير"
            daily_profit = 850
            remaining_days = max(0, 40 - days)
        elif invested == 40000:
            package_type = "الخبير +"
            daily_profit = 1200
            remaining_days = max(0, 40 - days)
        elif invested == 60000:
            package_type = "🥇 المحترفين"
            daily_profit = 1800
            remaining_days = max(0, 40 - days)

    profile_text = f"""
👤 الملف الشخصي:

🆔 معرف المستخدم: {user_id}
📱 اسم المستخدم: @{user.username or 'غير متوفر'}
👋 الاسم: {user.first_name}

💼 معلومات الاستثمار:
💰 إجمالي الاستثمار: {invested:,} دج
💳 الرصيد الحالي: {balance:,} دج
📈 إجمالي الأرباح: {total_profits:,} دج

📦 الباقة الحالية: {package_type}
💵 الربح اليومي: {daily_profit:,} دج
📅 الأيام المتبقية: {remaining_days} يوم
📊 أيام الاستثمار: {days} يوم

📅 تاريخ بدء الاستثمار: {start_date or 'لم يبدأ بعد'}
"""
    await update.message.reply_text(profile_text)

# 🔗 رابط الإحالة
async def show_referral_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = update.effective_user

    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()
        c.execute('''SELECT referral_link, total_referrals, referral_bonus 
                    FROM users WHERE user_id = ?''', (user_id,))
        result = c.fetchone()

        if result:
            referral_code, total_referrals, referral_bonus = result
        else:
            referral_code = generate_referral_link(user_id)
            total_referrals = referral_bonus = 0

    referral_link = f"https://t.me/ribeh_investment_bot?start=ref_{referral_code}"

    referral_text = f"""
🔗 **رابط الإحالة الخاص بك:**

`{referral_link}`

📊 **إحصائيات الإحالة:**
👥 عدد الإحالات: {total_referrals}
💰 مكافآت الإحالة: {referral_bonus:,} دج

🎁 **كيف تعمل الإحالة؟**
• احصل على 10% من كل استثمار لمن يسجل برابطك
• المكافأة تُضاف لرصيدك فوراً عند استثمار المُحال
• لا حد أقصى للإحالات أو المكافآت

📱 **شارك الرابط مع:**
• الأصدقاء والعائلة
• مجموعات التليجرام
• وسائل التواصل الاجتماعي

💡 **نصائح للنجاح:**
• اشرح فوائد الاستثمار
• شارك تجربتك الشخصية
• كن صادقاً وشفافاً

🚀 ابدأ بالمشاركة واربح أموال إضافية!
"""

    await update.message.reply_text(referral_text, parse_mode='Markdown')
    log_user_action(user_id, 'view_referral_link')

# 👥 إحالاتي
async def show_my_referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()

        # الإحالات النشطة
        c.execute('''SELECT r.referred_id, u.username, u.first_name, u.investment, 
                           r.referral_bonus, r.created_at
                    FROM referrals r
                    JOIN users u ON r.referred_id = u.user_id
                    WHERE r.referrer_id = ?
                    ORDER BY r.created_at DESC
                    LIMIT 10''', (user_id,))

        referrals = c.fetchall()

        # إجمالي الإحصائيات
        c.execute('''SELECT COUNT(*), SUM(referral_bonus), SUM(u.investment)
                    FROM referrals r
                    JOIN users u ON r.referred_id = u.user_id
                    WHERE r.referrer_id = ?''', (user_id,))

        total_count, total_bonus, total_investments = c.fetchone()
        total_bonus = total_bonus or 0
        total_investments = total_investments or 0

    if not referrals:
        referrals_text = """
👥 **إحالاتي:**

❌ لا توجد إحالات حتى الآن

🚀 **كيفية الحصول على إحالات:**
1. اضغط على 🔗 رابط الإحالة
2. انسخ الرابط وشاركه
3. عندما يسجل شخص برابطك ويستثمر، تحصل على مكافأة!

💰 مكافأة الإحالة: 10% من كل استثمار
"""
    else:
        referrals_text = f"""
👥 **إحالاتي:**

📊 **الإحصائيات العامة:**
• إجمالي الإحالات: {total_count}
• إجمالي المكافآت: {total_bonus:,} دج
• إجمالي استثمارات المُحالين: {total_investments:,} دج

📋 **آخر 10 إحالات:**
"""

        for i, referral in enumerate(referrals, 1):
            referred_id, username, first_name, investment, bonus, created_at = referral
            date_str = created_at.split()[0] if created_at else 'غير محدد'

            referrals_text += f"""
{i}. 👤 {first_name} (@{username or 'لا يوجد'})
   💰 الاستثمار: {investment:,} دج
   🎁 مكافأتك: {bonus:,} دج
   📅 التاريخ: {date_str}
"""

    referrals_text += """

🔗 لمشاركة رابط الإحالة، اضغط على "🔗 رابط الإحالة"
"""

    await update.message.reply_text(referrals_text, parse_mode='Markdown')
    log_user_action(user_id, 'view_referrals')

# 🔔 الإشعارات
async def show_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()

        # الإشعارات غير المقروءة
        c.execute('''SELECT id, message, notification_type, created_at
                    FROM notifications 
                    WHERE user_id = ? AND is_read = 0
                    ORDER BY created_at DESC
                    LIMIT 20''', (user_id,))

        unread_notifications = c.fetchall()

        # تحديد الإشعارات كمقروءة
        c.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0", (user_id,))
        conn.commit()

    if not unread_notifications:
        notifications_text = """
🔔 **الإشعارات:**

✅ لا توجد إشعارات جديدة

سيتم إشعارك هنا عند:
• 💰 استلام أرباح يومية
• 🎁 الحصول على مكافآت إحالة
• ✅ تأكيد المدفوعات
• 📢 الإعلانات المهمة
"""
    else:
        notifications_text = f"🔔 **الإشعارات الجديدة:** ({len(unread_notifications)})\n\n"

        for i, notification in enumerate(unread_notifications, 1):
            notif_id, message, notif_type, created_at = notification

            # تحديد الأيقونة حسب نوع الإشعار
            if notif_type == 'profit':
                icon = "💰"
            elif notif_type == 'referral':
                icon = "🎁"
            elif notif_type == 'payment':
                icon = "💳"
            elif notif_type == 'broadcast':  
                icon = "📢"
            else:
                icon = "ℹ️"

            date_str = created_at.split()[0] if created_at else 'اليوم'

            notifications_text += f"""
{i}. {icon} {message}
   📅 {date_str}
━━━━━━━━━━━━━━━━━━━━
"""

    await update.message.reply_text(notifications_text, parse_mode='Markdown')
    log_user_action(user_id, 'view_notifications')

# 💬 الدعم الفني
async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = update.effective_user

    support_text = f"""
💬 **الدعم الفني - Ribeh**

👋 مرحباً {user.first_name}!

🆔 **معرف المستخدم:** `{user_id}`
📱 **اسم المستخدم:** @{user.username or 'غير متوفر'}

📞 **طرق التواصل:**

1️⃣ **الدعم الفوري:**
   • تليجرام: @ribeh_support
   • متاح 24/7

2️⃣ **الأسئلة الشائعة:**
   • كيفية الاستثمار
   • آلية حساب الأرباح  
   • طرق السحب والإيداع
   • نظام الإحالة

3️⃣ **المساعدة الذاتية:**
   • تحقق من "📊 إحصائيات الأرباح"
   • راجع "📋 مدفوعاتي"
   • اقرأ الإشعارات في 🔔

⚡ **للدعم العاجل:**
أرسل رسالة تحتوي على:
• المشكلة بالتفصيل
• معرف المستخدم: `{user_id}`
• لقطة شاشة إن أمكن

🕐 **أوقات الرد:**
• الدعم الفوري: خلال ساعة
• الاستفسارات العامة: خلال 6 ساعات
• المشاكل التقنية: خلال 24 ساعة

نحن هنا لمساعدتك! 💪
"""

    await update.message.reply_text(support_text, parse_mode='Markdown')
    log_user_action(user_id, 'contact_support')

# 💸 نظام السحب المحسن
async def withdrawal_system(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()
        c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        user_balance = c.fetchone()[0] or 0

        # الحد الأدنى للسحب
        c.execute("SELECT setting_value FROM system_settings WHERE setting_name = 'min_withdrawal_amount'")
        min_amount = int(c.fetchone()[0])

        # رسوم السحب
        c.execute("SELECT setting_value FROM system_settings WHERE setting_name = 'withdrawal_fee_percentage'")
        fee_percentage = int(c.fetchone()[0])

    # السحوبات السابقة
    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()
        c.execute('''SELECT COUNT(*), SUM(amount) FROM withdrawals 
                    WHERE user_id = ? AND status = 'approved' ''', (user_id,))
        withdrawal_count, total_withdrawn = c.fetchone()
        total_withdrawn = total_withdrawn or 0

        # السحوبات المعلقة
        c.execute('''SELECT COUNT(*), SUM(amount) FROM withdrawals 
                    WHERE user_id = ? AND status = 'pending' ''', (user_id,))
        pending_count, pending_amount = c.fetchone()
        pending_amount = pending_amount or 0

    withdrawal_text = f"""
💸 **نظام السحب:**

💰 **رصيدك الحالي:** {user_balance:,} دج
💳 **الرصيد المتاح للسحب:** {user_balance - pending_amount:,} دج

📊 **إحصائيات السحب:**
• عدد السحوبات المكتملة: {withdrawal_count}
• إجمالي المسحوب: {total_withdrawn:,} دج
• سحوبات معلقة: {pending_count} ({pending_amount:,} دج)

📋 **شروط السحب:**
• الحد الأدنى: {min_amount:,} دج
• رسوم السحب: {fee_percentage}%
• مدة المعالجة: 24-48 ساعة

💳 **طرق السحب المتاحة:**
1️⃣ بريدي موب (Baridi Mob)
2️⃣ حساب جاري بريدي (CCP)
3️⃣ Wise (تحويل دولي)
4️⃣ البنك الشعبي الجزائري

📞 **لطلب السحب:**
تواصل مع الدعم الفني: @ribeh_support

📝 **معلومات مطلوبة:**
• رقم الحساب البنكي
• اسم صاحب الحساب (كما في البطاقة)
• المبلغ المطلوب سحبه
• طريقة السحب المفضلة

⚠️ **ملاحظات مهمة:**
• تأكد من صحة البيانات المصرفية
• السحب النهائي = المبلغ - رسوم {fee_percentage}%
• لا يمكن إلغاء طلب السحب بعد الإرسال
• تواصل مع الدعم لأي استفسار

🔒 معلوماتك محمية ومشفرة بالكامل
"""

    await update.message.reply_text(withdrawal_text, parse_mode='Markdown')
    log_user_action(user_id, 'view_withdrawal_system')


            

# 📦 معالج اختيار الباقات
async def select_package(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text

    # استخراج قيمة الباقة من النص
    package_amounts = {
        "💰 2000 دج": 2000,
        "💰 6000 دج": 6000,
        "💰 10000 دج": 10000,
        "💰 15000 دج": 15000,
        "💰 20000 دج": 20000,
        "💰 25000 دج": 25000,
        "💰 30000 دج": 30000,
        "💰 40000 دج": 40000,
        "💰 60000 دج": 60000
    }

    if message_text in package_amounts:
        amount = package_amounts[message_text]

        # حفظ الباقة المختارة في context للاستخدام لاحقاً
        context.user_data['selected_package'] = amount

        # عرض تفاصيل الباقة وطرق الدفع
        daily_profit = calculate_daily_profit(amount)
        total_return = (daily_profit * 40) + amount

        package_details = f"""
✅ تم اختيار باقة {amount:,} دج

📊 تفاصيل الاستثمار:
💰 قيمة الاستثمار: {amount:,} دج
📈 العائد اليومي: {daily_profit} دج
⏰ مدة الاستثمار: 40 يوم
💵 إجمالي العائد: {total_return:,} دج
📊 صافي الربح: {total_return - amount:,} دج

💳 طرق الدفع المتاحة:

1️⃣ 📱 بريدي موب (Baridi Mob)
2️⃣ 💳 حساب جاري بريدي (CCP)  
3️⃣ 🌍 Wise (تحويل دولي)
4️⃣ 💰 USDT (عملة رقمية)

📝 خطوات الإيداع:
1. قم بتحويل {amount:,} دج بإحدى الطرق أعلاه
2. اضغط على 🧾 إثبات الدفع
3. أرسل صورة الإيصال
4. انتظر التأكيد (2-6 ساعات)

⚠️ تأكد من تحويل المبلغ الصحيح: {amount:,} دج
"""

        reply_markup = ReplyKeyboardMarkup(main_menu, resize_keyboard=True)
        await update.message.reply_text(package_details, reply_markup=reply_markup)

    else:
        await update.message.reply_text("❌ باقة غير صحيحة. يرجى اختيار باقة من القائمة.")

def calculate_daily_profit(amount):
    """حساب العائد اليومي بناءً على قيمة الاستثمار"""
    profit_rates = {
        2000: 50,
        6000: 150,
        10000: 250,
        15000: 400,


# 👑 الأوامر الإدارية المتقدمة
async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال رسالة جماعية (للمدير فقط)"""
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("""
📢 **إرسال رسالة جماعية:**

الاستخدام: `/broadcast <الرسالة>`

مثال: `/broadcast أهلاً بكم في Ribeh! تحديث جديد متاح.`

**خيارات الفلترة:**
• `/broadcast_active <الرسالة>` - للمستثمرين النشطين فقط
• `/broadcast_new <الرسالة>` - للمستخدمين الجدد فقط
""")
        return

    message = ' '.join(context.args)

    # إرسال للجميع
    users_count = await send_bulk_notification(f"📢 {message}")

    await update.message.reply_text(f"✅ تم إرسال الرسالة لـ {users_count} مستخدم")

async def admin_broadcast_active(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال رسالة للمستثمرين النشطين فقط"""
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        return

    message = ' '.join(context.args)
    users_count = await send_bulk_notification(f"📢 {message}", 'active_investors')

    await update.message.reply_text(f"✅ تم إرسال الرسالة لـ {users_count} مستثمر نشط")

async def admin_broadcast_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال رسالة للمستخدمين الجدد فقط"""
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        return

    message = ' '.join(context.args)
    users_count = await send_bulk_notification(f"📢 {message}", 'new_users')

    await update.message.reply_text(f"✅ تم إرسال الرسالة لـ {users_count} مستخدم جديد")

async def admin_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض معلومات مستخدم محدد"""
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("الاستخدام: `/userinfo <user_id>`")
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ معرف المستخدم يجب أن يكون رقماً")
        return

    report = generate_user_report(target_user_id)

    if not report:
        await update.message.reply_text("❌ المستخدم غير موجود")
        return

    user_data = report['user']
    profit_stats = report['profits']
    payment_stats = report['payments']
    withdrawal_stats = report['withdrawals']

    info_text = f"""
👤 **معلومات المستخدم:** {user_data[0]}

📱 **البيانات الأساسية:**
• الاسم: {user_data[2] or 'غير متوفر'}
• المعرف: @{user_data[1] or 'غير متوفر'}
• المحيل: {user_data[3] or 'لا يوجد'}
• حالة الحساب: {'نشط' if user_data[14] else 'غير نشط'}
• تاريخ الانضمام: {user_data[15] or 'غير متوفر'}

💰 **الاستثمار والأرباح:**
• الاستثمار: {user_data[4]:,} دج
• الرصيد: {user_data[5]:,} دج
• إجمالي الأرباح: {user_data[12]:,} دج
• أيام الاستثمار: {user_data[8]}
• آخر ربح: {user_data[6] or 'لم يحصل على أرباح'}

🔗 **الإحالة:**
• عدد الإحالات: {user_data[9]}
• مكافآت الإحالة: {user_data[10]:,} دج
• رابط الإحالة: {user_data[11] or 'غير متوفر'}

📊 **إحصائيات الأرباح:**
• عدد أيام الربح: {profit_stats[0] or 0}
• إجمالي الأرباح: {profit_stats[1] or 0:,} دج
• متوسط الربح اليومي: {profit_stats[2] or 0:.1f} دج

💳 **المدفوعات:**
• عدد المدفوعات المُوافقة: {payment_stats[0] or 0}
• إجمالي المدفوعات: {payment_stats[1] or 0:,} دج

💸 **السحوبات:**
• عدد السحوبات: {withdrawal_stats[0] or 0}
• إجمالي المسحوب: {withdrawal_stats[1] or 0:,} دج

🔐 **الأمان:**
• فحص أمان الحساب: {'آمن' if check_user_security(target_user_id)['is_secure'] else 'مشبوه'}
"""

    await update.message.reply_text(info_text, parse_mode='Markdown')

async def admin_system_backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إنشاء نسخة احتياطية يدوية"""
    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text("🔄 جاري إنشاء النسخة الاحتياطية...")

    backup_file = create_backup()

    if backup_file:
        await update.message.reply_text(f"✅ تم إنشاء النسخة الاحتياطية: `{backup_file}`", parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ فشل في إنشاء النسخة الاحتياططية")

async def admin_force_profits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تشغيل حساب الأرباح يدوياً"""
    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text("🔄 جاري حساب الأرباح اليومية...")

    try:
        result = calculate_daily_profits()

        await update.message.reply_text(f"""
✅ **تم حساب الأرباح:**

👥 المستخدمين المُعالجين: {result['processed_users']}
💰 إجمالي الأرباح الموزعة: {result['total_distributed']:,} دج

⏰ الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
""")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ في حساب الأرباح: {str(e)}")

async def admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض وتعديل إعدادات النظام"""
    if update.effective_user.id != ADMIN_ID:
        return

    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()
        c.execute("SELECT setting_name, setting_value, description FROM system_settings")
        settings = c.fetchall()

    settings_text = "⚙️ **إعدادات النظام:**\n\n"

    for setting_name, setting_value, description in settings:
        settings_text += f"• **{description}:** `{setting_value}`\n"
        settings_text += f"  المفتاح: `{setting_name}`\n\n"

    settings_text += """
**لتعديل إعداد:**
`/set_setting <المفتاح> <القيمة الجديدة>`

**مثال:**
`/set_setting referral_bonus_percentage 15`
"""

    await update.message.reply_text(settings_text, parse_mode='Markdown')

async def admin_set_setting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تعديل إعداد في النظام"""
    if update.effective_user.id != ADMIN_ID:
        return

    if len(context.args) < 2:
        await update.message.reply_text("الاستخدام: `/set_setting <المفتاح> <القيمة>`")
        return

    setting_name = context.args[0]
    setting_value = ' '.join(context.args[1:])

    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()

        # التحقق من وجود الإعداد
        c.execute("SELECT description FROM system_settings WHERE setting_name = ?", (setting_name,))
        setting_info = c.fetchone()

        if not setting_info:
            await update.message.reply_text(f"❌ الإعداد `{setting_name}` غير موجود")
            return

        # تحديث الإعداد
        c.execute("""UPDATE system_settings 
                    SET setting_value = ?, updated_at = CURRENT_TIMESTAMP 
                    WHERE setting_name = ?""", (setting_value, setting_name))
        conn.commit()

    await update.message.reply_text(f"""
✅ **تم تحديث الإعداد:**

📝 الإعداد: {setting_info[0]}
🔧 القيمة الجديدة: `{setting_value}`
⏰ الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
""", parse_mode='Markdown')


        20000: 550,
        25000: 700,
        30000: 850,
        40000: 1200,
        60000: 1800
    }
    return profit_rates.get(amount, 0)

# 💳 الإيداع العام
async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    deposit_text = """
💳 طرق الدفع المتاحة:

1️⃣ 📱 بريدي موب (Baridi Mob)
2️⃣ 💳 حساب جاري بريدي (CCP)  
3️⃣ 🌍 Wise (تحويل دولي)
4️⃣ 💰 USDT (عملة رقمية)

📝 خطوات الإيداع:
1. اختر باقة من قائمة 📦 الباقات أولاً
2. قم بتحويل المبلغ
3. اضغط على 🧾 إثبات الدفع
4. أرسل صورة الإيصال

⚠️ تأكد من إرسال إثبات الدفع لتفعيل حسابك
"""
    await update.message.reply_text(deposit_text)

# 💸 السحب
async def withdrawal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    withdrawal_text = """
💸 سحب الأموال:

📋 الشروط:
• الحد الأدنى للسحب: 1000 دج
• رسوم السحب: 2%
• مدة المعالجة: 24-48 ساعة

📞 للسحب تواصل مع الدعم:
@ribeh_support

📄 معلومات مطلوبة:
• رقم الحساب البنكي
• اسم صاحب الحساب
• المبلغ المطلوب سحبه
"""
    await update.message.reply_text(withdrawal_text)

# 🏠 الصفحة الرئيسية
async def home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = ReplyKeyboardMarkup(main_menu, resize_keyboard=True)
    await update.message.reply_text("🏠 أهلاً بك في الصفحة الرئيسية", reply_markup=reply_markup)

# 💰 حساب الأرباح اليومية
def calculate_daily_profits():
    """حساب وإضافة الأرباح اليومية لجميع المستخدمين"""
    today = datetime.now().date()

    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()

        # الحصول على المستخدمين الذين لديهم استثمارات
        c.execute("""
            SELECT user_id, investment, last_profit_date, investment_start_date, investment_days
            FROM users 
            WHERE investment > 0
        """)

        users = c.fetchall()
        processed_users = 0
        total_distributed = 0

        for user_id, investment, last_profit_date, start_date, days in users:
            # التحقق من أن اليوم لم يتم حساب الربح فيه
            if last_profit_date == str(today):
                continue

            # تحديد الباقة والربح اليومي
            package_type = ""
            daily_profit = 0
            max_days = 0

            # حساب الربح اليومي حسب الباقات الجديدة
            if investment == 2000:
                package_type = "المبتدئين"
                daily_profit = 50
                max_days = 40
            elif investment == 6000:
                package_type = "المتوسط"
                daily_profit = 150
                max_days = 40
            elif investment == 10000:
                package_type = "المتقدم"
                daily_profit = 250
                max_days = 40
            elif investment == 15000:
                package_type = "المتقدم +"
                daily_profit = 400
                max_days = 40
            elif investment == 20000:
                package_type = "المحترف"
                daily_profit = 550
                max_days = 40
            elif investment == 25000:
                package_type = "المحترف +"
                daily_profit = 700
                max_days = 40
            elif investment == 30000:
                package_type = "الخبير"
                daily_profit = 850
                max_days = 40
            elif investment == 40000:
                package_type = "الخبير +"
                daily_profit = 1200
                max_days = 40
            elif investment == 60000:
                package_type = "المحترفين"
                daily_profit = 1800
                max_days = 40
            else:
                continue  # استثمار غير معروف

            # التحقق من عدم انتهاء فترة الاستثمار
            if days >= max_days:
                continue

            # إضافة الربح اليومي
            c.execute("""
                INSERT INTO daily_profits (user_id, profit_amount, investment_amount, package_type, profit_date)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, daily_profit, investment, package_type, today))

            # تحديث رصيد المستخدم والتاريخ
            new_days = days + 1
            c.execute("""
                UPDATE users 
                SET balance = balance + ?, 
                    last_profit_date = ?, 
                    investment_days = ?,
                    investment_start_date = COALESCE(investment_start_date, ?),
                    total_earned = total_earned + ?
                WHERE user_id = ?
            """, (daily_profit, today, new_days, today, daily_profit, user_id))

            # إضافة إشعار للمستخدم
            c.execute("""
                INSERT INTO notifications (user_id, message, notification_type)
                VALUES (?, ?, ?)
            """, (user_id, 
                 f"💰 تم إضافة ربح يومي: {daily_profit:,} دج لباقة {package_type}. الرصيد المحدث متاح في ملفك الشخصي!",
                 "profit"))

            # معالجة مكافأة الإحالة للمحيل (5% من الربح اليومي)
            c.execute("SELECT referrer FROM users WHERE user_id = ?", (user_id,))
            referrer_result = c.fetchone()

            if referrer_result and referrer_result[0]:  # إذا كان هناك محيل
                referrer_id = referrer_result[0]
                referral_bonus = int(daily_profit * 0.05)  # 5% من الربح اليومي

                if referral_bonus > 0:  # إضافة مكافأة الإحالة
                    c.execute("""
                        UPDATE users 
                        SET balance = balance + ?, referral_bonus = referral_bonus + ?
                        WHERE user_id = ?
                    """, (referral_bonus, referral_bonus, referrer_id))

                    # تحديث إحصائيات الإحالة
                    c.execute("""
                        UPDATE referrals 
                        SET referral_bonus = referral_bonus + ?
                        WHERE referrer_id = ? AND referred_id = ?
                    """, (referral_bonus, referrer_id, user_id))

                    # إشعار للمحيل
                    c.execute("""
                        INSERT INTO notifications (user_id, message, notification_type)
                        VALUES (?, ?, ?)
                    """, (referrer_id,
                         f"🎁 مكافأة إحالة يومية: {referral_bonus:,} دج من أرباح المُحال ({daily_profit:,} دج)",
                         "referral"))

            processed_users += 1
            total_distributed += daily_profit

        conn.commit()

    return {'processed_users': processed_users, 'total_distributed': total_distributed}



# 🛠️ معالج الأخطاء العام
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """معالج الأخطاء العام للبوت"""

    # تسجيل الخطأ
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    # إرسال إشعار للمدير عن الخطأ
    error_message = f"""
🚨 **خطأ في النظام:**

⏰ الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🔍 نوع الخطأ: {type(context.error).__name__}
📝 التفاصيل: {str(context.error)}

المستخدم: {update.effective_user.id if update and update.effective_user else 'غير محدد'}
الرسالة: {update.message.text if update and update.message else 'غير محدد'}
"""

    try:
        # إرسال إشعار للمدير
        await context.bot.send_message(chat_id=ADMIN_ID, text=error_message)
    except Exception:
        pass  # تجاهل الأخطاء في إرسال إشعار الخطأ

    # إرسال رسالة ودية للمستخدم
    if update and update.effective_user:
        try:
            reply_markup = ReplyKeyboardMarkup(main_menu, resize_keyboard=True)
            await update.message.reply_text("""
⚠️ **عذراً، حدث خطأ مؤقت!**

🔧 تم إرسال تقرير الخطأ للفريق التقني
⏱️ سيتم إصلاح المشكلة قريباً

💡 **يمكنك:**
• المحاولة مرة أخرى بعد قليل
• التواصل مع الدعم: @ribeh_support
• استخدام الأزرار أدناه للمتابعة

شكراً لصبرك! 🙏
""", reply_markup=reply_markup)
        except Exception:
            pass  # تجاهل الأخطاء في إرسال الرسالة للمستخدم


            # حساب الربح اليومي حسب الباقات الجديدة
            if investment == 2000:
                package_type = "المبتدئين"
                daily_profit = 50
                max_days = 40
            elif investment == 6000:
                package_type = "المتوسط"
                daily_profit = 150
                max_days = 40
            elif investment == 10000:
                package_type = "المتقدم"
                daily_profit = 250
                max_days = 40
            elif investment == 15000:
                package_type = "المتقدم +"
                daily_profit = 400
                max_days = 40
            elif investment == 20000:
                package_type = "المحترف"
                daily_profit = 550
                max_days = 40
            elif investment == 25000:
                package_type = "المحترف +"
                daily_profit = 700
                max_days = 40
            elif investment == 30000:
                package_type = "الخبير"
                daily_profit = 850
                max_days = 40
            elif investment == 40000:
                package_type = "الخبير +"
                daily_profit = 1200
                max_days = 40
            elif investment == 60000:
                package_type = "المحترفين"
                daily_profit = 1800
                max_days = 40
            else:
                continue  # استثمار غير معروف

            # التحقق من عدم انتهاء فترة الاستثمار
            if days >= max_days:
                continue

            # إضافة الربح اليومي
            c.execute("""
                INSERT INTO daily_profits (user_id, profit_amount, investment_amount, package_type, profit_date)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, daily_profit, investment, package_type, today))

            # تحديث رصيد المستخدم والتاريخ
            new_days = days + 1
            c.execute("""
                UPDATE users 
                SET balance = balance + ?, 
                    last_profit_date = ?, 
                    investment_days = ?,
                    investment_start_date = COALESCE(investment_start_date, ?),
                    total_earned = total_earned + ?
                WHERE user_id = ?
            """, (daily_profit, today, new_days, today, daily_profit, user_id))

            # إضافة إشعار للمستخدم
            c.execute("""
                INSERT INTO notifications (user_id, message, notification_type)
                VALUES (?, ?, ?)
            """, (user_id, 
                 f"💰 تم إضافة ربح يومي: {daily_profit:,} دج لباقة {package_type}. الرصيد المحدث متاح في ملفك الشخصي!",
                 "profit"))

            # معالجة مكافأة الإحالة للمحيل (5% من الربح اليومي)
            c.execute("SELECT referrer FROM users WHERE user_id = ?", (user_id,))
            referrer_result = c.fetchone()

            if referrer_result and referrer_result[0]:  # إذا كان هناك محيل
                referrer_id = referrer_result[0]
                referral_bonus = int(daily_profit * 0.05)  # 5% من الربح اليومي

                if referral_bonus > 0:  # إضافة مكافأة الإحالة
                    c.execute("""
                        UPDATE users 
                        SET balance = balance + ?, referral_bonus = referral_bonus + ?
                        WHERE user_id = ?
                    """, (referral_bonus, referral_bonus, referrer_id))

                    # تحديث إحصائيات الإحالة
                    c.execute("""
                        UPDATE referrals 
                        SET referral_bonus = referral_bonus + ?
                        WHERE referrer_id = ? AND referred_id = ?
                    """, (referral_bonus, referrer_id, user_id))

                    # إشعار للمحيل
                    c.execute("""
                        INSERT INTO notifications (user_id, message, notification_type)
                        VALUES (?, ?, ?)
                    """, (referrer_id,
                         f"🎁 مكافأة إحالة يومية: {referral_bonus:,} دج من أرباح المُحال ({daily_profit:,} دج)",
                         "referral"))

            processed_users += 1
            total_distributed += daily_profit

        conn.commit()

    return {'processed_users': processed_users, 'total_distributed': total_distributed}

# 📊 إحصائيات الأرباح
async def profit_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()

        # إحصائيات الأرباح
        c.execute("""
            SELECT 
                COUNT(*) as total_days,
                SUM(profit_amount) as total_profits,
                AVG(profit_amount) as avg_profit,
                MIN(profit_date) as first_profit,
                MAX(profit_date) as last_profit
            FROM daily_profits 
            WHERE user_id = ?
        """, (user_id,))

        stats = c.fetchone()

        if not stats or stats[0] == 0:
            await update.message.reply_text("""
📊 إحصائيات الأرباح:

❌ لا توجد أرباح مسجلة بعد
💡 قم بالاستثمار لبدء تحصيل الأرباح اليومية

للاستثمار:
1. اضغط على 📦 الباقات
2. اختر الباقة المناسبة
3. قم بالدفع والتأكيد
""")
            return

        total_days, total_profits, avg_profit, first_profit, last_profit = stats

        # آخر 5 أرباح
        c.execute("""
            SELECT profit_amount, profit_date, package_type
            FROM daily_profits 
            WHERE user_id = ? 
            ORDER BY id DESC 
            LIMIT 5
        """, (user_id,))

        recent_profits = c.fetchall()

    stats_text = f"""
📊 إحصائيات أرباحك:

📈 المعلومات العامة:
• إجمالي الأرباح: {total_profits:,} دج
• عدد أيام الربح: {total_days} يوم
• متوسط الربح اليومي: {avg_profit:.1f} دج
• أول ربح: {first_profit}
• آخر ربح: {last_profit}

📋 آخر 5 أرباح:
"""

    for profit_amount, profit_date, package_type in recent_profits:
        stats_text += f"💰 {profit_amount:,} دج - {profit_date} ({package_type})\n"

    stats_text += """
🎯 نصائح:
• الأرباح تُحسب تلقائياً كل يوم
• يمكنك سحب أرباحك في أي وقت
• كلما زاد الاستثمار، زادت الأرباح

💬 للدعم: @ribeh_support
"""

    await update.message.reply_text(stats_text)

# 📋 مدفوعاتي
async def my_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, method, status, created_at 
            FROM payments 
            WHERE user_id = ? 
            ORDER BY id DESC 
            LIMIT 10
        """, (user_id,))
        payments = c.fetchall()

    if not payments:
        await update.message.reply_text("""
📋 مدفوعاتي:

❌ لا توجد مدفوعات مسجلة لحسابك بعد

💡 لإضافة مدفوعة جديدة:
1. اضغط على 💳 إيداع
2. قم بالتحويل
3. اضغط على 🧾 إثبات الدفع
4. أرسل صورة الإيصال
""")
        return

    payments_text = "📋 مدفوعاتي:\n\n"

    for payment in payments:
        payment_id, method, status, created_at = payment

        # تحديد رمز الحالة
        if status == 'pending':
            status_icon = "⏳"
            status_text = "قيد المراجعة"
        elif status == 'approved':
            status_icon = "✅"
            status_text = "مُفعّلة"
        elif status == 'rejected':
            status_icon = "❌"
            status_text = "مرفوضة"
        else:
            status_icon = "❓"
            status_text = "غير محدد"

        # تنسيق التاريخ
        if created_at:
            date_str = created_at.split()[0]  # أخذ التاريخ فقط
        else:
            date_str = "غير محدد"

        payments_text += f"""
🧾 مدفوعة #{payment_id}
📅 التاريخ: {date_str}
💳 الطريقة: {method}
{status_icon} الحالة: {status_text}
➖➖➖➖➖➖➖➖➖
"""

    payments_text += """
📝 ملاحظات:
⏳ قيد المراجعة: سيتم مراجعتها خلال 2-6 ساعات
✅ مُفعّلة: تم إضافة المبلغ لحسابك
❌ مرفوضة: تواصل مع الدعم للاستفسار

💬 للدعم: @ribeh_support
"""

    await update.message.reply_text(payments_text)

# 🧾 إثبات الدفع
async def proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("""
📷 إرسال إثبات الدفع:

📋 تأكد من وضوح الصورة وظهور:
• تاريخ ووقت التحويل
• المبلغ المحول
• رقم العملية
• اسم المرسل

🖼️ أرسل الآن صورة إثبات الدفع...
""")
    return 1

# حفظ إثبات الدفع
async def save_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()

        # الحصول على قيمة الباقة المختارة إن وجدت
        selected_package = context.user_data.get('selected_package', 0)
        method_info = f"manual - {selected_package} دج" if selected_package > 0 else "manual"

        with sqlite3.connect("ribeh.db") as conn:
            c = conn.cursor()
            c.execute("INSERT INTO payments (user_id, method, proof) VALUES (?, ?, ?)", 
                     (user_id, method_info, photo_bytes))
            conn.commit()

        response_text = """
✅ تم استلام إثبات الدفع بنجاح!

⏰ سيتم مراجعة الدفع خلال 2-6 ساعات
📧 ستصلك رسالة تأكيد عند الموافقة
💼 سيتم تفعيل استثمارك فوراً بعد التأكيد

شكراً لثقتك في Ribeh! 🙏
"""

        if selected_package > 0:
            daily_profit = calculate_daily_profit(selected_package)
            response_text += f"""
📊 تفاصيل الباقة المختارة:
💰 الاستثمار: {selected_package:,} دج
📈 العائد اليومي: {daily_profit} دج
⏰ المدة: 40 يوم
"""

        await update.message.reply_text(response_text)

        # مسح البيانات المحفوظة
        context.user_data.pop('selected_package', None)
    else:
        await update.message.reply_text("❌ يرجى إرسال صورة فقط")
    return ConversationHandler.END

# الإلغاء
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = ReplyKeyboardMarkup(main_menu, resize_keyboard=True)
    await update.message.reply_text("تم الإلغاء 🛑", reply_markup=reply_markup)
    return ConversationHandler.END

# 👑 وظائف الإدارة
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        c.execute("SELECT SUM(investment) FROM users")
        total_investment = c.fetchone()[0] or 0
        c.execute("SELECT COUNT(*) FROM payments")
        total_payments = c.fetchone()[0]

    stats_text = f"""
📊 إحصائيات البوت:

👥 إجمالي المستخدمين: {total_users}
💰 إجمالي الاستثمارات: {total_investment} دج
💳 عدد المدفوعات: {total_payments}
👑 أنت المدير
"""
    await update.message.reply_text(stats_text)

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, username, investment FROM users LIMIT 10")
        users = c.fetchall()

    users_text = "👥 آخر 10 مستخدمين:\n\n"
    for user in users:
        users_text += f"🆔 {user[0]} | @{user[1] or 'لا يوجد'} | {user[2]} دج\n"

    await update.message.reply_text(users_text)

# معالج الرسائل غير المعروفة
async def unknown_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = ReplyKeyboardMarkup(main_menu, resize_keyboard=True)
    await update.message.reply_text("""
❓ **لم أفهم طلبك!**

يرجى استخدام الأزرار أدناه للتنقل في البوت:

🔹 **للاستثمار:** اضغط على "📦 الباقات"
🔹 **لمعرفة أرباحك:** اضغط على "💼 ملفي الشخصي"  
🔹 **للإيداع:** اضغط على "💳 إيداع"
🔹 **للدعم:** اضغط على "💬 الدعم الفني"

💡 **نصيحة:** استخدم الأزرار بدلاً من كتابة الأوامر يدوياً
""", reply_markup=reply_markup)

# 📱 مهمة إرسال الإشعارات
async def notification_sender_task(app):
    """إرسال الإشعارات المعلقة للمستخدمين"""
    while True:
        try:
            with sqlite3.connect("ribeh.db") as conn:
                c = conn.cursor()

                # الحصول على الإشعارات غير المرسلة
                c.execute('''SELECT id, user_id, message, notification_type
                            FROM notifications 
                            WHERE is_read = 0 
                            ORDER BY created_at ASC
                            LIMIT 50''')

                notifications = c.fetchall()

                for notif_id, user_id, message, notif_type in notifications:
                    try:
                        # إرسال الإشعار للمستخدم
                        await app.bot.send_message(
                            chat_id=user_id, 
                            text=f"🔔 {message}",
                            parse_mode='Markdown'
                        )

                        # تحديد الإشعار كمُرسل
                        c.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notif_id,))
                        conn.commit()

                        await asyncio.sleep(1)  # تجنب الإرسال السريع

                    except Exception as e:
                        print(f"❌ فشل إرسال إشعار للمستخدم {user_id}: {e}")
                        continue

            # انتظار 30 ثانية قبل التحقق مرة أخرى
            await asyncio.sleep(30)

        except Exception as e:
            print(f"❌ خطأ في مهمة الإشعارات: {e}")
            await asyncio.sleep(60)

# ⏰ المهام التلقائية المتطورة
async def daily_profit_task():
    """مهمة شاملة تعمل كل 24 ساعة"""
    while True:
        try:
            # انتظار حتى الساعة 12:00 ظهراً
            now = datetime.now()
            next_run = now.replace(hour=12, minute=0, second=0, microsecond=0)

            # إذا كان الوقت قد تجاوز 12:00، انتظر للغد
            if now >= next_run:
                next_run += timedelta(days=1)

            wait_seconds = (next_run - now).total_seconds()

            print(f"⏰ المهام التلقائية ستعمل في: {next_run}")
            await asyncio.sleep(wait_seconds)

            print("🚀 بدء تنفيذ المهام التلقائية...")

            # 1. حساب الأرباح اليومية
            profit_result = calculate_daily_profits()
            print(f"💰 تم توزيع {profit_result['total_distributed']:,} دج على {profit_result['processed_users']} مستخدم")

            # 2. إنشاء نسخة احتياطية
            backup_file = create_backup()
            if backup_file:
                print(f"💾 تم إنشاء نسخة احتياطية: {backup_file}")

            # 3. مراقبة الأداء
            performance_stats = performance_monitor()

            # 4. تنظيف الإشعارات القديمة (أكثر من 30 يوم)
            with sqlite3.connect("ribeh.db") as conn:
                c = conn.cursor()
                c.execute("""
                    DELETE FROM notifications 
                    WHERE created_at < datetime('now', '-30 days')
                """)
                deleted_notifications = c.rowcount
                conn.commit()

            print(f"🧹 تم حذف {deleted_notifications} إشعار قديم")

            # 5. إرسال تقرير يومي للمدير
            daily_report = f"""
📊 التقرير اليومي - {now.strftime('%Y-%m-%d')}

💰 الأرباح الموزعة:
• المستخدمين: {profit_result['processed_users']}
• المبلغ: {profit_result['total_distributed']:,} دج

📈 إحصائيات النظام:
• مستخدمين نشطين: {performance_stats['active_users']}
• إجمالي الاستثمارات: {performance_stats['total_investment']:,} دج
• مدفوعات معلقة: {performance_stats['pending_payments']}
• سحوبات معلقة: {performance_stats['pending_withdrawals']}

🔧 الصيانة:
• تم إنشاء نسخة احتياطية: {'✅' if backup_file else '❌'}
• تم تنظيف {deleted_notifications} إشعار قديم

النظام يعمل بكفاءة عالية! 🚀
"""

            # إرسال التقرير للمدير (إذا كان البوت متاحاً)
            # سيتم تنفيذ هذا لاحقاً عند ربط البوت بالمهام

            print("✅ اكتملت جميع المهام التلقائية بنجاح")

        except Exception as e:
            print(f"❌ خطأ في المهام التلقائية: {e}")
            await asyncio.sleep(3600)  # انتظار ساعة عند حدوث خطأ

def create_backup():
    """إنشاء نسخة احتياطية لقاعدة البيانات"""
    try:
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = f"ribeh_backup_{now}.db"
        with sqlite3.connect("ribeh.db") as conn:
            backup_conn = sqlite3.connect(backup_file)
            with backup_conn:
                conn.backup(backup_conn)
        backup_conn.close()
        return backup_file
    except Exception as e:
        print(f"❌ فشل إنشاء النسخة الاحتياطية: {e}")
        return None

def performance_monitor():
    """مراقبة أداء النظام وإرجاع الإحصائيات"""
    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()

        # المستخدمون النشطون (قاموا بالاستثمار)
        c.execute("SELECT COUNT(*) FROM users WHERE investment > 0")
        active_users = c.fetchone()[0]

        # إجمالي الاستثمارات
        c.execute("SELECT SUM(investment) FROM users")
        total_investment = c.fetchone()[0] or 0

        # المدفوعات المعلقة
        c.execute("SELECT COUNT(*) FROM payments WHERE status = 'pending'")
        pending_payments = c.fetchone()[0]

        # السحوبات المعلقة (افترض أن لديك جدول سحوبات)
        pending_withdrawals = 0 #c.execute("SELECT COUNT(*) FROM withdrawals WHERE status = 'pending'").fetchone()[0]

    return {
        "active_users": active_users,
        "total_investment": total_investment,
        "pending_payments": pending_payments,
        "pending_withdrawals": pending_withdrawals,
    }

# 🔗 وظائف نظام الإحالة
def generate_referral_link(user_id):
    """إنشاء رابط إحالة فريد للمستخدم"""
    import hashlib
    referral_code = hashlib.md5(str(user_id).encode()).hexdigest()[:8]
    
    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET referral_link = ? WHERE user_id = ?", (referral_code, user_id))
        conn.commit()
    
    return referral_code

def process_referral(referral_code, new_user_id):
    """معالجة الإحالة الجديدة"""
    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()
        
        # البحث عن المحيل
        c.execute("SELECT user_id FROM users WHERE referral_link = ?", (referral_code,))
        referrer = c.fetchone()
        
        if referrer and referrer[0] != new_user_id:  # تجنب الإحالة الذاتية
            referrer_id = referrer[0]
            
            # ربط المستخدم الجديد بالمحيل
            c.execute("UPDATE users SET referrer = ? WHERE user_id = ?", (referrer_id, new_user_id))
            
            # إضافة سجل الإحالة
            c.execute("""INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)""", 
                     (referrer_id, new_user_id))
            
            # زيادة عداد الإحالات
            c.execute("UPDATE users SET total_referrals = total_referrals + 1 WHERE user_id = ?", 
                     (referrer_id,))
            
            conn.commit()
            return True
    
    return False

def log_user_action(user_id, action, details=""):
    """تسجيل عمليات المستخدم"""
    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO system_logs (user_id, action, details) VALUES (?, ?, ?)""", 
                 (user_id, action, details))
        conn.commit()

async def send_bulk_notification(message, filter_type="all"):
    """إرسال إشعار جماعي للمستخدمين"""
    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()
        
        # تحديد المستخدمين حسب النوع
        if filter_type == "active_investors":
            c.execute("SELECT user_id FROM users WHERE investment > 0")
        elif filter_type == "new_users":
            c.execute("SELECT user_id FROM users WHERE investment = 0")
        else:
            c.execute("SELECT user_id FROM users")
        
        users = c.fetchall()
        
        # إضافة الإشعارات لقاعدة البيانات
        for user in users:
            c.execute("""INSERT INTO notifications (user_id, message, notification_type) 
                        VALUES (?, ?, ?)""", (user[0], message, "broadcast"))
        
        conn.commit()
        return len(users)

def generate_user_report(user_id):
    """إنشاء تقرير شامل عن المستخدم"""
    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()
        
        # بيانات المستخدم الأساسية
        c.execute("""SELECT * FROM users WHERE user_id = ?""", (user_id,))
        user_data = c.fetchone()
        
        if not user_data:
            return None
        
        # إحصائيات الأرباح
        c.execute("""SELECT COUNT(*), SUM(profit_amount), AVG(profit_amount) 
                    FROM daily_profits WHERE user_id = ?""", (user_id,))
        profit_stats = c.fetchone()
        
        # إحصائيات المدفوعات
        c.execute("""SELECT COUNT(*), SUM(amount) FROM payments 
                    WHERE user_id = ? AND status = 'approved'""", (user_id,))
        payment_stats = c.fetchone()
        
        # إحصائيات السحوبات
        c.execute("""SELECT COUNT(*), SUM(amount) FROM withdrawals 
                    WHERE user_id = ? AND status = 'approved'""", (user_id,))
        withdrawal_stats = c.fetchone()
        
        return {
            'user': user_data,
            'profits': profit_stats,
            'payments': payment_stats,
            'withdrawals': withdrawal_stats
        }

def check_user_security(user_id):
    """فحص أمان حساب المستخدم"""
    with sqlite3.connect("ribeh.db") as conn:
        c = conn.cursor()
        
        # فحص الأنشطة المشبوهة
        c.execute("""SELECT COUNT(*) FROM system_logs 
                    WHERE user_id = ? AND action LIKE '%suspicious%'""", (user_id,))
        suspicious_count = c.fetchone()[0]
        
        # فحص المدفوعات المرفوضة
        c.execute("""SELECT COUNT(*) FROM payments 
                    WHERE user_id = ? AND status = 'rejected'""", (user_id,))
        rejected_payments = c.fetchone()[0]
        
        is_secure = suspicious_count == 0 and rejected_payments < 3
        
        return {
            'is_secure': is_secure,
            'suspicious_activities': suspicious_count,
            'rejected_payments': rejected_payments
        }

# 🧠 تشغيل البوت
def main():
    # إعداد قاعدة البيانات
    init_db()

    app = Application.builder().token(TOKEN).build()

    # إضافة المعالجات الأساسية
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", admin_stats))  # للمدير فقط
    app.add_handler(CommandHandler("users", admin_users))  # للمدير فقط

    # المعالجات الإدارية المتقدمة
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(CommandHandler("broadcast_active", admin_broadcast_active))
    app.add_handler(CommandHandler("broadcast_new", admin_broadcast_new))
    app.add_handler(CommandHandler("userinfo", admin_user_info))
    app.add_handler(CommandHandler("backup", admin_system_backup))
    app.add_handler(CommandHandler("force_profits", admin_force_profits))
    app.add_handler(CommandHandler("settings", admin_settings))
    app.add_handler(CommandHandler("set_setting", admin_set_setting))
    app.add_handler(MessageHandler(filters.Regex("^(📦 الباقات)$"), show_packages))
    app.add_handler(MessageHandler(filters.Regex("^(💼 ملفي الشخصي)$"), show_profile))
    app.add_handler(MessageHandler(filters.Regex("^(💳 إيداع)$"), deposit))
    app.add_handler(MessageHandler(filters.Regex("^(💸 سحب الأموال)$"), withdrawal))
    app.add_handler(MessageHandler(filters.Regex("^(🏠 الصفحة الرئيسية)$"), home))
    app.add_handler(MessageHandler(filters.Regex("^(📋 مدفوعاتي)$"), my_payments))
    app.add_handler(MessageHandler(filters.Regex("^(🔙 العودة للقائمة الرئيسية)$"), home))

    # معالجات الباقات
    app.add_handler(MessageHandler(filters.Regex("^(💰 2000 دج|💰 6000 دج|💰 10000 دج|💰 15000 دج|💰 20000 دج|💰 25000 دج|💰 30000 دج|💰 40000 دج|💰 60000 دج)$"), select_package))
    app.add_handler(MessageHandler(filters.Regex("^(📊 إحصائيات الأرباح)$"), profit_stats))

    # معالج المحادثة لإثبات الدفع
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(🧾 إثبات الدفع)$"), proof)],
        states={1: [MessageHandler(filters.PHOTO, save_proof)]},
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv_handler)

    # إضافة معالجات الميزات الجديدة
    app.add_handler(MessageHandler(filters.Regex("^(🔗 رابط الإحالة)$"), show_referral_link))
    app.add_handler(MessageHandler(filters.Regex("^(👥 إحالاتي)$"), show_my_referrals))
    app.add_handler(MessageHandler(filters.Regex("^(🔔 الإشعارات)$"), show_notifications))
    app.add_handler(MessageHandler(filters.Regex("^(💬 الدعم الفني)$"), show_support))
    app.add_handler(MessageHandler(filters.Regex("^(💸 سحب الأموال)$"), withdrawal_system))

    # معالج الرسائل غير المعروفة (يجب أن يكون الأخير)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown_message))

    # إضافة معالج الأخطاء العام
    app.add_error_handler(error_handler)

    print("🚀 بوت Ribeh بدأ التشغيل...")

    # إضافة مهمة الأرباح التلقائية بعد بدء التطبيق
    async def post_init(application):
        """تشغيل المهام التلقائية بعد تهيئة التطبيق"""
        asyncio.create_task(daily_profit_task())

    # ربط المهمة التلقائية بالتطبيق
    app.post_init = post_init

    # إضافة مهمة إرسال الإشعارات
    async def post_init(application):
        """تشغيل المهام التلقائية بعد تهيئة التطبيق"""
        asyncio.create_task(daily_profit_task())
        asyncio.create_task(notification_sender_task(application))

    # ربط المهمة التلقائية بالتطبيق
    app.post_init = post_init

    # تشغيل البوت
    app.run_polling()

if __name__ == "__main__":
    main()