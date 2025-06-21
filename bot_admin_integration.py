
import asyncio
import sqlite3
from telegram import Bot

# إعدادات البوت
BOT_TOKEN = "7427215837:AAFWgPPm1_pF9fEjUI87nwlVJA-So41FvyQ"
bot = Bot(token=BOT_TOKEN)

class BotAdminIntegration:
    """فئة للتكامل بين لوحة الإدارة والبوت"""
    
    @staticmethod
    async def approve_payment(payment_id, investment_amount):
        """الموافقة على المدفوعة وإرسال إشعار للمستخدم"""
        with sqlite3.connect("ribeh.db") as conn:
            c = conn.cursor()
            
            # الحصول على بيانات المدفوعة
            c.execute('''SELECT p.user_id, u.username, u.first_name
                        FROM payments p
                        JOIN users u ON p.user_id = u.user_id
                        WHERE p.id = ?''', (payment_id,))
            
            payment_data = c.fetchone()
            
            if payment_data:
                user_id, username, first_name = payment_data
                
                # تحديث استثمار المستخدم
                c.execute('''UPDATE users SET 
                            investment = investment + ?,
                            investment_start_date = COALESCE(investment_start_date, DATE('now')),
                            investment_days = 0
                            WHERE user_id = ?''', (investment_amount, user_id))
                
                # تحديث حالة المدفوعة
                c.execute('''UPDATE payments SET 
                            status = 'approved',
                            amount = ?,
                            processed_at = CURRENT_TIMESTAMP
                            WHERE id = ?''', (investment_amount, payment_id))
                
                # إضافة إشعار للمستخدم
                c.execute('''INSERT INTO notifications (user_id, message, notification_type)
                            VALUES (?, ?, ?)''', 
                         (user_id, 
                          f"🎉 تهانينا! تم الموافقة على استثمارك بقيمة {investment_amount:,} دج وبدء تحصيل الأرباح اليومية!",
                          "payment"))
                
                conn.commit()
                
                # إرسال رسالة تأكيد للمستخدم عبر البوت
                try:
                    message = f"""
🎉 **تم تفعيل استثمارك بنجاح!**

👋 مرحباً {first_name}!
✅ تم الموافقة على مدفوعتك
💰 قيمة الاستثمار: {investment_amount:,} دج
📈 ستحصل على أرباح يومية ابتداءً من اليوم

📊 **لمتابعة أرباحك:**
• اضغط على "💼 ملفي الشخصي"
• راجع "📊 إحصائيات الأرباح"

شكراً لثقتك في Ribeh! 🚀
"""
                    await bot.send_message(chat_id=user_id, text=message, parse_mode='Markdown')
                    return True
                except Exception as e:
                    print(f"❌ فشل إرسال إشعار البوت للمستخدم {user_id}: {e}")
                    return True  # المعاملة نجحت حتى لو فشل الإشعار
                    
        return False
    
    @staticmethod
    async def reject_payment(payment_id, reason=""):
        """رفض المدفوعة وإرسال إشعار للمستخدم"""
        with sqlite3.connect("ribeh.db") as conn:
            c = conn.cursor()
            
            # الحصول على بيانات المدفوعة
            c.execute('''SELECT p.user_id, u.username, u.first_name
                        FROM payments p
                        JOIN users u ON p.user_id = u.user_id
                        WHERE p.id = ?''', (payment_id,))
            
            payment_data = c.fetchone()
            
            if payment_data:
                user_id, username, first_name = payment_data
                
                # تحديث حالة المدفوعة
                c.execute('''UPDATE payments SET 
                            status = 'rejected',
                            admin_notes = ?,
                            processed_at = CURRENT_TIMESTAMP
                            WHERE id = ?''', (reason, payment_id))
                
                # إضافة إشعار للمستخدم
                reason_text = f"\nالسبب: {reason}" if reason else ""
                c.execute('''INSERT INTO notifications (user_id, message, notification_type)
                            VALUES (?, ?, ?)''', 
                         (user_id, 
                          f"❌ عذراً، تم رفض مدفوعتك. يرجى التواصل مع الدعم للاستفسار.{reason_text}",
                          "payment"))
                
                conn.commit()
                
                # إرسال رسالة للمستخدم عبر البوت
                try:
                    message = f"""
❌ **تم رفض المدفوعة**

👋 مرحباً {first_name}،
للأسف تم رفض مدفوعتك{reason_text}

💬 **للاستفسار:**
تواصل مع الدعم الفني: @ribeh_support

📝 **إرشادات:**
• تأكد من وضوح إثبات الدفع
• تأكد من صحة المبلغ المُحول
• تأكد من ظهور تاريخ التحويل

نحن هنا لمساعدتك! 🤝
"""
                    await bot.send_message(chat_id=user_id, text=message, parse_mode='Markdown')
                    return True
                except Exception as e:
                    print(f"❌ فشل إرسال إشعار البوت للمستخدم {user_id}: {e}")
                    return True
                    
        return False
    
    @staticmethod
    async def send_broadcast(message, filter_type="all"):
        """إرسال رسالة جماعية عبر البوت"""
        with sqlite3.connect("ribeh.db") as conn:
            c = conn.cursor()
            
            # تحديد المستخدمين حسب الفلتر
            if filter_type == "active":
                c.execute("SELECT user_id FROM users WHERE investment > 0")
            elif filter_type == "new":
                c.execute("SELECT user_id FROM users WHERE investment = 0")
            else:
                c.execute("SELECT user_id FROM users")
            
            users = c.fetchall()
            sent_count = 0
            
            for user in users:
                try:
                    await bot.send_message(
                        chat_id=user[0], 
                        text=f"📢 **إعلان من إدارة Ribeh:**\n\n{message}",
                        parse_mode='Markdown'
                    )
                    sent_count += 1
                    await asyncio.sleep(0.5)  # تجنب حدود التليجرام
                except Exception as e:
                    continue
            
            return sent_count

# دوال مساعدة للاستخدام في لوحة التحكم
def approve_payment_sync(payment_id, investment_amount):
    """نسخة متزامنة للموافقة على المدفوعة"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            BotAdminIntegration.approve_payment(payment_id, investment_amount)
        )
    finally:
        loop.close()

def reject_payment_sync(payment_id, reason=""):
    """نسخة متزامنة لرفض المدفوعة"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            BotAdminIntegration.reject_payment(payment_id, reason)
        )
    finally:
        loop.close()

def send_broadcast_sync(message, filter_type="all"):
    """نسخة متزامنة للرسالة الجماعية"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            BotAdminIntegration.send_broadcast(message, filter_type)
        )
    finally:
        loop.close()
import sqlite3
import asyncio
from datetime import datetime

# متغير عام للبوت
bot_app = None

def set_bot_app(app):
    """تعيين تطبيق البوت للاستخدام في التكامل"""
    global bot_app
    bot_app = app

def send_broadcast_sync(message, filter_type='all'):
    """إرسال رسالة جماعية بطريقة متزامنة"""
    try:
        with sqlite3.connect("ribeh.db") as conn:
            c = conn.cursor()
            
            # تحديد المستخدمين حسب الفلتر
            if filter_type == 'active_investors':
                c.execute("SELECT user_id FROM users WHERE investment > 0")
            elif filter_type == 'new_users':
                c.execute("SELECT user_id FROM users WHERE investment = 0")
            else:
                c.execute("SELECT user_id FROM users WHERE is_active = 1")
            
            users = c.fetchall()
            
            # إضافة الإشعارات لقاعدة البيانات
            for user in users:
                c.execute('''INSERT INTO notifications (user_id, message, notification_type) 
                            VALUES (?, ?, ?)''', (user[0], message, 'broadcast'))
            
            conn.commit()
            return len(users)
    except Exception as e:
        print(f"خطأ في إرسال الرسالة الجماعية: {e}")
        return 0

def approve_payment_sync(payment_id, investment_amount):
    """الموافقة على مدفوعة وتفعيل الاستثمار"""
    try:
        with sqlite3.connect("ribeh.db") as conn:
            c = conn.cursor()
            
            # الحصول على تفاصيل المدفوعة
            c.execute('''SELECT p.user_id, u.username 
                        FROM payments p
                        JOIN users u ON p.user_id = u.user_id
                        WHERE p.id = ?''', (payment_id,))
            
            payment_info = c.fetchone()
            
            if not payment_info:
                return False
            
            user_id, username = payment_info
            
            # تحديث الاستثمار والحالة
            c.execute('''UPDATE users 
                        SET investment = investment + ?,
                            investment_start_date = COALESCE(investment_start_date, ?),
                            is_active = 1
                        WHERE user_id = ?''', 
                     (investment_amount, datetime.now().date(), user_id))
            
            # تحديث حالة المدفوعة
            c.execute('''UPDATE payments 
                        SET status = 'approved', 
                            amount = ?,
                            processed_at = CURRENT_TIMESTAMP
                        WHERE id = ?''', 
                     (investment_amount, payment_id))
            
            # إضافة إشعار للمستخدم
            c.execute('''INSERT INTO notifications (user_id, message, notification_type) 
                        VALUES (?, ?, ?)''', 
                     (user_id, 
                      f"✅ تم تفعيل استثمارك بقيمة {investment_amount:,} دج! ستبدأ أرباحك اليومية قريباً.",
                      'payment'))
            
            # معالجة مكافأة الإحالة إذا كان هناك محيل
            c.execute("SELECT referrer FROM users WHERE user_id = ?", (user_id,))
            referrer_result = c.fetchone()
            
            if referrer_result and referrer_result[0]:
                referrer_id = referrer_result[0]
                
                # حساب مكافأة الإحالة (10% من الاستثمار)
                referral_bonus = int(investment_amount * 0.10)
                
                # إضافة المكافأة للمحيل
                c.execute('''UPDATE users 
                            SET balance = balance + ?,
                                referral_bonus = referral_bonus + ?
                            WHERE user_id = ?''', 
                         (referral_bonus, referral_bonus, referrer_id))
                
                # تحديث سجل الإحالة
                c.execute('''UPDATE referrals 
                            SET referral_bonus = referral_bonus + ?
                            WHERE referrer_id = ? AND referred_id = ?''', 
                         (referral_bonus, referrer_id, user_id))
                
                # إشعار للمحيل
                c.execute('''INSERT INTO notifications (user_id, message, notification_type) 
                            VALUES (?, ?, ?)''', 
                         (referrer_id,
                          f"🎁 مكافأة إحالة: {referral_bonus:,} دج من استثمار @{username} ({investment_amount:,} دج)",
                          'referral'))
            
            conn.commit()
            return True
            
    except Exception as e:
        print(f"خطأ في الموافقة على المدفوعة: {e}")
        return False

def reject_payment_sync(payment_id, reason=""):
    """رفض مدفوعة"""
    try:
        with sqlite3.connect("ribeh.db") as conn:
            c = conn.cursor()
            
            # الحصول على تفاصيل المدفوعة
            c.execute('''SELECT p.user_id, u.username 
                        FROM payments p
                        JOIN users u ON p.user_id = u.user_id
                        WHERE p.id = ?''', (payment_id,))
            
            payment_info = c.fetchone()
            
            if not payment_info:
                return False
            
            user_id, username = payment_info
            
            # تحديث حالة المدفوعة
            c.execute('''UPDATE payments 
                        SET status = 'rejected',
                            admin_notes = ?,
                            processed_at = CURRENT_TIMESTAMP
                        WHERE id = ?''', 
                     (reason, payment_id))
            
            # إضافة إشعار للمستخدم
            rejection_message = f"❌ تم رفض مدفوعتك."
            if reason:
                rejection_message += f" السبب: {reason}"
            rejection_message += " يرجى التواصل مع الدعم للاستفسار."
            
            c.execute('''INSERT INTO notifications (user_id, message, notification_type) 
                        VALUES (?, ?, ?)''', 
                     (user_id, rejection_message, 'payment'))
            
            conn.commit()
            return True
            
    except Exception as e:
        print(f"خطأ في رفض المدفوعة: {e}")
        return False

def get_user_stats():
    """الحصول على إحصائيات المستخدمين للوحة الإدارة"""
    try:
        with sqlite3.connect("ribeh.db") as conn:
            c = conn.cursor()
            
            stats = {}
            
            # إجمالي المستخدمين
            c.execute("SELECT COUNT(*) FROM users")
            stats['total_users'] = c.fetchone()[0]
            
            # المستخدمين النشطين
            c.execute("SELECT COUNT(*) FROM users WHERE investment > 0")
            stats['active_users'] = c.fetchone()[0]
            
            # إجمالي الاستثمارات
            c.execute("SELECT SUM(investment) FROM users")
            stats['total_investment'] = c.fetchone()[0] or 0
            
            # المدفوعات المعلقة
            c.execute("SELECT COUNT(*) FROM payments WHERE status = 'pending'")
            stats['pending_payments'] = c.fetchone()[0]
            
            # إجمالي الأرباح الموزعة
            c.execute("SELECT SUM(profit_amount) FROM daily_profits")
            stats['total_profits_distributed'] = c.fetchone()[0] or 0
            
            return stats
            
    except Exception as e:
        print(f"خطأ في الحصول على الإحصائيات: {e}")
        return {}

def send_user_notification(user_id, message, notification_type='admin'):
    """إرسال إشعار لمستخدم محدد"""
    try:
        with sqlite3.connect("ribeh.db") as conn:
            c = conn.cursor()
            c.execute('''INSERT INTO notifications (user_id, message, notification_type) 
                        VALUES (?, ?, ?)''', (user_id, message, notification_type))
            conn.commit()
            return True
    except Exception as e:
        print(f"خطأ في إرسال الإشعار: {e}")
        return False
