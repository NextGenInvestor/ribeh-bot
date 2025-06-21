
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
import sqlite3
import os
from datetime import datetime, timedelta
import hashlib

app = Flask(__name__)
app.secret_key = 'ribeh_admin_secret_key_2024'

# بيانات المدير
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "ribeh123"  # يمكنك تغيير كلمة المرور

# التحقق من تسجيل الدخول
def is_logged_in():
    return session.get('logged_in', False)

def get_db_connection():
    conn = sqlite3.connect('ribeh.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    if not is_logged_in():
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash('تم تسجيل الدخول بنجاح!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('تم تسجيل الخروج بنجاح!', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if not is_logged_in():
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # إحصائيات عامة
    total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    total_investment = conn.execute('SELECT SUM(investment) FROM users').fetchone()[0] or 0
    total_payments = conn.execute('SELECT COUNT(*) FROM payments').fetchone()[0]
    total_referrals = conn.execute('SELECT SUM(total_referrals) FROM users').fetchone()[0] or 0
    total_referral_bonus = conn.execute('SELECT SUM(referral_bonus) FROM users').fetchone()[0] or 0
    
    # المستخدمين الجدد اليوم (إفتراضي - يحتاج إضافة عمود التاريخ)
    new_users_today = 0
    
    # أحدث المستخدمين
    recent_users = conn.execute('''
        SELECT user_id, username, investment 
        FROM users 
        ORDER BY user_id DESC 
        LIMIT 5
    ''').fetchall()
    
    # المدفوعات المعلقة
    pending_payments = conn.execute('''
        SELECT p.id, p.user_id, u.username, p.method, p.created_at
        FROM payments p
        JOIN users u ON p.user_id = u.user_id
        WHERE p.status = 'pending'
        ORDER BY p.id DESC
        LIMIT 5
    ''').fetchall()
    
    conn.close()
    
    stats = {
        'total_users': total_users,
        'total_investment': total_investment,
        'total_payments': total_payments,
        'new_users_today': new_users_today,
        'total_referrals': total_referrals,
        'total_referral_bonus': total_referral_bonus
    }
    
    return render_template('dashboard.html', 
                         stats=stats, 
                         recent_users=recent_users,
                         pending_payments=pending_payments)

@app.route('/users')
def users():
    if not is_logged_in():
        return redirect(url_for('login'))
    
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    conn = get_db_connection()
    
    # إجمالي المستخدمين
    total = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    
    # المستخدمين للصفحة الحالية
    users = conn.execute('''
        SELECT user_id, username, investment
        FROM users
        ORDER BY user_id DESC
        LIMIT ? OFFSET ?
    ''', (per_page, (page - 1) * per_page)).fetchall()
    
    conn.close()
    
    # حساب الصفحات
    total_pages = (total + per_page - 1) // per_page
    
    return render_template('users.html', 
                         users=users, 
                         page=page, 
                         total_pages=total_pages,
                         total=total)

@app.route('/payments')
def payments():
    if not is_logged_in():
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    payments = conn.execute('''
        SELECT p.id, p.user_id, u.username, p.method, p.status, p.created_at
        FROM payments p
        JOIN users u ON p.user_id = u.user_id
        ORDER BY p.id DESC
    ''').fetchall()
    
    conn.close()
    
    return render_template('payments.html', payments=payments)

@app.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    if request.method == 'POST':
        investment = request.form['investment']
        
        conn.execute('''
            UPDATE users SET investment = ? WHERE user_id = ?
        ''', (investment, user_id))
        conn.commit()
        conn.close()
        
        flash('تم تحديث بيانات المستخدم بنجاح!', 'success')
        return redirect(url_for('users'))
    
    user = conn.execute('''
        SELECT user_id, username, investment
        FROM users WHERE user_id = ?
    ''', (user_id,)).fetchone()
    
    conn.close()
    
    if user is None:
        flash('المستخدم غير موجود!', 'error')
        return redirect(url_for('users'))
    
    return render_template('edit_user.html', user=user)

@app.route('/delete_user/<int:user_id>')
def delete_user(user_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # حذف المدفوعات أولاً
    conn.execute('DELETE FROM payments WHERE user_id = ?', (user_id,))
    # حذف المستخدم
    conn.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    flash('تم حذف المستخدم بنجاح!', 'success')
    return redirect(url_for('users'))

@app.route('/view_payment/<int:payment_id>')
def view_payment(payment_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    payment = conn.execute('''
        SELECT p.id, p.user_id, u.username, p.method, p.proof, p.status, p.created_at
        FROM payments p
        JOIN users u ON p.user_id = u.user_id
        WHERE p.id = ?
    ''', (payment_id,)).fetchone()
    
    conn.close()
    
    if payment is None:
        flash('المدفوعة غير موجودة!', 'error')
        return redirect(url_for('payments'))
    
    return render_template('view_payment.html', payment=payment)

@app.route('/stats')
def stats():
    if not is_logged_in():
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # إحصائيات تفصيلية
    stats_data = {
        'total_users': conn.execute('SELECT COUNT(*) FROM users').fetchone()[0],
        'total_investment': conn.execute('SELECT SUM(investment) FROM users').fetchone()[0] or 0,
        'total_payments': conn.execute('SELECT COUNT(*) FROM payments').fetchone()[0],
        'avg_investment': conn.execute('SELECT AVG(investment) FROM users WHERE investment > 0').fetchone()[0] or 0,
        'max_investment': conn.execute('SELECT MAX(investment) FROM users').fetchone()[0] or 0,
        'users_with_investment': conn.execute('SELECT COUNT(*) FROM users WHERE investment > 0').fetchone()[0]
    }
    
    # توزيع الاستثمارات
    investment_ranges = conn.execute('''
        SELECT 
            COUNT(CASE WHEN investment = 0 THEN 1 END) as no_investment,
            COUNT(CASE WHEN investment = 2000 THEN 1 END) as basic_package,
            COUNT(CASE WHEN investment = 10000 THEN 1 END) as advanced_package,
            COUNT(CASE WHEN investment = 60000 THEN 1 END) as pro_package,
            COUNT(CASE WHEN investment > 0 AND investment NOT IN (2000, 10000, 60000) THEN 1 END) as custom_investment
        FROM users
    ''').fetchone()
    
    conn.close()
    
    return render_template('stats.html', 
                         stats=stats_data,
                         investment_ranges=investment_ranges)

@app.route('/broadcast', methods=['GET', 'POST'])
def broadcast():
    if not is_logged_in():
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        message = request.form['message']
        filter_type = request.form.get('filter_type', 'all')
        
        try:
            from bot_admin_integration import send_broadcast_sync
            sent_count = send_broadcast_sync(message, filter_type)
            flash(f'تم إرسال الرسالة لـ {sent_count} مستخدم بنجاح!', 'success')
        except Exception as e:
            flash(f'حدث خطأ في إرسال الرسالة: {str(e)}', 'error')
        
        return redirect(url_for('broadcast'))
    
    return render_template('broadcast.html')

@app.route('/approve_payment/<int:payment_id>')
def approve_payment(payment_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # الحصول على تفاصيل المدفوعة
    payment = conn.execute('''
        SELECT p.user_id, u.username, p.method
        FROM payments p
        JOIN users u ON p.user_id = u.user_id
        WHERE p.id = ?
    ''', (payment_id,)).fetchone()
    
    if payment:
        # تحديث حالة المدفوعة إلى موافق
        conn.execute('''
            UPDATE payments SET status = 'approved' WHERE id = ?
        ''', (payment_id,))
        
        # يمكنك هنا إضافة الاستثمار للمستخدم (مثال)
        # conn.execute('UPDATE users SET investment = investment + ? WHERE user_id = ?', (amount, payment.user_id))
        
        conn.commit()
        flash(f'تم الموافقة على المدفوعة للمستخدم @{payment["username"]}', 'success')
    else:
        flash('المدفوعة غير موجودة!', 'error')
    
    conn.close()
    return redirect(url_for('payments'))

@app.route('/reject_payment/<int:payment_id>')
def reject_payment(payment_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    
    # الحصول على تفاصيل المدفوعة
    payment = conn.execute('''
        SELECT p.user_id, u.username, p.method
        FROM payments p
        JOIN users u ON p.user_id = u.user_id
        WHERE p.id = ?
    ''', (payment_id,)).fetchone()
    
    if payment:
        # تحديث حالة المدفوعة إلى مرفوض
        conn.execute('''
            UPDATE payments SET status = 'rejected' WHERE id = ?
        ''', (payment_id,))
        
        conn.commit()
        flash(f'تم رفض المدفوعة للمستخدم @{payment["username"]}', 'warning')
    else:
        flash('المدفوعة غير موجودة!', 'error')
    
    conn.close()
    return redirect(url_for('payments'))

@app.route('/calculate_profits')
def calculate_profits_manual():
    if not is_logged_in():
        return redirect(url_for('login'))
    
    try:
        # استيراد الدالة من main.py
        import sys
        import os
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from main import calculate_daily_profits
        
        processed = calculate_daily_profits()
        flash(f'تم حساب الأرباح بنجاح لـ {processed} مستخدم!', 'success')
    except Exception as e:
        flash(f'حدث خطأ في حساب الأرباح: {str(e)}', 'error')
    
    return redirect(url_for('dashboard'))

@app.route('/set_investment/<int:payment_id>', methods=['POST'])
def set_investment(payment_id):
    if not is_logged_in():
        return redirect(url_for('login'))
    
    investment_amount = request.form.get('investment_amount', type=int)
    
    if not investment_amount or investment_amount <= 0:
        flash('مبلغ الاستثمار غير صحيح!', 'error')
        return redirect(url_for('view_payment', payment_id=payment_id))
    
    # استخدام التكامل مع البوت
    try:
        from bot_admin_integration import approve_payment_sync
        success = approve_payment_sync(payment_id, investment_amount)
        
        if success:
            flash(f'تم تفعيل الاستثمار بقيمة {investment_amount:,} دج وإرسال إشعار للمستخدم عبر البوت!', 'success')
        else:
            flash('حدث خطأ في تفعيل الاستثمار!', 'error')
    except Exception as e:
        # التراجع للطريقة التقليدية في حالة فشل التكامل
        conn = get_db_connection()
        
        payment = conn.execute('''
            SELECT p.user_id, u.username
            FROM payments p
            JOIN users u ON p.user_id = u.user_id
            WHERE p.id = ?
        ''', (payment_id,)).fetchone()
        
        if payment:
            conn.execute('''
                UPDATE users SET investment = investment + ? WHERE user_id = ?
            ''', (investment_amount, payment['user_id']))
            
            conn.execute('''
                UPDATE payments SET status = 'approved' WHERE id = ?
            ''', (payment_id,))
            
            conn.commit()
            flash(f'تم تفعيل الاستثمار بقيمة {investment_amount:,} دج (بدون إشعار البوت)', 'warning')
        else:
            flash('المدفوعة غير موجودة!', 'error')
        
        conn.close()
    
    return redirect(url_for('payments'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
