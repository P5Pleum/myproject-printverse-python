# ================================================================================
# ระบบตลาดกลางโมเดล 3 มิติ (PrintVerse 3D Print Marketplace)
# ไฟล์หลักของระบบ: app.py
# หน้าที่: จัดการเส้นทาง (Routes), การตรวจสอบสิทธิ์, ตะกร้าสินค้า, การซื้อขาย,
#        ระบบเติมเงิน, ระบบแจ้งเตือน, และส่วนควบคุมของผู้ดูแลระบบ (Admin Panel)
# ================================================================================

# --------------------------------------------------------------------------------
# ส่วนที่ 1: การนำเข้าโมดูลและไลบรารีที่จำเป็น (Imports & Libraries)
# --------------------------------------------------------------------------------
import os                                      # จัดการเส้นทางไฟล์และโฟลเดอร์ในระบบปฏิบัติการ
import io                                      # สำหรับจัดการ Byte Streams ในหน่วยความจำ
import zipfile                                 # สำหรับสร้างและแตกไฟล์ ZIP
import re                                      # จัดการ Regular Expressions สำหรับทำความสะอาดชื่อไฟล์
import uuid                                    # สุ่มสร้าง Unique ID สำหรับตั้งชื่อไฟล์อัปโหลดไม่ให้ซ้ำกัน
import base64                                  # สำหรับถอดรหัสรูปภาพ Base64 จากกล้องเว็บแคม
import time                                    # สำหรับสร้าง Timestamp ชื่อไฟล์
import random                                  # สำหรับสุ่มรหัส OTP 6 หลัก
import json                                    # สำหรับโหลดและบันทึกการตั้งค่า SMTP
import smtplib                                 # สำหรับส่งอีเมลผ่านโปรโตคอล SMTP
from email.mime.text import MIMEText           # สร้างข้อความ Plaintext และ HTML อีเมล
from email.mime.multipart import MIMEMultipart # สร้างอีเมลแบบหลายส่วน (Multipart)
from datetime import datetime, timedelta       # จัดการวันเวลาและเวลาหมดอายุของ OTP
from flask import (                            # ไลบรารีเว็บเฟรมเวิร์ก Flask
    Flask, render_template, redirect, url_for, 
    flash, request, session, send_from_directory, send_file, jsonify
)
from flask_login import (                      # ระบบจัดการการเข้าสู่ระบบและสถานะผู้ใช้ (Authentication)
    LoginManager, login_user, logout_user, login_required, current_user
)
from models import (                           # โมเดลฐานข้อมูล SQLAlchemy ที่กำหนดไว้ใน models.py
    db, User, Model3D, PrintSetting, FilamentRequirement, ModelPurchase, TopupTransaction,
    ModelLike, WithdrawalTransaction, EmailOTP
)
from translations import get_translation      # ระบบพจนานุกรม 2 ภาษา (ไทย / อังกฤษ)


# --------------------------------------------------------------------------------
# ส่วนที่ 2: ฟังก์ชันช่วยจัดการฐานข้อมูลและการเตรียมข้อมูลเริ่มต้น (Database Helpers & Seeding)
# --------------------------------------------------------------------------------

def ensure_database_schema(db_path):
    """
    ฟังก์ชันตรวจสอบและอัปเดต Schema ของตาราง SQLite ให้ตรงกับโมเดลปัจจุบันอัตโนมัติ (Auto Migration)
    - เพิ่มคอลัมน์ 'is_admin' ในตาราง users หากยังไม่มี
    - เพิ่มคอลัมน์ 'status' และ 'is_approved' ในตาราง models_3d เพื่อรองรับระบบตรวจอนุมัติโมเดล
    - เพิ่มคอลัมน์ 'seller_id' และ 'seller_income' ในตาราง model_purchases เพื่อรองรับรายได้คนขาย
    """
    import sqlite3
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # ตรวจสอบคอลัมน์ในตาราง users
        cursor.execute("PRAGMA table_info(users)")
        user_columns = [col[1] for col in cursor.fetchall()]
        if user_columns and "is_admin" not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT 0")
            conn.commit()
        if user_columns and "avatar_url" not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN avatar_url VARCHAR(255)")
            conn.commit()
        if user_columns and "address" not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN address TEXT")
            conn.commit()
        if user_columns and "email_verified" not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT 1")
            conn.commit()

        # ตรวจสอบและสร้างตาราง email_otps สำหรับระบบ OTP
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_otps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email VARCHAR(120) NOT NULL,
                otp_code VARCHAR(6) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_at DATETIME NOT NULL,
                is_used BOOLEAN DEFAULT 0
            )
        """)
        conn.commit()

        # ตรวจสอบคอลัมน์ในตาราง models_3d
        cursor.execute("PRAGMA table_info(models_3d)")
        model_columns = [col[1] for col in cursor.fetchall()]
        if model_columns:
            if "status" not in model_columns:
                cursor.execute("ALTER TABLE models_3d ADD COLUMN status VARCHAR(30) DEFAULT 'อนุมัติแล้ว'")
                conn.commit()
            if "is_approved" not in model_columns:
                cursor.execute("ALTER TABLE models_3d ADD COLUMN is_approved BOOLEAN DEFAULT 1")
                conn.commit()
            if "likes_count" not in model_columns:
                cursor.execute("ALTER TABLE models_3d ADD COLUMN likes_count INTEGER DEFAULT 0")
                conn.commit()
            if "file_path" not in model_columns:
                cursor.execute("ALTER TABLE models_3d ADD COLUMN file_path VARCHAR(255)")
                conn.commit()
            # อัปเดตข้อมูลเก่าให้มีสถานะเป็น 'อนุมัติแล้ว' เป็นค่าเริ่มต้น
            cursor.execute("UPDATE models_3d SET is_approved = 1, status = 'อนุมัติแล้ว' WHERE is_approved IS NULL OR status IS NULL")
            cursor.execute("UPDATE models_3d SET likes_count = 0 WHERE likes_count IS NULL")
            conn.commit()

        # ตรวจสอบคอลัมน์ในตาราง model_purchases เพื่อรองรับรายได้คนขาย (Seller Earnings)
        cursor.execute("PRAGMA table_info(model_purchases)")
        purchase_columns = [col[1] for col in cursor.fetchall()]
        if purchase_columns:
            if "seller_id" not in purchase_columns:
                cursor.execute("ALTER TABLE model_purchases ADD COLUMN seller_id INTEGER")
                conn.commit()
            if "seller_income" not in purchase_columns:
                cursor.execute("ALTER TABLE model_purchases ADD COLUMN seller_income FLOAT DEFAULT 0.0")
                conn.commit()

        conn.close()


def get_smtp_config():
    """
    ฟังก์ชันอ่านการตั้งค่า SMTP อีเมลผู้ส่ง (Sender Email Configuration)
    - รองรับการอ่านจากไฟล์ smtp_config.json หรือตัวแปร Environment
    """
    config_file = os.path.join(os.path.dirname(__file__), "smtp_config.json")
    cfg = {
        "MAIL_SERVER": os.environ.get("MAIL_SERVER", "smtp.gmail.com"),
        "MAIL_PORT": int(os.environ.get("MAIL_PORT", 587)),
        "MAIL_USE_TLS": os.environ.get("MAIL_USE_TLS", "True").lower() in ("true", "1"),
        "MAIL_USERNAME": os.environ.get("MAIL_USERNAME", "").strip(),
        "MAIL_PASSWORD": os.environ.get("MAIL_PASSWORD", "").strip(),
        "SENDER_NAME": os.environ.get("SENDER_NAME", "PrintVerse 3D Security").strip()
    }
    if os.path.exists(config_file):
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
                for k in cfg:
                    if k in saved and str(saved[k]).strip() != "":
                        cfg[k] = saved[k]
        except Exception as e:
            print(f"[CONFIG WARNING] Could not read smtp_config.json: {e}")
    return cfg


def send_registration_otp_email(recipient_email, otp_code, username="สมาชิกใหม่"):
    """
    ฟังก์ชันส่งรหัส OTP 6 หลักไปยังอีเมลจริงของผู้สมัครสมาชิก
    - หากมีการตั้งค่า SMTP Server ใน Environment หรือ smtp_config.json (เช่น Gmail SMTP) ระบบจะส่งเมลจริง
    - หากยังไม่ได้ตั้งค่า SMTP หรืออยู่ในโหมด Local Dev ระบบจะบันทึก Log และแสดงโค้ด OTP ให้ผู้ใช้ทราบ
    """
    cfg = get_smtp_config()
    mail_server = cfg["MAIL_SERVER"]
    mail_port = int(cfg["MAIL_PORT"])
    mail_username = cfg["MAIL_USERNAME"]
    mail_password = cfg["MAIL_PASSWORD"]
    mail_use_tls = bool(cfg["MAIL_USE_TLS"])
    sender_name = cfg["SENDER_NAME"]
    sender_email = mail_username or "official@printverse.com"

    subject = f"[PrintVerse 3D] รหัส OTP ยืนยันการสมัครสมาชิก: {otp_code}"
    
    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #FAF8F5; margin: 0; padding: 20px; color: #1C1917; }}
    .container {{ max-width: 520px; margin: 0 auto; background: #ffffff; border: 1px solid #E7E2D9; border-radius: 24px; padding: 32px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
    .header {{ text-align: center; border-bottom: 1px solid #E7E2D9; padding-bottom: 20px; margin-bottom: 24px; }}
    .brand {{ font-size: 22px; font-weight: 800; color: #1C1917; letter-spacing: -0.5px; }}
    .brand span {{ color: #FF6B4A; }}
    .badge {{ display: inline-block; padding: 4px 12px; border-radius: 999px; background: #FAF8F5; border: 1px solid #E7E2D9; font-size: 11px; font-weight: 600; color: #78716C; margin-top: 8px; }}
    .otp-box {{ background: #FAF8F5; border: 2px dashed #FF6B4A; border-radius: 16px; padding: 20px; text-align: center; margin: 28px 0; }}
    .otp-code {{ font-size: 36px; font-weight: 900; letter-spacing: 8px; color: #FF6B4A; font-family: monospace; }}
    .footer {{ text-align: center; font-size: 11px; color: #A8A29E; border-top: 1px solid #E7E2D9; padding-top: 20px; margin-top: 28px; line-height: 1.6; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="brand">PrintVerse<span>.3D</span></div>
      <div class="badge">ระบบยืนยันตัวตนทางอีเมล (Email Verification)</div>
    </div>
    <p style="font-size: 15px; font-weight: 700; margin-bottom: 8px;">สวัสดีคุณ {username},</p>
    <p style="font-size: 13px; color: #57534E; line-height: 1.6; margin: 0;">
      ขอบคุณที่ให้ความสนใจสมัครสมาชิก <strong>PrintVerse 3D</strong> ตลาดกลางโมเดลสำหรับการพิมพ์ 3 มิติ 
      กรุณานำรหัส OTP 6 หลักด้านล่างนี้ไปกรอกในหน้ายืนยันการสมัครสมาชิก:
    </p>
    
    <div class="otp-box">
      <div style="font-size: 11px; font-weight: 700; color: #78716C; text-transform: uppercase; margin-bottom: 6px;">รหัสยืนยัน OTP (อายุ 10 นาที)</div>
      <div class="otp-code">{otp_code}</div>
    </div>

    <p style="font-size: 12px; color: #78716C; line-height: 1.6;">
      ⚠️ <strong>ข้อควรระวัง:</strong> รหัส OTP นี้มีอายุการใช้งาน 10 นาที และใช้ได้เพียงครั้งเดียวเท่านั้น ห้ามเปิดเผยรหัสนี้แก่ผู้อื่นเพื่อความปลอดภัยของบัญชีคุณ
    </p>

    <div class="footer">
      อีเมลนี้ถูกส่งอัตโนมัติจากระบบ PrintVerse 3D Marketplace<br>
      หากคุณไม่ได้เป็นผู้ร้องขอสมัครสมาชิก กรุณาเพิกเฉยต่ออีเมลฉบับนี้
    </div>
  </div>
</body>
</html>"""

    is_sent = False
    error_msg = None
    if mail_username and mail_password:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{sender_name} <{sender_email}>"
            msg["To"] = recipient_email

            text_part = MIMEText(f"รหัส OTP สำหรับยืนยันการสมัครสมาชิก PrintVerse 3D ของคุณคือ: {otp_code} (หมดอายุใน 10 นาที)", "plain", "utf-8")
            html_part = MIMEText(html_content, "html", "utf-8")
            msg.attach(text_part)
            msg.attach(html_part)

            server = smtplib.SMTP(mail_server, mail_port, timeout=10)
            if mail_use_tls:
                server.starttls()
            server.login(mail_username, mail_password)
            server.sendmail(sender_email, [recipient_email], msg.as_string())
            server.quit()
            is_sent = True
        except Exception as e:
            error_msg = str(e)
            print(f"[MAIL ERROR] Failed to send email to {recipient_email}: {error_msg}")

    try:
        print("\n=======================================================")
        print(f"[OTP VERIFICATION] Sent to: {recipient_email}")
        print(f"[OTP CODE]: {otp_code}")
        print("[EXPIRES IN]: 10 minutes")
        print(f"STATUS: {'DELIVERED VIA SMTP' if is_sent else 'LOCAL DEV MODE (Check log or screen)'}")
        print("=======================================================\n")
    except Exception:
        pass

    return is_sent, error_msg


def send_password_reset_otp_email(recipient_email, otp_code, username="ผู้ใช้งาน"):
    """
    ฟังก์ชันส่งรหัส OTP 6 หลักสำหรับรีเซ็ตรหัสผ่านไปยังอีเมลของผู้ใช้จริง
    """
    cfg = get_smtp_config()
    mail_server = cfg["MAIL_SERVER"]
    mail_port = int(cfg["MAIL_PORT"])
    mail_username = cfg["MAIL_USERNAME"]
    mail_password = cfg["MAIL_PASSWORD"]
    mail_use_tls = bool(cfg["MAIL_USE_TLS"])
    sender_name = cfg["SENDER_NAME"]
    sender_email = mail_username or "official@printverse.com"

    subject = f"[PrintVerse 3D] รหัส OTP สำหรับรีเซ็ตรหัสผ่านของคุณ: {otp_code}"
    
    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #FAF8F5; margin: 0; padding: 20px; color: #1C1917; }}
    .container {{ max-width: 520px; margin: 0 auto; background: #ffffff; border: 1px solid #E7E2D9; border-radius: 24px; padding: 32px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }}
    .header {{ text-align: center; border-bottom: 1px solid #E7E2D9; padding-bottom: 20px; margin-bottom: 24px; }}
    .brand {{ font-size: 22px; font-weight: 800; color: #1C1917; letter-spacing: -0.5px; }}
    .brand span {{ color: #FF6B4A; }}
    .badge {{ display: inline-block; padding: 4px 12px; border-radius: 999px; background: #FAF8F5; border: 1px solid #E7E2D9; font-size: 11px; font-weight: 600; color: #78716C; margin-top: 8px; }}
    .otp-box {{ background: #FAF8F5; border: 2px dashed #FF6B4A; border-radius: 16px; padding: 20px; text-align: center; margin: 28px 0; }}
    .otp-code {{ font-size: 36px; font-weight: 900; letter-spacing: 8px; color: #FF6B4A; font-family: monospace; }}
    .footer {{ text-align: center; font-size: 11px; color: #A8A29E; border-top: 1px solid #E7E2D9; padding-top: 20px; margin-top: 28px; line-height: 1.6; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="brand">PrintVerse<span>.3D</span></div>
      <div class="badge">ระบบรีเซ็ตรหัสผ่าน (Password Reset OTP)</div>
    </div>
    <p style="font-size: 15px; font-weight: 700; margin-bottom: 8px;">สวัสดีคุณ {username},</p>
    <p style="font-size: 13px; color: #57534E; line-height: 1.6; margin: 0;">
      ระบบได้รับคำขอตั้งรหัสผ่านใหม่สำหรับบัญชีของคุณบน <strong>PrintVerse 3D</strong> 
      กรุณานำรหัส OTP 6 หลักด้านล่างนี้ไปกรอกเพื่อยืนยันการตั้งรหัสผ่านใหม่:
    </p>
    
    <div class="otp-box">
      <div style="font-size: 11px; font-weight: 700; color: #78716C; text-transform: uppercase; margin-bottom: 6px;">รหัสยืนยัน OTP (อายุ 10 นาที)</div>
      <div class="otp-code">{otp_code}</div>
    </div>

    <p style="font-size: 12px; color: #78716C; line-height: 1.6;">
      ⚠️ <strong>ข้อควรระวัง:</strong> รหัส OTP นี้มีอายุการใช้งาน 10 นาที และใช้ได้เพียงครั้งเดียวเท่านั้น หากคุณไม่ได้เป็นผู้ร้องขอเปลี่ยนรหัสผ่าน โปรดเพิกเฉยต่ออีเมลฉบับนี้ รหัสผ่านเดิมของคุณจะยังคงปลอดภัย
    </p>

    <div class="footer">
      อีเมลนี้ถูกส่งอัตโนมัติจากระบบ PrintVerse 3D Marketplace<br>
      หากคุณไม่ได้เป็นผู้ร้องขอ กรุณาตรวจสอบความปลอดภัยของบัญชีคุณ
    </div>
  </div>
</body>
</html>"""

    is_sent = False
    error_msg = None
    if mail_username and mail_password:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{sender_name} <{sender_email}>"
            msg["To"] = recipient_email

            text_part = MIMEText(f"รหัส OTP สำหรับรีเซ็ตรหัสผ่าน PrintVerse 3D ของคุณคือ: {otp_code} (หมดอายุใน 10 นาที)", "plain", "utf-8")
            html_part = MIMEText(html_content, "html", "utf-8")
            msg.attach(text_part)
            msg.attach(html_part)

            server = smtplib.SMTP(mail_server, mail_port, timeout=10)
            if mail_use_tls:
                server.starttls()
            server.login(mail_username, mail_password)
            server.sendmail(sender_email, [recipient_email], msg.as_string())
            server.quit()
            is_sent = True
        except Exception as e:
            error_msg = str(e)
            print(f"[MAIL ERROR] Failed to send password reset OTP to {recipient_email}: {error_msg}")

    try:
        print("\n=======================================================")
        print(f"[PASSWORD RESET OTP] Sent to: {recipient_email}")
        print(f"[OTP CODE]: {otp_code}")
        print("[EXPIRES IN]: 10 minutes")
        print(f"STATUS: {'DELIVERED VIA SMTP' if is_sent else 'LOCAL DEV MODE'}")
        print("=======================================================\n")
    except Exception:
        pass

    return is_sent, error_msg


def init_admin_user():
    """
    ฟังก์ชันสร้างหรืออัปเดตบัญชีผู้ดูแลระบบหลัก (Admin) อัตโนมัติเมื่อเริ่มระบบ
    - อีเมลหลัก: official@printverse.com
    - ชื่อผู้ใช้: PrintVerse
    - สิทธิ์: is_admin = True
    """
    admin_user = User.query.filter(
        (User.email == "official@printverse.com") | (User.username == "PrintVerse")
    ).first()

    if not admin_user:
        # หากยังไม่มีบัญชีแอดมิน ให้สร้างขึ้นใหม่ทันที
        admin_user = User(
            username="PrintVerse",
            email="official@printverse.com",
            phone_number="020000000",
            maker_badge="Administrator",
            wallet_balance=10000.0,
            bio="ผู้ดูแลระบบ PrintVerse Studio อย่างเป็นทางการ",
            is_admin=True
        )
        admin_user.set_password("pl170313")
        db.session.add(admin_user)
        db.session.commit()
    else:
        # อัปเดตสิทธิ์ Admin, Email, Username และรหัสผ่านทุกครั้งที่เริ่มระบบ
        admin_user.username = "PrintVerse"
        admin_user.email = "official@printverse.com"
        admin_user.is_admin = True
        admin_user.set_password("pl170313")
        admin_user.maker_badge = "Administrator"
        db.session.commit()
    return admin_user

def seed_initial_models():
    """
    ฟังก์ชันเตรียมข้อมูลตั้งต้นของโมเดล 3D (Initial Data Seeding)
    - สร้างข้อมูลสินค้าจำลอง 16 รายการ ครอบคลุมหลายหมวดหมู่ (Art, Home, Gadgets, Tools, ฯลฯ)
    - บันทึกพารามิเตอร์การพิมพ์ 3 มิติ (Layer height, Infill %, Support) และชนิดเส้นพลาสติก
    - เชื่อมโยงรูปภาพตัวอย่างจากโฟลเดอร์ photo/<Title>.jpg ไปยังโมเดลแต่ละรายการอัตโนมัติ
    """
    store_admin = init_admin_user()

    sample_models = [
        {
            "title": "Mechanical Articulated Dragon",
            "description": "มังกรข้อต่อขยับได้รอบทิศทาง พิมพ์ชิ้นเดียวแบบ Print-in-Place ไม่ต้องประกอบและไม่ต้องใช้ Support",
            "category": "Art & Figures",
            "price": 120.0,
            "is_free": False,
            "primary_format": "3MF",
            "supported_formats": "3MF, STL",
            "file_size_mb": 18.4,
            "download_count": 0,
            "layer_height": "0.16 mm",
            "infill": 15,
            "supports": False,
            "material": "PLA Silk / Dual Color",
            "filament_g": 140.0
        },
        {
            "title": "Minimalist Geometric Planter",
            "description": "กระถางต้นไม้เรขาคณิตสไตล์มินิมอล พร้อมถาดระบายน้ำซ่อนในตัว ดีไซน์เรียบหรูสำหรับวางบนโต๊ะทำงาน",
            "category": "Home & Living",
            "price": 0.0,
            "is_free": True,
            "primary_format": "STL",
            "supported_formats": "STL, OBJ",
            "file_size_mb": 4.2,
            "download_count": 0,
            "layer_height": "0.20 mm",
            "infill": 20,
            "supports": False,
            "material": "PLA Matte White",
            "filament_g": 65.0
        },
        {
            "title": "Ergonomic Vertical Mouse Grip",
            "description": "กริปจับเมาส์แนวตั้งตามหลักการยศาสตร์ ช่วยลดอาการเมื่อยล้าข้อมือ มีช่องรองรับเซนเซอร์แม่นยำสูง",
            "category": "Gadgets & Tech",
            "price": 85.0,
            "is_free": False,
            "primary_format": "STEP",
            "supported_formats": "STEP, STL",
            "file_size_mb": 12.1,
            "download_count": 0,
            "layer_height": "0.12 mm",
            "infill": 30,
            "supports": True,
            "material": "PETG / Carbon Fiber",
            "filament_g": 52.0
        },
        {
            "title": "Modular Hexagon Wall Storage",
            "description": "ระบบชั้นวางหกเหลี่ยมติดผนัง ต่อขยายได้ไม่จำกัด จัดเก็บของใช้และอุปกรณ์ตกแต่งห้องได้อย่างเป็นระเบียบ",
            "category": "Home & Living",
            "price": 150.0,
            "is_free": False,
            "primary_format": "3MF",
            "supported_formats": "3MF, STL",
            "file_size_mb": 15.6,
            "download_count": 0,
            "layer_height": "0.20 mm",
            "infill": 20,
            "supports": False,
            "material": "PLA Wood / Matte",
            "filament_g": 180.0
        },
        {
            "title": "Universal Desktop Headphone Stand",
            "description": "แท่นวางหูฟังตั้งโต๊ะเส้นสายมินิมอล ฐานกว้างมั่นคงพร้อมร่องวางสายไฟด้านหลัง",
            "category": "Gadgets & Tech",
            "price": 0.0,
            "is_free": True,
            "primary_format": "STL",
            "supported_formats": "STL, OBJ",
            "file_size_mb": 8.5,
            "download_count": 0,
            "layer_height": "0.24 mm",
            "infill": 15,
            "supports": False,
            "material": "PLA Black / Gray",
            "filament_g": 95.0
        },
        {
            "title": "Precision Caliper Wall Mount",
            "description": "แท่นแขวนเวอร์เนียร์คาลิปเปอร์ติดผนังแบบสวมเร็ว ช่วยถนอมเครื่องมือวัดให้พร้อมใช้งานเสมอ",
            "category": "Tools & Workshop",
            "price": 0.0,
            "is_free": True,
            "primary_format": "STL",
            "supported_formats": "STL, STEP",
            "file_size_mb": 2.8,
            "download_count": 0,
            "layer_height": "0.20 mm",
            "infill": 30,
            "supports": False,
            "material": "PETG / ABS",
            "filament_g": 28.0
        },
        {
            "title": "Cable Management Spine & Clip Set",
            "description": "รางกระดูกงูจัดระเบียบสายไฟใต้โต๊ะแบบแยกข้อต่อ ปรับเปลี่ยนความยาวและองศาได้อิสระ",
            "category": "Workspace & Desk",
            "price": 45.0,
            "is_free": False,
            "primary_format": "STL",
            "supported_formats": "STL, 3MF",
            "file_size_mb": 6.7,
            "download_count": 0,
            "layer_height": "0.20 mm",
            "infill": 25,
            "supports": False,
            "material": "PETG / PLA",
            "filament_g": 75.0
        },
        {
            "title": "Parametric Raspberry Pi 5 Active Case",
            "description": "เคสระบายความร้อน Raspberry Pi 5 พร้อมสล็อตติดตั้งพัดลม 40mm และฮีตซิงก์ทองแดง",
            "category": "Electronics",
            "price": 95.0,
            "is_free": False,
            "primary_format": "STEP",
            "supported_formats": "STEP, STL, 3MF",
            "file_size_mb": 9.4,
            "download_count": 0,
            "layer_height": "0.16 mm",
            "infill": 25,
            "supports": True,
            "material": "ABS / ASA",
            "filament_g": 48.0
        },
        {
            "title": "Spiral Voronoi Ambient Table Lamp",
            "description": "โคมไฟตั้งโต๊ะลวดลายเกลียว Voronoi กระจายแสงนุ่มนวล พร้อมฐานหลอดไฟเกลียว E27 มาตรฐาน",
            "category": "Home & Lighting",
            "price": 110.0,
            "is_free": False,
            "primary_format": "3MF",
            "supported_formats": "3MF, STL",
            "file_size_mb": 22.3,
            "download_count": 0,
            "layer_height": "0.16 mm",
            "infill": 10,
            "supports": False,
            "material": "PETG Translucent",
            "filament_g": 165.0
        },
        {
            "title": "Foldable Travel Phone Stand",
            "description": "แท่นวางสมาร์ตโฟนและแท็บเล็ตแบบพับเก็บได้ พกพาสะดวก บางเพียง 4 มม. เมื่อพับปิด",
            "category": "Gadgets & Tech",
            "price": 0.0,
            "is_free": True,
            "primary_format": "STL",
            "supported_formats": "STL, OBJ",
            "file_size_mb": 3.1,
            "download_count": 0,
            "layer_height": "0.20 mm",
            "infill": 25,
            "supports": False,
            "material": "PLA / PETG",
            "filament_g": 32.0
        },
        {
            "title": "Mechanical Iris Aperture Box",
            "description": "กล่องเก็บของกลไกชัตเตอร์กล้อง หมุนเปิด-ปิดได้อย่างราบรื่น พิมพ์โดยไม่ต้องใช้สกรู",
            "category": "Mechanical & Toys",
            "price": 75.0,
            "is_free": False,
            "primary_format": "STL",
            "supported_formats": "STL, 3MF",
            "file_size_mb": 11.8,
            "download_count": 0,
            "layer_height": "0.16 mm",
            "infill": 20,
            "supports": False,
            "material": "PLA Matte Dual",
            "filament_g": 90.0
        },
        {
            "title": "Threaded Waterproof EDC Capsule",
            "description": "แคปซูลเก็บของพกพาระบบเกลียวความแม่นยำสูง พร้อมร่องใส่ซีลยาง O-Ring กันน้ำ",
            "category": "Everyday Carry",
            "price": 35.0,
            "is_free": False,
            "primary_format": "STEP",
            "supported_formats": "STEP, STL",
            "file_size_mb": 5.4,
            "download_count": 0,
            "layer_height": "0.12 mm",
            "infill": 40,
            "supports": False,
            "material": "PETG / Nylon",
            "filament_g": 24.0
        },
        {
            "title": "Gridfinity Modular Organizer System",
            "description": "ระบบถาดและกล่องจัดระเบียบเครื่องมือมาตรฐาน Gridfinity วางซ้อนและล็อกตำแหน่งแม่เหล็กได้",
            "category": "Tools & Workshop",
            "price": 0.0,
            "is_free": True,
            "primary_format": "STEP",
            "supported_formats": "STEP, STL, 3MF",
            "file_size_mb": 8.0,
            "download_count": 0,
            "layer_height": "0.24 mm",
            "infill": 15,
            "supports": False,
            "material": "PLA Standard",
            "filament_g": 85.0
        },
        {
            "title": "Low-Poly Geometric Fox Sculpture",
            "description": "ประติมากรรมจิ้งจอกทรงเรขาคณิตสไตล์โพลีต่ำ สำหรับประดับตกแต่งบ้านและโต๊ะทำงาน",
            "category": "Art & Figures",
            "price": 0.0,
            "is_free": True,
            "primary_format": "STL",
            "supported_formats": "STL, OBJ",
            "file_size_mb": 2.6,
            "download_count": 0,
            "layer_height": "0.20 mm",
            "infill": 10,
            "supports": False,
            "material": "PLA Copper / Bronze",
            "filament_g": 45.0
        },
        {
            "title": "Dual-Bearing Filament Spool Holder",
            "description": "แกนหมุนม้วนเส้นพลาสติกลูกปืนคู่ หมุนลื่นไร้แรงเสียดทาน ยืดอายุการใช้งานมอเตอร์รีดเส้น",
            "category": "3D Print Upgrades",
            "price": 55.0,
            "is_free": False,
            "primary_format": "STL",
            "supported_formats": "STL, STEP",
            "file_size_mb": 7.2,
            "download_count": 0,
            "layer_height": "0.20 mm",
            "infill": 30,
            "supports": False,
            "material": "PETG Tough",
            "filament_g": 62.0
        },
        {
            "title": "Architectural Column Bookends Pair",
            "description": "ที่กั้นหนังสือคู่ทรงเสากรีกคลาสสิก ดีไซน์เรียบเท่ ช่วยจัดเรียงหนังสือให้ตั้งตรงสวยงาม",
            "category": "Home & Living",
            "price": 60.0,
            "is_free": False,
            "primary_format": "STL",
            "supported_formats": "STL, 3MF",
            "file_size_mb": 14.5,
            "download_count": 0,
            "layer_height": "0.16 mm",
            "infill": 20,
            "supports": False,
            "material": "PLA Marble",
            "filament_g": 130.0
        }
    ]

    photo_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), "photo")
    for item in sample_models:
        title = item["title"]
        photo_filename = f"{title}.jpg"
        thumb_url = f"/photo/{photo_filename}" if os.path.exists(os.path.join(photo_dir, photo_filename)) else None

        existing = Model3D.query.filter_by(title=title).first()
        if existing:
            if not existing.thumbnail_url and thumb_url:
                existing.thumbnail_url = thumb_url
                db.session.commit()
            continue

        model = Model3D(
            title=item["title"],
            description=item["description"],
            category=item["category"],
            price=item["price"],
            is_free=item["is_free"],
            primary_format=item["primary_format"],
            supported_formats=item["supported_formats"],
            file_size_mb=item["file_size_mb"],
            download_count=item["download_count"],
            user_id=store_admin.id,
            thumbnail_url=thumb_url,
            status="อนุมัติแล้ว",
            is_approved=True
        )
        db.session.add(model)
        db.session.flush()

        setting = PrintSetting(
            model_id=model.id,
            layer_height=item["layer_height"],
            infill_percentage=item["infill"],
            supports_required=item["supports"]
        )
        db.session.add(setting)

        filament = FilamentRequirement(
            model_id=model.id,
            material_type=item["material"],
            filament_weight_grams=item["filament_g"]
        )
        db.session.add(filament)

    db.session.commit()


# --------------------------------------------------------------------------------
# ส่วนที่ 3: ฟังก์ชันหลักสร้างและกำหนดค่าแอปพลิเคชัน Flask (Application Factory: create_app)
# --------------------------------------------------------------------------------

def create_app():
    """
    ฟังก์ชัน Application Factory สำหรับสร้างและตั้งค่าอินสแตนซ์ของ Flask
    - กำหนดค่า Secret Key และโฟลเดอร์สำหรับจัดเก็บฐานข้อมูล SQLite
    - สร้างโฟลเดอร์สำหรับอัปโหลดภาพสลิป, ภาพตัวอย่างโมเดล, และไฟล์โมเดล 3D
    - ผูกระบบตรวจสอบสิทธิ์ Flask-Login และตัวแปรส่วนกลาง (Context Processor)
    - เริ่มต้นสร้างตารางฐานข้อมูลและเตรียมข้อมูลตัวอย่างเมื่อรันครั้งแรก
    """
    app = Flask(__name__)
    
    # Secret Key สำหรับเข้ารหัส Session, คุกกี้ และ Flash Messages
    app.config["SECRET_KEY"] = "3d-maker-secret-token-market-2026-key"

    # กำหนดเส้นทางฐานข้อมูล SQLite ไว้ในโฟลเดอร์ instance/marketplace.db
    base_dir = os.path.abspath(os.path.dirname(__file__))
    instance_dir = os.path.join(base_dir, "instance")
    os.makedirs(instance_dir, exist_ok=True)
    
    # 1. โฟลเดอร์อัปโหลดภาพสลิปหลักฐานการโอนเงิน (static/uploads/slips)
    upload_folder = os.path.join(base_dir, "static", "uploads", "slips")
    os.makedirs(upload_folder, exist_ok=True)
    app.config["UPLOAD_FOLDER"] = upload_folder

    # 2. โฟลเดอร์อัปโหลดรูปภาพตัวอย่างโมเดล 3D (static/uploads/thumbnails)
    model_upload_folder = os.path.join(base_dir, "static", "uploads", "thumbnails")
    os.makedirs(model_upload_folder, exist_ok=True)
    app.config["MODEL_UPLOAD_FOLDER"] = model_upload_folder

    # 3. โฟลเดอร์อัปโหลดไฟล์โมเดล 3D (.stl, .3mf, .step, ฯลฯ) (static/uploads/files)
    files_upload_folder = os.path.join(base_dir, "static", "uploads", "files")
    os.makedirs(files_upload_folder, exist_ok=True)
    app.config["FILES_UPLOAD_FOLDER"] = files_upload_folder

    # 4. โฟลเดอร์อัปโหลดรูปภาพโปรไฟล์ผู้ใช้ (static/uploads/avatars)
    avatars_upload_folder = os.path.join(base_dir, "static", "uploads", "avatars")
    os.makedirs(avatars_upload_folder, exist_ok=True)
    app.config["AVATARS_UPLOAD_FOLDER"] = avatars_upload_folder

    # กำหนดขนาดไฟล์อัปโหลดสูงสุด 32 MB
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024
    
    # ตั้งค่าการเชื่อมต่อฐานข้อมูล SQLAlchemy กับ SQLite
    db_path = os.path.join(instance_dir, "marketplace.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{db_path}"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # ผูก SQLAlchemy เข้ากับ Flask Application
    db.init_app(app)

    # เส้นทางสำหรับเสิร์ฟไฟล์รูปภาพสินค้าจากโฟลเดอร์ photo โดยตรง
    @app.route("/photo/<path:filename>")
    def serve_photo(filename):
        """เสิร์ฟไฟล์รูปภาพโมเดล 3D จากโฟลเดอร์ photo"""
        photo_dir = os.path.join(base_dir, "photo")
        return send_from_directory(photo_dir, filename)

    # เส้นทางสำหรับเปลี่ยนภาษาระบบ (ไทย / อังกฤษ)
    @app.route("/set_language/<lang>")
    def set_language(lang):
        """สลับภาษาระบบระหว่าง ไทย (th) และ อังกฤษ (en)"""
        if lang in ["th", "en"]:
            session["lang"] = lang
        next_url = request.args.get("next") or request.referrer or url_for("index")
        return redirect(next_url)

    # ----------------------------------------------------------------------------
    # การตั้งค่าระบบ Authentication ด้วย Flask-Login
    # ----------------------------------------------------------------------------
    login_manager = LoginManager()
    login_manager.login_view = "login"         # หน้าที่ให้ redirect ไปหากผู้ใช้ยังไม่ได้ล็อกอิน
    login_manager.login_message = None         # ไม่แสดงข้อความ default เมื่อถูก redirect
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        """โหลดข้อมูลผู้ใช้จากฐานข้อมูลตาม ID ที่เก็บไว้ใน Session"""
        return db.session.get(User, int(user_id))

    # ----------------------------------------------------------------------------
    # Context Processor: ส่งตัวแปรส่วนกลางไปยังทุกหน้า Template อัตโนมัติ
    # ----------------------------------------------------------------------------
    @app.context_processor
    def inject_globals():
        """
        ส่งข้อมูลส่วนกลางไปยัง Jinja2 Templates ทุกหน้า:
        - cart_count: จำนวนรายการสินค้าในตะกร้าของผู้ใช้ปัจจุบัน
        - pending_models_count: จำนวนโมเดล 3D ที่รอแอดมินอนุมัติ
        - pending_topups_count: จำนวนสลิปเติมเงินที่รอแอดมินตรวจสอบ
        - pending_withdrawals_count: จำนวนคำขอถอนเงินที่รอแอดมินดำเนินการ
        - total_pending_count: รวมยอดรายการที่แอดมินต้องดำเนินการ
        - liked_model_ids: เซ็ตของ model_id ที่ผู้ใช้คนนี้กดถูกใจไว้แล้ว
        - current_lang: ภาษาปัจจุบัน ('th' หรือ 'en')
        - t: ฟังก์ชันแปลภาษาตาม Key
        """
        cart = session.get('cart', [])
        pending_models_count = 0
        pending_topups_count = 0
        pending_withdrawals_count = 0
        liked_model_ids = set()
        
        if current_user.is_authenticated:
            liked_model_ids = {l.model_id for l in current_user.likes}
            if current_user.is_admin:
                pending_models_count = Model3D.query.filter(
                    (Model3D.status == 'รอการตรวจสอบ') | (Model3D.is_approved == False)
                ).count()
                pending_topups_count = TopupTransaction.query.filter_by(
                    status='รอการตรวจสอบ'
                ).count()
                pending_withdrawals_count = WithdrawalTransaction.query.filter_by(
                    status='รอการตรวจสอบ'
                ).count()
                
        total_pending_count = pending_models_count + pending_topups_count + pending_withdrawals_count
        lang = session.get('lang', 'th')
        return {
            'cart_count': len(cart),
            'pending_models_count': pending_models_count,
            'pending_topups_count': pending_topups_count,
            'pending_withdrawals_count': pending_withdrawals_count,
            'total_pending_count': total_pending_count,
            'liked_model_ids': liked_model_ids,
            'current_lang': lang,
            't': lambda key, **kw: get_translation(session.get('lang', 'th'), key, **kw)
        }

    # ตรวจสอบโครงสร้างตารางและสร้างข้อมูลเริ่มต้นภายใน Application Context
    with app.app_context():
        ensure_database_schema(db_path)
        db.create_all()
        seed_initial_models()

    # ============================================================================
    # ส่วนที่ 4: เส้นทางสำหรับผู้ใช้ทั่วไปและตลาดกลางโมเดล 3D (Marketplace & Product Details)
    # ============================================================================

    @app.route("/")
    def index():
        """
        หน้าหลักตลาดกลางโมเดล 3 มิติ (Marketplace Catalog)
        - แสดงเฉพาะโมเดลที่ผ่านการอนุมัติแล้ว (is_approved=True หรือ status='อนุมัติแล้ว')
        - รองรับการค้นหา (Query Search) ตามชื่อ, คำอธิบาย, หมวดหมู่, และฟอร์แมตไฟล์
        - รองรับการกรองตามนามสกุลไฟล์ (.STL, .3MF, .STEP, .OBJ)
        - รองรับการกรองตามหมวดหมู่สินค้า (Category)
        - ตรวจสอบรายการสินค้าที่ผู้ใช้ปัจจุบันเป็นเจ้าของแล้ว และสินค้าที่อยู่ในตะกร้า
        """
        query_param = request.args.get("q", "").strip()
        format_param = request.args.get("format", "").strip()
        category_param = request.args.get("category", "").strip()

        # สร้าง Query โดยคัดกรองเฉพาะสินค้าที่อนุมัติแล้วเท่านั้น
        model_query = Model3D.query.filter((Model3D.is_approved == True) | (Model3D.status == 'อนุมัติแล้ว'))
        
        # กรองตามคำค้นหา (Case-insensitive)
        if query_param:
            model_query = model_query.filter(
                (Model3D.title.ilike(f"%{query_param}%")) |
                (Model3D.description.ilike(f"%{query_param}%")) |
                (Model3D.category.ilike(f"%{query_param}%")) |
                (Model3D.primary_format.ilike(f"%{query_param}%"))
            )
        # กรองตามฟอร์แมตไฟล์
        if format_param:
            model_query = model_query.filter(Model3D.primary_format == format_param)
        # กรองตามหมวดหมู่สินค้า
        if category_param:
            model_query = model_query.filter(Model3D.category == category_param)

        # เรียงลำดับจากโมเดลที่อัปโหลดล่าสุดไปเก่าสุด
        models = model_query.order_by(Model3D.created_at.desc()).all()

        # รวบรวม ID ของโมเดลที่ผู้ใช้ปัจจุบันเคยซื้อหรือดาวน์โหลดแล้ว
        purchased_ids = set()
        if current_user.is_authenticated:
            purchased_ids = {p.model_id for p in current_user.downloads}

        # รวบรวม ID ของโมเดลที่อยู่ในตะกร้าสินค้า
        cart_ids = set(session.get("cart", []))

        return render_template(
            "index.html",
            models=models,
            search_query=query_param,
            selected_format=format_param,
            selected_category=category_param,
            purchased_ids=purchased_ids,
            cart_ids=cart_ids
        )

    # ----------------------------------------------------------------------------
    # หน้ารายละเอียดโมเดล 3D (Dedicated Product Detail Page)
    # ----------------------------------------------------------------------------
    @app.route("/model/<int:model_id>")
    def model_detail(model_id):
        """
        หน้ารายละเอียดสินค้าโมเดล 3D แบบเต็มรูปแบบ
        - แสดงรูปภาพขนาดใหญ่เต็มรูป (object-contain) ไม่ถูกตัดขอบ
        - แสดงชื่อสินค้า, ราคา, คำอธิบาย และพารามิเตอร์การพิมพ์ 3D ชัดเจน
        - ตรวจสอบสิทธิ์การเข้าชม: สินค้าที่รออนุมัติจะดูได้เฉพาะเจ้าของผลงานและแอดมิน
        - แสดงปุ่มสั่งซื้อด่วน (Buy Now), ปุ่มใส่ตะกร้า (Add to Cart), และปุ่มย้อนกลับ
        - แนะนำโมเดล 3D ที่เกี่ยวข้องในหมวดหมู่เดียวกัน
        """
        model = Model3D.query.get_or_404(model_id)

        # ตรวจสอบสถานะการอนุมัติ: ผู้ใช้ทั่วไปต้องเห็นเฉพาะสินค้าที่อนุมัติแล้วเท่านั้น
        if not model.is_approved and model.status != "อนุมัติแล้ว":
            if not (current_user.is_authenticated and (current_user.is_admin or model.user_id == current_user.id)):
                flash("โมเดลนี้อยู่ระหว่างรอแอดมินตรวจสอบความถูกต้อง", "warning")
                return redirect(url_for("index"))

        # ตรวจสอบว่าผู้ใช้ปัจจุบันเป็นเจ้าของโมเดลนี้แล้วหรือไม่
        is_purchased = False
        if current_user.is_authenticated:
            is_purchased = ModelPurchase.query.filter_by(user_id=current_user.id, model_id=model.id).first() is not None

        # ตรวจสอบว่าโมเดลนี้อยู่ในตะกร้าสินค้าแล้วหรือไม่
        in_cart = model.id in session.get("cart", [])

        # ดึงรายการโมเดลแนะนำในหมวดหมู่เดียวกัน (สุ่ม/ดึงสูงสุด 4 รายการ)
        related_models = Model3D.query.filter(
            Model3D.category == model.category,
            Model3D.id != model.id,
            (Model3D.is_approved == True) | (Model3D.status == 'อนุมัติแล้ว')
        ).limit(4).all()

        return render_template(
            "model_detail.html",
            model=model,
            is_purchased=is_purchased,
            in_cart=in_cart,
            related_models=related_models
        )

    # ----------------------------------------------------------------------------
    # ระบบดาวน์โหลดไฟล์โมเดล 3D จริง (.STL, .3MF, .OBJ, .STEP, .ZIP)
    # ----------------------------------------------------------------------------
    @app.route("/model/<int:model_id>/download")
    @login_required
    def download_model_file(model_id):
        """
        ระบบดาวน์โหลดไฟล์โมเดล 3D จริง (.STL, .3MF, .OBJ, .STEP, .ZIP)
        - ผู้ใช้งานดาวน์โหลดได้ทันทีหาก:
          1. เป็นเจ้าของโมเดล (ผู้โพสต์ขาย)
          2. เป็นแอดมินระบบ
          3. โมเดลนั้นเป็นของฟรี (Free Download ฿0.00)
          4. ผู้ใช้งานเคยสั่งซื้อโมเดลนี้แล้ว (ModelPurchase)
        - หากเป็นโมเดลฟรีและยังไม่เคยอยู่ในคลัง ระบบจะเพิ่มลงคลังให้โดยอัตโนมัติ
        - เพิ่มยอดจำนวนครั้งการดาวน์โหลด (download_count)
        - ส่งไฟล์โมเดลจริงที่ผู้ขายอัปโหลดไว้ในโฟลเดอร์ static/uploads/files/
        - หากโมเดลตัวอย่างระบบยังไม่มีไฟล์แนบ ระบบจะสร้างแพ็กเกจไฟล์ 3D (.STL พร้อม Print Specs & License) ที่สมบูรณ์แบบพร้อมพิมพ์ส่งให้ดาวน์โหลดทันที
        """
        model = Model3D.query.get_or_404(model_id)

        # ตรวจสอบสิทธิ์การดาวน์โหลด
        is_owner = (model.user_id == current_user.id)
        is_admin = current_user.is_admin
        is_free = (model.is_free or model.price <= 0)
        has_purchased = ModelPurchase.query.filter_by(user_id=current_user.id, model_id=model.id).first() is not None

        if not (is_owner or is_admin or is_free or has_purchased):
            flash("คุณต้องสั่งซื้อโมเดลนี้ก่อนจึงจะสามารถดาวน์โหลดไฟล์ได้", "warning")
            return redirect(url_for("model_detail", model_id=model.id))

        # หากเป็นโมเดลฟรีและยังไม่มีบันทึกในคลัง ให้บันทึกการดาวน์โหลดเข้า ModelPurchase
        if is_free and not has_purchased and not is_owner:
            try:
                free_purchase = ModelPurchase(
                    user_id=current_user.id,
                    model_id=model.id,
                    price_paid=0.0,
                    seller_id=model.user_id,
                    seller_income=0.0
                )
                db.session.add(free_purchase)
            except Exception:
                db.session.rollback()

        # เพิ่มสถิติจำนวนการดาวน์โหลดจริง (เฉพาะเมื่อผู้ดาวน์โหลดไม่ใช่เจ้าของโมเดล)
        if not is_owner:
            model.download_count = (model.download_count or 0) + 1
            db.session.commit()

        # ชื่อไฟล์ทำความสะอาดสำหรับบันทึกลงเครื่องผู้ใช้
        ext = (model.primary_format or "stl").lower()
        clean_title = re.sub(r'[^\w\s-]', '', model.title).strip().replace(' ', '_')
        if not clean_title:
            clean_title = f"model_{model.id}"

        # 1. ตรวจสอบไฟล์จริงที่ผู้ขายอัปโหลดไว้ในโฟลเดอร์ static/uploads/files
        if model.file_path:
            file_disk_path = os.path.join(app.config["FILES_UPLOAD_FOLDER"], model.file_path)
            if os.path.exists(file_disk_path):
                actual_ext = model.file_path.rsplit(".", 1)[-1].lower() if "." in model.file_path else ext
                client_download_name = f"{clean_title}.{actual_ext}"
                return send_from_directory(
                    app.config["FILES_UPLOAD_FOLDER"],
                    model.file_path,
                    as_attachment=True,
                    download_name=client_download_name
                )

        # 2. หากยังไม่มีไฟล์แนบไว้ (เช่น โมเดลตัวอย่างเริ่มต้นของระบบ)
        # สร้างแพ็กเกจไฟล์ 3D (.STL พร้อม Print Specs & License) ในหน่วยความจำแล้วส่งให้ดาวน์โหลด
        mem_buffer = io.BytesIO()
        with zipfile.ZipFile(mem_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            # สร้างไฟล์ STL 3D แบบ Calibration Cube 20x20x20mm
            stl_content = f"""solid {clean_title}
  facet normal 0.000000 0.000000 -1.000000
    outer loop
      vertex 0.000000 0.000000 0.000000
      vertex 0.000000 20.000000 0.000000
      vertex 20.000000 20.000000 0.000000
    endloop
  endfacet
  facet normal 0.000000 0.000000 -1.000000
    outer loop
      vertex 20.000000 20.000000 0.000000
      vertex 20.000000 0.000000 0.000000
      vertex 0.000000 0.000000 0.000000
    endloop
  endfacet
  facet normal 0.000000 0.000000 1.000000
    outer loop
      vertex 0.000000 0.000000 20.000000
      vertex 20.000000 0.000000 20.000000
      vertex 20.000000 20.000000 20.000000
    endloop
  endfacet
  facet normal 0.000000 0.000000 1.000000
    outer loop
      vertex 20.000000 20.000000 20.000000
      vertex 0.000000 20.000000 20.000000
      vertex 0.000000 0.000000 20.000000
    endloop
  endfacet
  facet normal 0.000000 -1.000000 0.000000
    outer loop
      vertex 0.000000 0.000000 0.000000
      vertex 20.000000 0.000000 0.000000
      vertex 20.000000 0.000000 20.000000
    endloop
  endfacet
  facet normal 0.000000 -1.000000 0.000000
    outer loop
      vertex 20.000000 0.000000 20.000000
      vertex 0.000000 0.000000 20.000000
      vertex 0.000000 0.000000 0.000000
    endloop
  endfacet
  facet normal 1.000000 0.000000 0.000000
    outer loop
      vertex 20.000000 0.000000 0.000000
      vertex 20.000000 20.000000 0.000000
      vertex 20.000000 20.000000 20.000000
    endloop
  endfacet
  facet normal 1.000000 0.000000 0.000000
    outer loop
      vertex 20.000000 20.000000 20.000000
      vertex 20.000000 0.000000 20.000000
      vertex 20.000000 0.000000 0.000000
    endloop
  endfacet
  facet normal 0.000000 1.000000 0.000000
    outer loop
      vertex 20.000000 20.000000 0.000000
      vertex 0.000000 20.000000 0.000000
      vertex 0.000000 20.000000 20.000000
    endloop
  endfacet
  facet normal 0.000000 1.000000 0.000000
    outer loop
      vertex 0.000000 20.000000 20.000000
      vertex 20.000000 20.000000 20.000000
      vertex 20.000000 20.000000 0.000000
    endloop
  endfacet
  facet normal -1.000000 0.000000 0.000000
    outer loop
      vertex 0.000000 20.000000 0.000000
      vertex 0.000000 0.000000 0.000000
      vertex 0.000000 0.000000 20.000000
    endloop
  endfacet
  facet normal -1.000000 0.000000 0.000000
    outer loop
      vertex 0.000000 0.000000 20.000000
      vertex 0.000000 20.000000 20.000000
      vertex 0.000000 20.000000 0.000000
    endloop
  endfacet
endsolid {clean_title}
"""
            zf.writestr(f"{clean_title}.stl", stl_content)

            # ข้อมูลคำแนะนำการพิมพ์และการใช้งาน (Print Specifications)
            spec_info = f"""================================================================================
PrintVerse 3D Printing Specifications & Instructions
================================================================================
Model Title       : {model.title}
Category          : {model.category}
Primary Format    : {model.primary_format}
Author / Creator  : {model.author.username if model.author else 'PrintVerse Official'}
Estimated Size    : {model.file_size_mb} MB

PRINT PARAMETERS RECOMMENDED:
--------------------------------------------------------------------------------
Layer Height      : {model.print_setting.layer_height if model.print_setting else '0.20 mm'}
Infill Percentage : {model.print_setting.infill_percentage if model.print_setting else 20}%
Supports Required : {'Yes' if (model.print_setting and model.print_setting.supports_required) else 'No (Print-in-Place)'}
Recommended Material : {model.filament_info.material_type if model.filament_info else 'PLA / PETG'}
Estimated Weight  : ~{model.filament_info.filament_weight_grams if model.filament_info else 50.0} grams

LICENSE & USAGE:
--------------------------------------------------------------------------------
Licensed to       : {current_user.username} ({current_user.email})
Download Date     : {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
Usage Rights      : Personal & Prototyping Use. Commercial redistribution prohibited.
Platform          : PrintVerse 3D Marketplace (http://127.0.0.1:5000)
================================================================================
"""
            zf.writestr("PRINT_SPECIFICATIONS.txt", spec_info)

        mem_buffer.seek(0)
        return send_file(
            mem_buffer,
            as_attachment=True,
            download_name=f"{clean_title}_3D_Package.zip",
            mimetype="application/zip"
        )

    # ----------------------------------------------------------------------------
    # ระบบกดถูกใจสินค้าแต่ละชิ้น (Like / Favorite System)
    # ----------------------------------------------------------------------------
    @app.route("/model/<int:model_id>/like", methods=["POST"])
    def toggle_like_model(model_id):
        """
        ระบบกดถูกใจ / ยกเลิกถูกใจโมเดล 3D (Toggle Like/Favorite)
        - ตรวจสอบว่าผู้ใช้ล็อกอินหรือไม่ หากยังไม่ได้ล็อกอินจะส่งข้อความแจ้งเตือน (หรือ JSON 401 ถ้าเป็น AJAX)
        - หากเคยกดถูกใจแล้ว -> ลบรายการ Like ออก และลด likes_count ลง 1
        - หากยังไม่เคยกดถูกใจ -> สร้างรายการ Like ใหม่ และเพิ่ม likes_count ขึ้น 1
        - รองรับทั้งการเรียกผ่าน AJAX/Fetch API (คืนค่า JSON) และ Form Submit ทั่วไป (Redirect)
        """
        if not current_user.is_authenticated:
            is_ajax = (request.is_json or 
                       request.headers.get("X-Requested-With") == "XMLHttpRequest" or 
                       "application/json" in request.headers.get("Accept", ""))
            if is_ajax:
                return jsonify({"error": "unauthorized", "message": "กรุณาเข้าสู่ระบบก่อนกดถูกใจสินค้า"}), 401
            flash("กรุณาเข้าสู่ระบบก่อนกดถูกใจสินค้า", "warning")
            return redirect(url_for("login"))

        model = Model3D.query.get_or_404(model_id)
        existing_like = ModelLike.query.filter_by(user_id=current_user.id, model_id=model.id).first()

        if existing_like:
            db.session.delete(existing_like)
            model.likes_count = max(0, (model.likes_count or 0) - 1)
            db.session.commit()
            liked = False
        else:
            new_like = ModelLike(user_id=current_user.id, model_id=model.id)
            db.session.add(new_like)
            model.likes_count = (model.likes_count or 0) + 1
            db.session.commit()
            liked = True

        is_ajax = (request.is_json or 
                   request.headers.get("X-Requested-With") == "XMLHttpRequest" or 
                   "application/json" in request.headers.get("Accept", ""))
        if is_ajax:
            return jsonify({
                "success": True,
                "status": "ok",
                "liked": liked,
                "likes_count": model.likes_count or 0,
                "model_id": model.id
            })

        return redirect(request.referrer or url_for("model_detail", model_id=model.id))

    @app.route("/favorites")
    @login_required
    def favorites():
        """
        หน้ารายการโมเดล 3D ที่ผู้ใช้กดถูกใจไว้ทั้งหมด (Liked/Favorite Models)
        """
        liked_entries = current_user.likes.order_by(ModelLike.created_at.desc()).all()
        liked_model_ids = [l.model_id for l in liked_entries]
        models = Model3D.query.filter(
            Model3D.id.in_(liked_model_ids),
            (Model3D.is_approved == True) | (Model3D.status == 'อนุมัติแล้ว')
        ).all() if liked_model_ids else []
        
        # จัดเรียงตามลำดับที่กดถูกใจล่าสุด
        model_dict = {m.id: m for m in models}
        ordered_models = [model_dict[mid] for mid in liked_model_ids if mid in model_dict]

        purchased_ids = {p.model_id for p in current_user.downloads}
        cart_ids = set(session.get("cart", []))

        return render_template(
            "favorites.html",
            models=ordered_models,
            purchased_ids=purchased_ids,
            cart_ids=cart_ids
        )


    # ============================================================================
    # ส่วนที่ 5: ระบบตะกร้าสินค้าและการสั่งซื้อ (Shopping Cart & Checkout System)
    # ============================================================================

    @app.route("/cart")
    @login_required
    def cart():
        """
        หน้าตะกร้าสินค้า (Shopping Cart)
        - ดึงรายการโมเดลที่บันทึกไว้ใน Session ของผู้ใช้
        - แสดงราคาสินค้าที่รวมภาษีมูลค่าเพิ่ม VAT 7% เรียบร้อยแล้ว พร้อมแยกราคาก่อนภาษีและ VAT
        """
        cart_ids = session.get("cart", [])
        cart_models = Model3D.query.filter(Model3D.id.in_(cart_ids)).all() if cart_ids else []
        total_price = sum(m.price for m in cart_models if not m.is_free)
        subtotal = round(total_price / 1.07, 2)
        vat_amount = round(total_price - subtotal, 2)
        return render_template(
            "cart.html", 
            cart_models=cart_models, 
            subtotal=subtotal, 
            vat_amount=vat_amount, 
            total_price=total_price
        )

    @app.route("/cart/add/<int:model_id>", methods=["POST"])
    @login_required
    def cart_add(model_id):
        """
        เพิ่มสินค้าลงในตะกร้า (เก็บ ID ไว้ใน Session['cart'])
        - ตรวจสอบก่อนว่าเคยซื้อไฟล์นี้ไปแล้วหรือยัง หากมีแล้วจะไม่ให้ใส่ซ้ำ
        """
        model = Model3D.query.get_or_404(model_id)
        if ModelPurchase.query.filter_by(user_id=current_user.id, model_id=model_id).first():
            flash(f"คุณมีไฟล์ '{model.title}' ในคลังของคุณแล้ว", "info")
            return redirect(request.referrer or url_for("index"))

        cart = session.get("cart", [])
        if model_id not in cart:
            cart.append(model_id)
            session["cart"] = cart
            flash(f"เพิ่ม '{model.title}' ลงในตะกร้าเรียบร้อยแล้ว", "success")
        else:
            flash(f"'{model.title}' อยู่ในตะกร้าสินค้าแล้ว", "info")
        return redirect(request.referrer or url_for("index"))

    @app.route("/cart/remove/<int:model_id>", methods=["POST"])
    @login_required
    def cart_remove(model_id):
        """
        นำสินค้าออกจากตะกร้า
        """
        cart = session.get("cart", [])
        if model_id in cart:
            cart.remove(model_id)
            session["cart"] = cart
            flash("นำโมเดลออกจากตะกร้าแล้ว", "info")
        return redirect(url_for("cart"))

    @app.route("/cart/checkout", methods=["POST"])
    @login_required
    def cart_checkout():
        """
        การชำระเงินสำหรับสินค้าทั้งหมดในตะกร้า (Cart Checkout)
        - ราคาหน้ารวม VAT 7% แล้ว ตัดเงินเท่ากับราคาที่แสดงจริง
        - โอนรายได้ราคาสินค้าให้คนขาย และบันทึกประวัติการสั่งซื้อ
        """
        cart_ids = session.get("cart", [])
        if not cart_ids:
            flash("ไม่มีสินค้าในตะกร้า", "info")
            return redirect(url_for("cart"))

        cart_models = Model3D.query.filter(Model3D.id.in_(cart_ids)).all()
        total_price = sum(m.price for m in cart_models if not m.is_free)
        subtotal = round(total_price / 1.07, 2)
        vat_amount = round(total_price - subtotal, 2)

        # ตรวจสอบยอดเงินในกระเป๋าเทียบกับยอดรวมสุทธิ (ราคารวม VAT แล้ว)
        if current_user.wallet_balance < total_price:
            flash(f"ยอดเงินคงเหลือไม่พอ (ยอดรวมชำระ ฿{total_price:.2f} | คุณมี ฿{current_user.wallet_balance:.2f}) สามารถเติมเงินได้ที่หน้ากระเป๋าเงิน", "danger")
            return redirect(url_for("cart"))

        # ตัดยอดเงินจากกระเป๋าผู้ซื้อ
        current_user.wallet_balance -= total_price
        last_purchase_id = None
        for m in cart_models:
            if not ModelPurchase.query.filter_by(user_id=current_user.id, model_id=m.id).first():
                if not m.is_free and m.price > 0:
                    item_price = m.price
                    seller_income = round(m.price / 1.07, 2)
                else:
                    item_price = 0.0
                    seller_income = 0.0
                seller_id = m.user_id

                # โอนรายได้ราคาสินค้าเข้าบัญชีกระเป๋าของคนโพสต์ขายโมเดลทันที
                if seller_income > 0 and seller_id and seller_id != current_user.id:
                    seller = User.query.get(seller_id)
                    if seller:
                        seller.wallet_balance += seller_income

                p = ModelPurchase(
                    user_id=current_user.id,
                    model_id=m.id,
                    price_paid=item_price,
                    seller_id=seller_id,
                    seller_income=seller_income
                )
                db.session.add(p)
                db.session.flush()
                last_purchase_id = p.id

        # ล้างตะกร้าสินค้าใน Session
        session["cart"] = []
        db.session.commit()
        flash("สั่งซื้อสินค้าทั้งหมดในตะกร้าสำเร็จ ดาวน์โหลดไฟล์ได้ที่คลังของคุณ", "success")
        if last_purchase_id:
            return redirect(url_for("dashboard", new_purchase_id=last_purchase_id))
        return redirect(url_for("dashboard"))

    # ----------------------------------------------------------------------------
    # การสั่งซื้อสินค้าทันทีแบบด่วน / ดาวน์โหลดฟรี (Instant Buy / Fast Download)
    # ----------------------------------------------------------------------------
    @app.route("/buy/<int:model_id>", methods=["POST"])
    @login_required
    def buy_model(model_id):
        """
        สั่งซื้อโมเดลทันทีโดยไม่ต้องผ่านตะกร้า (Buy Now)
        - หากเป็นโมเดลฟรี: บันทึกลงคลังได้ทันที ไม่ต้องหักเงิน
        - หากเป็นโมเดลเสียเงิน: หักเงินเท่ากับราคาที่แสดงหน้าสินค้า (ราคารวมภาษีมูลค่าเพิ่ม VAT 7% แล้ว)
        - โอนรายได้ราคาสินค้าก่อน VAT (Base Price) เข้ากระเป๋าคนโพสต์ขายโมเดล
        """
        model = Model3D.query.get_or_404(model_id)

        # ตรวจสอบว่าเคยเป็นเจ้าของแล้วหรือไม่
        existing = ModelPurchase.query.filter_by(user_id=current_user.id, model_id=model_id).first()
        if existing:
            flash(f"คุณมีไฟล์ '{model.title}' ในคลังของคุณแล้ว", "info")
            return redirect(url_for("dashboard"))

        seller_id = model.user_id
        seller_income = 0.0

        # ตรวจสอบกรณีโมเดลมีราคา
        if not model.is_free and model.price > 0:
            # ราคา model.price คือราคารวม VAT 7% แล้วตามที่แสดงบนการ์ดสินค้า
            total_amount = round(model.price, 2)
            base_price = round(total_amount / 1.07, 2)
            vat_amount = round(total_amount - base_price, 2)

            if current_user.wallet_balance < total_amount:
                flash(f"ยอดเงินคงเหลือไม่พอ (ราคาสินค้า ฿{total_amount:.2f} | คุณมี ฿{current_user.wallet_balance:.2f}) กรุณาเติมเงินก่อนทำรายการ", "danger")
                return redirect(url_for("model_detail", model_id=model.id))

            # หักเงินจาก Wallet ของผู้ซื้อตามราคาที่แสดงบนการ์ดสินค้า
            current_user.wallet_balance -= total_amount

            # โอนเงินรายได้ราคาสินค้าให้คนโพสต์ขายโมเดลทันที
            if seller_id and seller_id != current_user.id:
                seller = User.query.get(seller_id)
                if seller:
                    seller.wallet_balance += base_price
                    seller_income = base_price

            purchase = ModelPurchase(
                user_id=current_user.id,
                model_id=model.id,
                price_paid=total_amount,
                seller_id=seller_id,
                seller_income=seller_income
            )
        else:
            purchase = ModelPurchase(
                user_id=current_user.id,
                model_id=model.id,
                price_paid=0.0,
                seller_id=seller_id,
                seller_income=0.0
            )

        # นำออกจากตะกร้าถ้ามีอยู่
        cart = session.get("cart", [])
        if model_id in cart:
            cart.remove(model_id)
            session["cart"] = cart

        db.session.add(purchase)
        db.session.commit()

        flash(f"ได้รับไฟล์ '{model.title}' เรียบร้อยแล้ว จัดเก็บในคลังของคุณแล้ว", "success")
        return redirect(url_for("dashboard", new_purchase_id=purchase.id))

    # ============================================================================
    # ส่วนที่ 6: ระบบจัดการข้อมูลส่วนตัวของผู้ใช้ (User Profile & Account Settings)
    # ============================================================================

    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        """
        หน้าโปรไฟล์ผู้ใช้งาน (User Profile)
        - แสดงข้อมูลบัญชีผู้ใช้, ยอดเงินในกระเป๋า (Wallet), ป้าย Maker Badge
        - แก้ไขข้อมูลส่วนตัว: ชื่อผู้ใช้ (Username) และ เบอร์โทรศัพท์ (Phone Number)
        - เปลี่ยนรหัสผ่าน: ตรวจสอบรหัสผ่านเดิม และบันทึกรหัสผ่านใหม่ (อย่างน้อย 6 ตัวอักษร)
        """
        if request.method == "POST":
            action = request.form.get("action")
            
            # 1. แก้ไขข้อมูลส่วนตัว (ชื่อผู้ใช้, เบอร์โทรศัพท์, ที่อยู่, Bio, สเปกเครื่องพิมพ์, Maker Badge)
            if action == "update_info":
                verify_password = request.form.get("verify_password", "")
                if not verify_password:
                    flash("กรุณากรอกรหัสผ่านเข้าสู่ระบบปัจจุบันของคุณเพื่อยืนยันการแก้ไขข้อมูลส่วนตัวและที่อยู่", "danger")
                    return redirect(url_for("profile"))

                if not current_user.check_password(verify_password):
                    flash("รหัสผ่านยืนยันไม่ถูกต้อง! กรุณากรอกรหัสผ่านเข้าสู่ระบบของคุณให้ถูกต้องเพื่อบันทึกการเปลี่ยนแปลง", "danger")
                    return redirect(url_for("profile"))

                new_username = request.form.get("username", "").strip()
                new_phone = request.form.get("phone", "").strip()
                new_address = request.form.get("address", "").strip()
                new_bio = request.form.get("bio", "").strip()
                new_printer = request.form.get("printer_setup", "").strip()
                new_badge = request.form.get("maker_badge", "").strip()
                
                if not new_username:
                    flash("กรุณากรอกชื่อผู้ใช้", "danger")
                    return redirect(url_for("profile"))

                # ตรวจสอบชื่อผู้ใช้ซ้ำกับคนอื่นในระบบ
                existing_user = User.query.filter(User.username == new_username, User.id != current_user.id).first()
                if existing_user:
                    flash("ชื่อผู้ใช้นี้มีคนใช้แล้ว โปรดเลือกชื่ออื่น", "danger")
                    return redirect(url_for("profile"))

                current_user.username = new_username
                current_user.phone_number = new_phone
                current_user.address = new_address
                if new_bio:
                    current_user.bio = new_bio
                if new_printer:
                    current_user.printer_setup = new_printer
                if new_badge:
                    current_user.maker_badge = new_badge

                db.session.commit()
                flash("ยืนยันรหัสผ่านถูกต้อง และบันทึกข้อมูลส่วนตัว/ที่อยู่เรียบร้อยแล้ว", "success")
                return redirect(url_for("profile"))

            # 2. แก้ไขรหัสผ่านเข้าสู่ระบบ
            elif action == "update_password":
                current_password = request.form.get("current_password", "")
                new_password = request.form.get("new_password", "")
                confirm_new_password = request.form.get("confirm_new_password", "")

                # ตรวจสอบรหัสผ่านปัจจุบันว่าถูกต้องหรือไม่
                if not current_user.check_password(current_password):
                    flash("รหัสผ่านปัจจุบันไม่ถูกต้อง", "danger")
                    return redirect(url_for("profile"))

                # ตรวจสอบความยาวรหัสผ่านใหม่
                if len(new_password) < 6:
                    flash("รหัสผ่านใหม่ต้องมีความยาวอย่างน้อย 6 ตัวอักษร", "danger")
                    return redirect(url_for("profile"))

                # ตรวจสอบการยืนยันรหัสผ่านใหม่
                if new_password != confirm_new_password:
                    flash("รหัสผ่านใหม่และการยืนยันรหัสผ่านไม่ตรงกัน", "danger")
                    return redirect(url_for("profile"))

                # เข้ารหัสและบันทึกรหัสผ่านใหม่
                current_user.set_password(new_password)
                db.session.commit()
                flash("เปลี่ยนรหัสผ่านเรียบร้อยแล้ว", "success")
                return redirect(url_for("profile"))

            # 3. รีเซ็ตรหัสผ่านใหม่ด้วยรหัส OTP ทางอีเมล (เมื่อลืมรหัสผ่านปัจจุบัน)
            elif action == "reset_password_otp":
                otp_code = request.form.get("otp_code", "").strip()
                new_password = request.form.get("new_password", "")
                confirm_new_password = request.form.get("confirm_new_password", "")

                if not otp_code or not new_password or not confirm_new_password:
                    flash("กรุณากรอกรหัส OTP 6 หลัก และรหัสผ่านใหม่ให้ครบถ้วนทุกช่อง", "danger")
                    return redirect(url_for("profile", tab="otp"))

                # ตรวจสอบรหัส OTP ในตาราง email_otps
                otp_record = EmailOTP.query.filter_by(
                    email=current_user.email,
                    is_used=False
                ).order_by(EmailOTP.created_at.desc()).first()

                if not otp_record or otp_record.otp_code != otp_code:
                    flash("รหัส OTP ไม่ถูกต้อง กรุณาตรวจสอบรหัส 6 หลักในอีเมลของคุณอีกครั้ง", "danger")
                    return redirect(url_for("profile", tab="otp"))

                if datetime.utcnow() > otp_record.expires_at:
                    flash("รหัส OTP นี้หมดอายุแล้ว (เกิน 10 นาที) กรุณากดขอรับรหัส OTP ใหม่อีกครั้ง", "danger")
                    return redirect(url_for("profile", tab="otp"))

                if len(new_password) < 6:
                    flash("รหัสผ่านใหม่ต้องมีความยาวอย่างน้อย 6 ตัวอักษร", "danger")
                    return redirect(url_for("profile", tab="otp"))

                if new_password != confirm_new_password:
                    flash("รหัสผ่านใหม่และการยืนยันรหัสผ่านไม่ตรงกัน", "danger")
                    return redirect(url_for("profile", tab="otp"))

                # ทำเครื่องหมายว่าใช้ OTP แล้ว
                otp_record.is_used = True

                # แฮชรหัสผ่านใหม่และบันทึกลงฐานข้อมูล
                current_user.set_password(new_password)
                db.session.commit()

                flash("ยืนยันรหัส OTP ถูกต้อง! ตั้งรหัสผ่านใหม่เรียบร้อยแล้ว", "success")
                return redirect(url_for("profile"))

        return render_template("profile.html", user=current_user)

    @app.route("/api/profile/send-reset-otp", methods=["POST"])
    @login_required
    def profile_send_reset_otp():
        """
        API ส่งรหัส OTP 6 หลักสำหรับรีเซ็ตรหัสผ่านไปยังอีเมลของผู้ใช้ที่กำลังเข้าสู่ระบบอยู่
        """
        email = current_user.email
        username = current_user.username

        otp_code = f"{random.randint(100000, 999999):06d}"
        expires_at = datetime.utcnow() + timedelta(minutes=10)

        # ยกเลิก OTP เก่าของอีเมลนี้
        EmailOTP.query.filter_by(email=email, is_used=False).delete()

        otp_record = EmailOTP(
            email=email,
            otp_code=otp_code,
            expires_at=expires_at,
            is_used=False
        )
        db.session.add(otp_record)
        db.session.commit()

        is_sent, err = send_password_reset_otp_email(email, otp_code, username)

        return jsonify({
            "success": True,
            "is_sent": is_sent,
            "message": f"ระบบได้ส่งรหัส OTP 6 หลักไปยังอีเมล '{email}' เรียบร้อยแล้ว (หมดอายุใน 10 นาที)" if is_sent else f"ส่งรหัส OTP เรียบร้อยแล้ว"
        })

    @app.route("/profile/send-reset-otp", methods=["POST"])
    @login_required
    def profile_request_reset_otp_form():
        """
        ส่งรหัส OTP สำหรับรีเซ็ตรหัสผ่าน (รองรับแบบ Standard Form Submit)
        """
        email = current_user.email
        username = current_user.username

        otp_code = f"{random.randint(100000, 999999):06d}"
        expires_at = datetime.utcnow() + timedelta(minutes=10)

        EmailOTP.query.filter_by(email=email, is_used=False).delete()
        otp_record = EmailOTP(
            email=email,
            otp_code=otp_code,
            expires_at=expires_at,
            is_used=False
        )
        db.session.add(otp_record)
        db.session.commit()

        is_sent, err = send_password_reset_otp_email(email, otp_code, username)
        flash(f"ระบบได้ส่งรหัส OTP 6 หลักไปยังอีเมล '{email}' เรียบร้อยแล้ว กรุณานำรหัสมากรอกด้านล่าง", "success")
        return redirect(url_for("profile", tab="otp"))

    @app.route("/profile/avatar", methods=["POST"])
    @login_required
    def update_avatar():
        """
        อัปเดตรูปภาพโปรไฟล์ผู้ใช้
        - รองรับ 2 วิธี:
          1. อัปโหลดไฟล์รูปภาพจากเครื่องผู้ใช้ (File Upload)
          2. ถ่ายภาพสดจากกล้องเว็บแคม (Live Webcam Capture เป็น Base64)
        """
        avatar_data = request.form.get("avatar_data", "")
        if not avatar_data and request.is_json:
            avatar_data = (request.get_json(silent=True) or {}).get("avatar_data", "")

        filename = None
        # กรณีส่งภาพถ่ายจากกล้องเว็บแคม (Data URL Base64)
        if avatar_data and "base64," in avatar_data:
            try:
                header, encoded = avatar_data.split("base64,", 1)
                image_bytes = base64.b64decode(encoded)
                filename = f"avatar_{current_user.id}_{int(time.time())}.png"
                filepath = os.path.join(app.config["AVATARS_UPLOAD_FOLDER"], filename)
                with open(filepath, "wb") as f:
                    f.write(image_bytes)
            except Exception as e:
                if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                    return jsonify({"success": False, "message": f"ไม่สามารถประมวลผลรูปภาพได้: {str(e)}"}), 400
                flash("เกิดข้อผิดพลาดในการบันทึกรูปภาพจากกล้อง", "danger")
                return redirect(url_for("profile"))

        # กรณีอัปโหลดไฟล์ภาพจากเครื่อง
        elif "avatar_file" in request.files:
            file = request.files["avatar_file"]
            if file and file.filename != "":
                ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
                if ext in {"png", "jpg", "jpeg", "webp"}:
                    filename = f"avatar_{current_user.id}_{int(time.time())}.{ext}"
                    filepath = os.path.join(app.config["AVATARS_UPLOAD_FOLDER"], filename)
                    file.save(filepath)
                else:
                    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                        return jsonify({"success": False, "message": "รองรับเฉพาะไฟล์รูปภาพ (PNG, JPG, WEBP)"}), 400
                    flash("รองรับเฉพาะไฟล์รูปภาพ (PNG, JPG, WEBP)", "danger")
                    return redirect(url_for("profile"))

        if filename:
            # ลบไฟล์รูปเก่าถ้ามีและอยู่ในโฟลเดอร์ avatars
            if current_user.avatar_url and "/uploads/avatars/" in current_user.avatar_url:
                old_filename = os.path.basename(current_user.avatar_url)
                old_filepath = os.path.join(app.config["AVATARS_UPLOAD_FOLDER"], old_filename)
                if os.path.exists(old_filepath):
                    try:
                        os.remove(old_filepath)
                    except Exception:
                        pass

            current_user.avatar_url = f"/static/uploads/avatars/{filename}"
            db.session.commit()

            if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({
                    "success": True, 
                    "message": "อัปเดตรูปโปรไฟล์สำเร็จเรียบร้อยแล้ว",
                    "avatar_url": current_user.avatar_url
                })
            flash("อัปเดตรูปโปรไฟล์เรียบร้อยแล้ว", "success")
            return redirect(url_for("profile"))

        if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"success": False, "message": "ไม่พบข้อมูลรูปภาพ กรุณาเลือกไฟล์หรือถ่ายภาพ"}), 400
        flash("กรุณาเลือกไฟล์ภาพหรือถ่ายภาพก่อนกดบันทึก", "warning")
        return redirect(url_for("profile"))

    @app.route("/profile/avatar/remove", methods=["POST"])
    @login_required
    def remove_avatar():
        """ลบรูปโปรไฟล์ออกและใช้รูปภาพเริ่มต้น"""
        if current_user.avatar_url and "/uploads/avatars/" in current_user.avatar_url:
            old_filename = os.path.basename(current_user.avatar_url)
            old_filepath = os.path.join(app.config["AVATARS_UPLOAD_FOLDER"], old_filename)
            if os.path.exists(old_filepath):
                try:
                    os.remove(old_filepath)
                except Exception:
                    pass
        current_user.avatar_url = None
        db.session.commit()
        flash("ลบรูปโปรไฟล์เรียบร้อยแล้ว", "info")
        return redirect(url_for("profile"))


    # ============================================================================
    # ส่วนที่ 7: ระบบเติมเงินเข้ากระเป๋าและแนบสลิปโอนเงิน (Wallet Top-up System)
    # ============================================================================

    ALLOWED_SLIP_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "jfif", "bmp"}

    @app.route("/topup", methods=["GET", "POST"])
    @login_required
    def topup():
        """
        ระบบเติมเงินเข้ากระเป๋า (Wallet Top-up)
        - รองรับ 3 ช่องทางการโอน:
            1. พร้อมเพย์ (PromptPay QR) -> กำหนดต้นทางเป็น 'พร้อมเพย์' อัตโนมัติ
            2. โอนผ่านบัญชีธนาคาร (Banking) -> เลือกธนาคารต้นทางของผู้โอน
            3. TrueMoney Wallet -> กรอกเบอร์โทรศัพท์ที่ใช้โอน
        - แนบรูปภาพสลิปหลักฐานการโอนเงิน (บันทึกลง static/uploads/slips/)
        - รองรับการอนุมัติเงินเข้ากระเป๋าทันที (Instant Credit) หรือรอแอดมินตรวจสอบ
        """
        if request.method == "POST":
            # ตรวจสอบจำนวนเงินที่ระบุ
            try:
                amount = float(request.form.get("amount", 0))
            except ValueError:
                flash("กรุณากรอกจำนวนเงินเป็นตัวเลขที่ถูกต้อง", "danger")
                return redirect(url_for("topup"))

            if amount <= 0:
                flash("จำนวนเงินต้องมากกว่า 0 บาท", "danger")
                return redirect(url_for("topup"))

            payment_method = request.form.get("payment_method", "").strip()
            if not payment_method:
                payment_method = "พร้อมเพย์ (PromptPay QR)"

            transfer_time = request.form.get("transfer_time", "").strip()
            if not transfer_time:
                transfer_time = datetime.now().strftime("%d/%m/%Y %H:%M")

            # ตรวจสอบข้อมูลผู้โอนตามประเภทช่องทางที่เลือก
            if "TrueMoney" in payment_method:
                sender_info = request.form.get("sender_phone", "").strip() or "TrueMoney Wallet"
            elif "Banking" in payment_method:
                # โอนผ่าน Banking (โอนเข้าเลขบัญชีธนาคารกรุงไทย 919-0-582233)
                sender_info = request.form.get("sender_bank", "").strip() or "ธนาคารพาณิชย์ (Banking)"
            else:
                # โอนผ่าน พร้อมเพย์ (PromptPay QR) -> กำหนดเป็น พร้อมเพย์ อัตโนมัติ ไม่ต้องเลือกธนาคาร
                sender_info = "พร้อมเพย์"

            # ตรวจสอบไฟล์ภาพสลิป
            slip_file = request.files.get("slip")
            if not slip_file or slip_file.filename == "":
                flash("กรุณาแนบภาพสลิปหลักฐานการโอนเงิน", "danger")
                return redirect(url_for("topup"))

            ext = slip_file.filename.rsplit(".", 1)[-1].lower() if "." in slip_file.filename else ""
            if ext not in ALLOWED_SLIP_EXTENSIONS:
                flash("รองรับเฉพาะไฟล์ภาพนามสกุล .png, .jpg, .jpeg, .webp, .jfif, .bmp เท่านั้น", "danger")
                return redirect(url_for("topup"))

            # บันทึกไฟล์ภาพสลิปอย่างปลอดภัยด้วยชื่อที่ไม่ซ้ำกัน
            filename = f"slip_{current_user.id}_{int(datetime.utcnow().timestamp())}_{uuid.uuid4().hex[:6]}.{ext}"
            file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            slip_file.save(file_path)

            # บันทึกรายการลงฐานข้อมูลในสถานะ "รอการตรวจสอบ"
            # (ระบบจะแจ้งเตือนไปยังแอดมิน และยอดเงินจะไม่เข้ากระเป๋า จนกว่าแอดมินจะตรวจสอบสลิปและกดยืนยันอนุมัติ)
            topup_tx = TopupTransaction(
                user_id=current_user.id,
                amount=amount,
                payment_method=payment_method,
                sender_phone=sender_info,
                transfer_time=transfer_time,
                slip_image=filename,
                status="รอการตรวจสอบ"
            )
            db.session.add(topup_tx)
            db.session.commit()

            flash(f"แจ้งเติมเงิน ฿{amount:,.2f} ผ่าน {payment_method} เรียบร้อยแล้ว! ข้อมูลและสลิปถูกส่งแจ้งเตือนไปยังแอดมินแล้ว โปรดรอแอดมินตรวจสอบและกดยืนยัน ยอดเงินจะเข้ากระเป๋าของคุณทันที", "info")
            return redirect(url_for("topup"))

        # GET: แสดงหน้าจอเติมเงินและประวัติสลิปของผู้ใช้งานปัจจุบัน
        user_topups = current_user.topups.order_by(TopupTransaction.created_at.desc()).all()
        return render_template("topup.html", user=current_user, topups=user_topups)

    # ----------------------------------------------------------------------------
    # ระบบถอนเงินออกจากกระเป๋า Wallet กลับเข้าบัญชี (Wallet Withdrawal)
    # ----------------------------------------------------------------------------
    @app.route("/withdraw", methods=["GET", "POST"])
    @login_required
    def withdraw():
        """
        ระบบถอนเงินออกจากกระเป๋า (Wallet Withdrawal)
        - ผู้ใช้สามารถแจ้งถอนเงินจากรายได้ที่ขายโมเดล หรือเงินในกระเป๋าเข้าบัญชีตัวเอง
        - รองรับการถอนเงินผ่าน PromptPay และธนาคารพาณิชย์หลักในไทย
        - ตรวจสอบยอดเงินคงเหลือ (หักยอดทันทีเพื่อป้องกันการกดถอนซ้ำ)
        - ส่งคำขอไปยังแอดมินในสถานะ 'รอการตรวจสอบ'
        - หากแอดมินปฏิเสธ ระบบจะคืนเงินเข้ากระเป๋าให้อัตโนมัติ
        """
        if request.method == "POST":
            try:
                amount = float(request.form.get("amount", 0))
            except ValueError:
                flash("กรุณากรอกจำนวนเงินเป็นตัวเลขที่ถูกต้อง", "danger")
                return redirect(url_for("withdraw"))

            if amount <= 0:
                flash("จำนวนเงินที่ต้องการถอนต้องมากกว่า 0 บาท", "danger")
                return redirect(url_for("withdraw"))

            if amount > current_user.wallet_balance:
                flash(f"ยอดเงินคงเหลือไม่เพียงพอสำหรับการถอน (คุณมี ฿{current_user.wallet_balance:,.2f})", "danger")
                return redirect(url_for("withdraw"))

            bank_name = request.form.get("bank_name", "").strip()
            account_number = request.form.get("account_number", "").strip()
            account_name = request.form.get("account_name", "").strip()

            if not bank_name or not account_number or not account_name:
                flash("กรุณากรอกข้อมูลบัญชีรับเงินให้ครบถ้วนทุกช่อง", "danger")
                return redirect(url_for("withdraw"))

            # หักยอดเงินออกจากกระเป๋าของผู้ใช้ทันที
            current_user.wallet_balance -= amount

            withdraw_tx = WithdrawalTransaction(
                user_id=current_user.id,
                amount=amount,
                bank_name=bank_name,
                account_number=account_number,
                account_name=account_name,
                status="รอการตรวจสอบ"
            )
            db.session.add(withdraw_tx)
            db.session.commit()

            fee = withdraw_tx.fee
            net_amount = withdraw_tx.net_amount
            flash(f"แจ้งขอถอนเงินจำนวน ฿{amount:,.2f} เรียบร้อยแล้ว! (หักค่าบริการ 1% ฿{fee:,.2f} ยอดเงินที่จะโอนเข้าบัญชีสุทธิ ฿{net_amount:,.2f}) คำขออยู่ระหว่างรอแอดมินดำเนินการโอนเงินเข้าบัญชี {bank_name} ({account_number})", "success")
            return redirect(url_for("withdraw"))

        # GET: แสดงหน้าจอถอนเงินและประวัติการถอน
        user_withdrawals = current_user.withdrawals.order_by(WithdrawalTransaction.created_at.desc()).all()
        return render_template("withdraw.html", user=current_user, withdrawals=user_withdrawals)

    # ----------------------------------------------------------------------------
    # ระบบสลีปธุรกรรมและประวัติการโอนเข้า-โอนออก (Transaction Slips & In/Out History)
    # ----------------------------------------------------------------------------
    @app.route("/wallet/transactions")
    @login_required
    def wallet_transactions():
        """
        หน้ารวมประวัติธุรกรรมกระเป๋าเงินทั้งหมด (โอนเข้า / โอนออก)
        - โอนเข้า (Inflow): เติมเงินเข้ากระเป๋า, รายได้จากการขายโมเดล
        - โอนออก (Outflow): ถอนเงินกลับบัญชี, การซื้อโมเดล
        - รองรับการกรองตามประเภทธุรกรรม (ทั้งหมด / โอนเข้า / โอนออก)
        - รองรับการกดดูสลีปและดาวน์โหลดเป็นไฟล์ PDF ได้ทุกรายการ
        """
        topups = current_user.topups.order_by(TopupTransaction.created_at.desc()).all()
        withdrawals = current_user.withdrawals.order_by(WithdrawalTransaction.created_at.desc()).all()
        sales = current_user.sales.order_by(ModelPurchase.purchased_at.desc()).all()
        purchases = current_user.downloads.filter(ModelPurchase.price_paid > 0).order_by(ModelPurchase.purchased_at.desc()).all()

        combined = []
        for t in topups:
            combined.append({
                "id": t.id,
                "type": "topup",
                "direction": "in",
                "title": "เติมเงินเข้ากระเป๋า",
                "description": f"ผ่าน {t.payment_method}",
                "amount": t.amount,
                "status": t.status,
                "created_at": t.created_at,
                "ref_id": f"PV-TOP-{t.id:04d}",
                "slip_url": url_for("slip_topup", tx_id=t.id) if (t.status == "สำเร็จ" or current_user.is_admin) else None,
                "obj": t
            })
        for w in withdrawals:
            combined.append({
                "id": w.id,
                "type": "withdraw",
                "direction": "out",
                "title": "ถอนเงินกลับบัญชี",
                "description": f"เข้า {w.bank_name} ({w.account_number})",
                "amount": w.amount,
                "status": w.status,
                "created_at": w.created_at,
                "ref_id": f"PV-WD-{w.id:04d}",
                "slip_url": url_for("slip_withdraw", tx_id=w.id) if (w.status == "สำเร็จ" or current_user.is_admin) else None,
                "obj": w
            })
        for s in sales:
            combined.append({
                "id": s.id,
                "type": "sale",
                "direction": "in",
                "title": "รายได้จากการขายโมเดล",
                "description": f"โมเดล: {s.model.title if s.model else 'ไฟล์ 3D'}",
                "amount": s.seller_income,
                "status": "สำเร็จ",
                "created_at": s.purchased_at,
                "ref_id": f"PV-SALE-{s.id:04d}",
                "slip_url": None,
                "obj": s
            })
        for p in purchases:
            combined.append({
                "id": p.id,
                "type": "purchase",
                "direction": "out",
                "title": "ซื้อโมเดล 3 มิติ",
                "description": f"โมเดล: {p.model.title if p.model else 'ไฟล์ 3D'}",
                "amount": p.price_paid,
                "status": "สำเร็จ",
                "created_at": p.purchased_at,
                "ref_id": f"PV-ORD-{p.id:04d}",
                "slip_url": url_for("slip_order", purchase_id=p.id),
                "obj": p
            })

        combined.sort(key=lambda x: x["created_at"] or datetime.min, reverse=True)

        total_in = sum(item["amount"] for item in combined if item["direction"] == "in" and item["status"] == "สำเร็จ")
        total_out = sum(item["amount"] for item in combined if item["direction"] == "out" and item["status"] in ("สำเร็จ", "รอการตรวจสอบ"))

        return render_template(
            "wallet_transactions.html",
            user=current_user,
            transactions=combined,
            total_in=total_in,
            total_out=total_out,
            topups=topups,
            withdrawals=withdrawals
        )

    @app.route("/slip/topup/<int:tx_id>")
    @login_required
    def slip_topup(tx_id):
        """
        แสดงใบสลีปอิเล็กทรอนิกส์สำหรับการเติมเงิน (Top-up e-Slip)
        - อนุญาตเฉพาะเจ้าของรายการ หรือแอดมินระบบ
        - สามารถกดพิมพ์ หรือดาวน์โหลดเป็นไฟล์ PDF
        """
        tx = TopupTransaction.query.get_or_404(tx_id)
        if tx.user_id != current_user.id and not current_user.is_admin:
            flash("คุณไม่มีสิทธิ์เข้าถึงสลีปรายการนี้", "danger")
            return redirect(url_for("topup"))

        if tx.status != "สำเร็จ" and not current_user.is_admin:
            flash("รายการเติมเงินนี้ต้องรอให้แอดมินตรวจสอบและอนุมัติก่อน จึงจะมีสลีปยืนยันการเติมเงิน", "warning")
            return redirect(url_for("topup"))

        return render_template("slip_topup.html", tx=tx, user=tx.user)

    @app.route("/slip/withdraw/<int:tx_id>")
    @login_required
    def slip_withdraw(tx_id):
        """
        แสดงใบสลีปอิเล็กทรอนิกส์สำหรับการถอนเงิน (Withdrawal e-Slip)
        - อนุญาตเฉพาะเจ้าของรายการ หรือแอดมินระบบ
        - ต้องได้รับการอนุมัติ/ยืนยันจากแอดมินแล้วเท่านั้น (status == 'สำเร็จ')
        - สามารถกดพิมพ์ หรือดาวน์โหลดเป็นไฟล์ PDF
        """
        tx = WithdrawalTransaction.query.get_or_404(tx_id)
        if tx.user_id != current_user.id and not current_user.is_admin:
            flash("คุณไม่มีสิทธิ์เข้าถึงสลีปรายการนี้", "danger")
            return redirect(url_for("withdraw"))

        if tx.status != "สำเร็จ" and not current_user.is_admin:
            flash("รายการถอนเงินนี้ต้องรอให้แอดมินตรวจสอบและยืนยันการโอนเงินก่อน จึงจะมีสลีปให้ดู", "warning")
            return redirect(url_for("withdraw"))

        return render_template("slip_withdraw.html", tx=tx, user=tx.user)

    @app.route("/slip/order/<int:purchase_id>")
    @login_required
    def slip_order(purchase_id):
        """
        หน้าแสดงใบเสร็จรับเงิน / ใบกำกับภาษีอย่างย่อ สำหรับคำสั่งซื้อโมเดล 3D
        - แสดงรายละเอียดผู้ซื้อ ผู้ขาย ชื่อโมเดล
        - แจกแจงมูลค่าก่อนภาษี และภาษีมูลค่าเพิ่ม VAT 7%
        - สามารถพิมพ์ หรือดาวน์โหลดเป็น PDF (ขนาด 1 หน้า A4 พอดี)
        """
        purchase = ModelPurchase.query.get_or_404(purchase_id)
        if purchase.user_id != current_user.id and purchase.seller_id != current_user.id and not current_user.is_admin:
            flash("คุณไม่มีสิทธิ์เข้าถึงใบเสร็จรายการนี้", "danger")
            return redirect(url_for("dashboard"))

        seller = purchase.seller or (purchase.model.user if purchase.model else None)
        return render_template("slip_order.html", purchase=purchase, buyer=purchase.user, seller=seller)


    # ============================================================================
    # ส่วนที่ 8: ระบบสมาชิก การเข้าสู่ระบบ และการออกจากระบบ (Authentication & Dashboard)
    # ============================================================================

    @app.route("/register", methods=["GET", "POST"])
    def register():
        """
        หน้ารงทะเบียนสมัครสมาชิกใหม่ (User Registration with Address & Email OTP)
        - กรอกชื่อผู้ใช้, อีเมล, เบอร์โทร, ที่อยู่ (Address), รหัสผ่าน
        - ตรวจสอบความถูกต้องและไม่ให้อีเมลหรือชื่อผู้ใช้ซ้ำกัน
        - ส่งรหัส OTP 6 หลักไปยังอีเมลจริงของผู้ใช้ (Real Email Verification)
        - เก็บข้อมูลชั่วคราวใน session["pending_registration"] จนกว่าจะยืนยัน OTP สำเร็จ
        """
        if current_user.is_authenticated:
            return redirect(url_for("index"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip().lower()
            phone = request.form.get("phone", "").strip()
            # รับข้อมูลที่อยู่ (รองรับทั้งแบบแยกช่อง ที่อยู่, ตำบล/แขวง, อำเภอ/เขต, จังหวัด, รหัสไปรษณีย์)
            address_detail = request.form.get("address_detail", "").strip()
            subdistrict = request.form.get("subdistrict", "").strip()
            district = request.form.get("district", "").strip()
            province = request.form.get("province", "").strip()
            postal_code = request.form.get("postal_code", "").strip()

            if address_detail or subdistrict or district or province or postal_code:
                addr_parts = []
                if address_detail:
                    addr_parts.append(address_detail)
                if subdistrict:
                    addr_parts.append(subdistrict if subdistrict.startswith(("ต.", "ตำบล", "แขวง")) else f"ต.{subdistrict}")
                if district:
                    addr_parts.append(district if district.startswith(("อ.", "อำเภอ", "เขต")) else f"อ.{district}")
                if province:
                    addr_parts.append(province if province.startswith(("จ.", "จังหวัด")) else f"จ.{province}")
                if postal_code:
                    addr_parts.append(postal_code)
                address = " ".join(addr_parts).strip()
            else:
                address = request.form.get("address", "").strip()

            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")
            printer_setup = request.form.get("printer_setup", "3D Printer").strip()

            if not username or not email or not password or not confirm_password:
                flash("กรุณากรอกข้อมูลที่จำเป็นให้ครบถ้วนทุกช่อง", "danger")
                return render_template("register.html")

            # ตรวจสอบรูปแบบอีเมล
            email_pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"
            if not re.match(email_pattern, email):
                flash("รูปแบบอีเมลไม่ถูกต้อง กรุณาระบุอีเมลที่ถูกต้อง (เช่น user@gmail.com)", "danger")
                return render_template("register.html")

            if len(password) < 6:
                flash("รหัสผ่านต้องมีความยาวอย่างน้อย 6 ตัวอักษร", "danger")
                return render_template("register.html")

            # ตรวจสอบยืนยันรหัสผ่านตรงกัน
            if password != confirm_password:
                flash("รหัสผ่านและการยืนยันรหัสผ่านไม่ตรงกัน", "danger")
                return render_template("register.html")

            # ตรวจสอบอีเมลหรือชื่อผู้ใช้ซ้ำในฐานข้อมูล
            if User.query.filter_by(email=email).first():
                flash("อีเมลนี้ถูกลงทะเบียนไว้ในระบบแล้ว", "danger")
                return render_template("register.html")

            if User.query.filter_by(username=username).first():
                flash("ชื่อผู้ใช้นี้มีคนใช้แล้ว โปรดเลือกชื่ออื่น", "danger")
                return render_template("register.html")

            # สุ่มรหัส OTP 6 หลัก
            otp_code = f"{random.randint(100000, 999999):06d}"
            expires_at = datetime.utcnow() + timedelta(minutes=10)

            # ยกเลิก OTP เก่าของอีเมลนี้
            EmailOTP.query.filter_by(email=email, is_used=False).delete()

            otp_record = EmailOTP(
                email=email,
                otp_code=otp_code,
                expires_at=expires_at,
                is_used=False
            )
            db.session.add(otp_record)
            db.session.commit()

            # บันทึกข้อมูลที่รอการยืนยันลง Session
            session["pending_registration"] = {
                "username": username,
                "email": email,
                "phone": phone,
                "address": address,
                "password": password,
                "printer_setup": printer_setup if printer_setup else "3D Printer"
            }

            # ส่งอีเมล OTP
            is_sent, err = send_registration_otp_email(email, otp_code, username)
            if is_sent:
                flash(f"ระบบได้ส่งรหัส OTP 6 หลักไปยังอีเมล '{email}' เรียบร้อยแล้ว กรุณานำรหัสมากรอกยืนยันภายใน 10 นาที", "success")
            else:
                flash(f"ระบบได้จัดส่งรหัสยืนยันไปยังอีเมล '{email}' แล้ว กรุณาตรวจสอบกล่องข้อความหรือกล่องอีเมลขยะ (Spam)", "info")

            return redirect(url_for("verify_otp"))

        return render_template("register.html")

    @app.route("/register/verify-otp", methods=["GET", "POST"])
    def verify_otp():
        """
        หน้าสำหรับกรอกรหัสยืนยัน OTP (Email OTP Verification)
        - ตรวจสอบรหัส OTP 6 หลักที่ส่งไปยังอีเมล
        - หากถูกต้อง จะสร้างบัญชีผู้ใช้ใหม่ลงฐานข้อมูลพร้อมที่อยู่ และเข้าสู่ระบบทันที
        """
        if current_user.is_authenticated:
            return redirect(url_for("index"))

        pending = session.get("pending_registration")
        if not pending:
            flash("ไม่มีข้อมูลการสมัครสมาชิกที่รอดำเนินการ กรุณากรอกข้อมูลสมัครสมาชิกใหม่", "warning")
            return redirect(url_for("register"))

        cfg = get_smtp_config()
        is_smtp_configured = bool(cfg.get("MAIL_USERNAME") and cfg.get("MAIL_PASSWORD"))
        latest_otp_record = EmailOTP.query.filter_by(
            email=pending["email"],
            is_used=False
        ).order_by(EmailOTP.created_at.desc()).first()
        dev_otp = latest_otp_record.otp_code if latest_otp_record else ""

        if request.method == "POST":
            otp_input = request.form.get("otp_code", "").strip()
            if not otp_input:
                otp_input = "".join([request.form.get(f"otp_{i}", "").strip() for i in range(1, 7)])

            if not otp_input:
                flash("กรุณากรอกรหัส OTP 6 หลัก", "danger")
                return render_template(
                    "verify_otp.html",
                    pending_email=pending["email"],
                    pending_username=pending["username"],
                    is_smtp_configured=is_smtp_configured,
                    dev_otp=dev_otp,
                    sender_email=cfg.get("MAIL_USERNAME", "")
                )

            otp_record = EmailOTP.query.filter_by(
                email=pending["email"],
                is_used=False
            ).order_by(EmailOTP.created_at.desc()).first()

            if not otp_record or otp_record.otp_code != otp_input:
                flash("รหัส OTP ไม่ถูกต้อง กรุณาตรวจสอบและลองใหม่อีกครั้ง", "danger")
                return render_template(
                    "verify_otp.html",
                    pending_email=pending["email"],
                    pending_username=pending["username"],
                    is_smtp_configured=is_smtp_configured,
                    dev_otp=dev_otp,
                    sender_email=cfg.get("MAIL_USERNAME", "")
                )

            if datetime.utcnow() > otp_record.expires_at:
                flash("รหัส OTP นี้หมดอายุแล้ว (เกิน 10 นาที) กรุณากดขอรับรหัสใหม่", "danger")
                return render_template(
                    "verify_otp.html",
                    pending_email=pending["email"],
                    pending_username=pending["username"],
                    is_smtp_configured=is_smtp_configured,
                    dev_otp=dev_otp,
                    sender_email=cfg.get("MAIL_USERNAME", "")
                )

            # OTP ถูกต้อง -> ตั้งสถานะว่าใช้แล้ว
            otp_record.is_used = True

            # สร้างบัญชีผู้ใช้ใหม่ลงตาราง users
            new_user = User(
                username=pending["username"],
                email=pending["email"],
                phone_number=pending.get("phone", ""),
                address=pending.get("address", ""),
                printer_setup=pending.get("printer_setup", "3D Printer"),
                maker_badge="Member",
                wallet_balance=0.0,
                email_verified=True
            )
            new_user.set_password(pending["password"])
            db.session.add(new_user)
            db.session.commit()

            # ล้าง session รอดำเนินการ
            session.pop("pending_registration", None)

            # เข้าสู่ระบบอัตโนมัติ
            login_user(new_user)
            flash(f"ยืนยันอีเมลสำเร็จ! ยินดีต้อนรับคุณ {new_user.username} สู่ PrintVerse 3D", "success")
            return redirect(url_for("index"))

        return render_template(
            "verify_otp.html",
            pending_email=pending["email"],
            pending_username=pending["username"],
            is_smtp_configured=is_smtp_configured,
            dev_otp=dev_otp,
            sender_email=cfg.get("MAIL_USERNAME", "")
        )

    @app.route("/register/resend-otp", methods=["POST"])
    def resend_otp():
        """
        ขอส่งรหัส OTP ใหม่อีกครั้ง (Resend OTP)
        """
        pending = session.get("pending_registration")
        if not pending:
            flash("ไม่มีข้อมูลการสมัครสมาชิกที่รอดำเนินการ กรุณากรอกข้อมูลสมัครสมาชิกใหม่", "warning")
            return redirect(url_for("register"))

        email = pending["email"]
        username = pending["username"]

        otp_code = f"{random.randint(100000, 999999):06d}"
        expires_at = datetime.utcnow() + timedelta(minutes=10)

        EmailOTP.query.filter_by(email=email, is_used=False).delete()
        otp_record = EmailOTP(
            email=email,
            otp_code=otp_code,
            expires_at=expires_at,
            is_used=False
        )
        db.session.add(otp_record)
        db.session.commit()

        is_sent, err = send_registration_otp_email(email, otp_code, username)
        if is_sent:
            flash(f"ระบบได้ส่งรหัส OTP ชุดใหม่ไปยังอีเมล '{email}' เรียบร้อยแล้ว", "success")
        else:
            flash(f"ระบบได้จัดส่งรหัสยืนยันชุดใหม่ไปยังอีเมล '{email}' แล้ว", "info")

        return redirect(url_for("verify_otp"))

    @app.route("/register/cancel", methods=["GET", "POST"])
    def cancel_registration():
        """
        ยกเลิกการสมัครสมาชิกที่รอดำเนินการและกลับไปหน้าสมัครใหม่
        """
        session.pop("pending_registration", None)
        flash("ยกเลิกการสมัครสมาชิกที่รอดำเนินการเรียบร้อยแล้ว", "info")
        return redirect(url_for("register"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        """
        หน้าเข้าสู่ระบบ (User Login)
        - ตรวจสอบอีเมลและรหัสผ่านผ่านการ Hashing (Werkzeug Security)
        - รองรับ Remember Me เพื่อจดจำสถานะการล็อกอิน
        - รองรับการใช้งานพร้อมกันหลายบัญชีบนเบราว์เซอร์หรือโปรไฟล์ที่แยกกัน
        """
        if current_user.is_authenticated:
            return redirect(url_for("index"))

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            remember = True if request.form.get("remember") else False

            user = User.query.filter_by(email=email).first()

            # ตรวจสอบรหัสผ่าน
            if not user or not user.check_password(password):
                flash("อีเมลหรือรหัสผ่านไม่ถูกต้อง โปรดลองอีกครั้ง", "danger")
                return render_template("login.html")

            login_user(user, remember=remember)
            flash("เข้าสู่ระบบสำเร็จ", "success")
            return redirect(url_for("index"))

        return render_template("login.html")

    @app.route("/api/forgot-password/send-otp", methods=["POST"])
    def forgot_password_send_otp():
        """
        API ส่งรหัส OTP 6 หลักสำหรับรีเซ็ตรหัสผ่านไปยังอีเมลจริงที่ผู้ใช้ระบุ (หน้า Login/Forgot Password)
        """
        data = request.get_json(silent=True) or request.form
        email = data.get("email", "").strip().lower()

        if not email:
            return jsonify({"success": False, "message": "กรุณากรอกอีเมลของคุณ"}), 400

        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({"success": False, "message": "ไม่พบบัญชีผู้ใช้ที่ลงทะเบียนด้วยอีเมลนี้ในระบบ"}), 404

        otp_code = f"{random.randint(100000, 999999):06d}"
        expires_at = datetime.utcnow() + timedelta(minutes=10)

        # ยกเลิก OTP เก่าของอีเมลนี้ที่ยังไม่ได้ใช้
        EmailOTP.query.filter_by(email=email, is_used=False).delete()

        otp_record = EmailOTP(
            email=email,
            otp_code=otp_code,
            expires_at=expires_at,
            is_used=False
        )
        db.session.add(otp_record)
        db.session.commit()

        is_sent, err = send_password_reset_otp_email(email, otp_code, user.username)

        return jsonify({
            "success": True,
            "is_sent": is_sent,
            "message": f"ระบบได้ส่งรหัส OTP 6 หลักไปยังอีเมล '{email}' เรียบร้อยแล้ว (หมดอายุใน 10 นาที)" if is_sent else f"ส่งรหัส OTP สำเร็จ (Dev Mode)"
        })

    @app.route("/forgot-password", methods=["GET", "POST"])
    def forgot_password():
        """
        ระบบลืมรหัสผ่านและรีเซ็ตรหัสผ่านใหม่ด้วย Email OTP (Forgot & Reset Password with OTP)
        - ผู้ใช้ระบุเฉพาะอีเมลที่ลงทะเบียน (ไม่ต้องกรอกเบอร์โทรศัพท์)
        - ต้องกดรับรหัส OTP 6 หลักส่งตรงไปยังอีเมลจริง
        - นำรหัส OTP มากดยืนยันพร้อมตั้งรหัสผ่านใหม่ (อย่างน้อย 6 ตัวอักษร)
        - แฮชรหัสผ่านใหม่และบันทึกลงฐานข้อมูล SQLite
        """
        if current_user.is_authenticated:
            return redirect(url_for("index"))

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            otp_code = request.form.get("otp_code", "").strip()
            new_password = request.form.get("new_password", "")
            confirm_new_password = request.form.get("confirm_new_password", "")

            if not email:
                flash("กรุณากรอกอีเมลของคุณ", "danger")
                return render_template("forgot_password.html", email=email)

            user = User.query.filter_by(email=email).first()
            if not user:
                flash("ไม่พบบัญชีผู้ใช้ที่ลงทะเบียนด้วยอีเมลนี้ในระบบ", "danger")
                return render_template("forgot_password.html", email=email)

            if not otp_code:
                flash("กรุณากรอกรหัส OTP 6 หลักที่ได้รับทางอีเมล", "danger")
                return render_template("forgot_password.html", email=email)

            # ตรวจสอบรหัส OTP ในตาราง EmailOTP
            valid_otp = EmailOTP.query.filter_by(
                email=email,
                otp_code=otp_code,
                is_used=False
            ).filter(EmailOTP.expires_at >= datetime.utcnow()).first()

            if not valid_otp:
                flash("รหัส OTP ไม่ถูกต้องหรือหมดอายุแล้ว (อายุ 10 นาที) กรุณากดขอรหัสใหม่อีกครั้ง", "danger")
                return render_template("forgot_password.html", email=email)

            if len(new_password) < 6:
                flash("รหัสผ่านใหม่ต้องมีความยาวอย่างน้อย 6 ตัวอักษร", "danger")
                return render_template("forgot_password.html", email=email)

            if new_password != confirm_new_password:
                flash("รหัสผ่านใหม่และการยืนยันรหัสผ่านไม่ตรงกัน", "danger")
                return render_template("forgot_password.html", email=email)

            # ทำเครื่องหมายว่า OTP นี้ถูกใช้งานแล้ว
            valid_otp.is_used = True

            # แฮชรหัสผ่านใหม่และบันทึกลงฐานข้อมูล
            user.set_password(new_password)
            db.session.commit()

            flash(f"ยืนยันรหัส OTP ถูกต้อง! ตั้งรหัสผ่านใหม่สำหรับบัญชี '{user.email}' เรียบร้อยแล้ว สามารถเข้าสู่ระบบด้วยรหัสผ่านใหม่ได้ทันที", "success")
            return redirect(url_for("login"))

        return render_template("forgot_password.html")

    @app.route("/dashboard")
    @login_required
    def dashboard():
        """
        หน้ารวมคลังโมเดลของฉัน (User Model Library & Downloads)
        - แสดงรายการโมเดล 3D ทั้งหมดที่ผู้ใช้เคยซื้อหรือดาวน์โหลดฟรี
        - แสดงลิงก์ดาวน์โหลดไฟล์โมเดลพร้อมพิมพ์
        - แสดงสลีปใบเสร็จรับเงินทันทีหากเพิ่งสั่งซื้อสำเร็จ (new_purchase_id)
        """
        new_purchase_id = request.args.get("new_purchase_id", type=int)
        new_purchase = None
        if new_purchase_id:
            new_purchase = ModelPurchase.query.filter_by(id=new_purchase_id, user_id=current_user.id).first()
        my_purchases = current_user.downloads.order_by(ModelPurchase.purchased_at.desc()).all()
        return render_template("dashboard.html", user=current_user, my_purchases=my_purchases, new_purchase=new_purchase)

    # ============================================================================
    # ส่วนที่ 9: ระบบอัปโหลดและจัดการโมเดลของผู้ใช้งานทั่วไป (User Model Upload & Management)
    # ============================================================================

    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
    ALLOWED_MODEL_EXTENSIONS = {"stl", "3mf", "step", "obj", "zip"}

    @app.route("/models/upload", methods=["GET", "POST"])
    @login_required
    def upload_model():
        """
        ระบบอัปโหลดโมเดล 3D ใหม่ (Upload 3D Model)
        - ผู้ใช้ทั่วไปสามารถกรอกข้อมูลโมเดลเพื่อลงขาย:
            * ชื่อสินค้า, คำอธิบาย, หมวดหมู่, ราคา (฿) หรือตั้งเป็นของฟรี
            * พารามิเตอร์การพิมพ์ (Layer Height, Infill %, Support Required)
            * วัสดุเส้นที่แนะนำ (PLA, PETG, ABS ฯลฯ) และน้ำหนักเส้นพลาสติก
            * อัปโหลดรูปภาพตัวอย่าง (Thumbnail) เข้า static/uploads/thumbnails/
            * อัปโหลดไฟล์โมเดล 3D (.stl, .3mf, .step, .obj, .zip) เข้า static/uploads/files/
        - สิทธิ์และการอนุมัติ:
            * แอดมินโพสต์: อนุมัติทันที (is_approved=True, status='อนุมัติแล้ว')
            * ผู้ใช้ทั่วไป: ต้องรอการตรวจสอบจากแอดมิน (is_approved=False, status='รอการตรวจสอบ')
        """
        if request.method == "POST":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            category = request.form.get("category", "Gadgets & Tools").strip()

            # แปลงราคาเป็นตัวเลขทศนิยม
            try:
                price = float(request.form.get("price", 0))
                if price < 0:
                    price = 0.0
            except ValueError:
                price = 0.0

            primary_format = request.form.get("primary_format", "STL").strip()
            supported_formats = request.form.get("supported_formats", primary_format).strip()
            layer_height = request.form.get("layer_height", "0.20 mm").strip()

            try:
                infill_percentage = int(request.form.get("infill_percentage", 20))
            except ValueError:
                infill_percentage = 20

            supports_required = request.form.get("supports_required") == "yes"
            material_type = request.form.get("material_type", "PLA").strip()

            try:
                filament_weight_grams = float(request.form.get("filament_weight_grams", 50.0))
            except ValueError:
                filament_weight_grams = 50.0

            if not title:
                flash("กรุณาระบุชื่อสินค้า / โมเดล 3D", "danger")
                return redirect(url_for("upload_model"))

            # 1. จัดการอัปโหลดรูปภาพตัวอย่างสินค้า (Thumbnail)
            thumbnail_file = request.files.get("thumbnail")
            thumbnail_url = None
            if thumbnail_file and thumbnail_file.filename != "":
                ext = thumbnail_file.filename.rsplit(".", 1)[-1].lower() if "." in thumbnail_file.filename else ""
                if ext in ALLOWED_IMAGE_EXTENSIONS:
                    thumb_filename = f"model_thumb_{current_user.id}_{int(datetime.utcnow().timestamp())}_{uuid.uuid4().hex[:6]}.{ext}"
                    thumb_path = os.path.join(app.config["MODEL_UPLOAD_FOLDER"], thumb_filename)
                    thumbnail_file.save(thumb_path)
                    thumbnail_url = f"/static/uploads/thumbnails/{thumb_filename}"
                else:
                    flash("รูปภาพตัวอย่างต้องเป็นไฟล์ .png, .jpg, .jpeg, หรือ .webp เท่านั้น", "danger")
                    return redirect(url_for("upload_model"))

            # 2. จัดการอัปโหลดไฟล์โมเดล 3D จริง (3D Print File)
            model_file = request.files.get("model_file")
            file_size_mb = 5.0
            m_filename = None
            if model_file and model_file.filename != "":
                m_ext = model_file.filename.rsplit(".", 1)[-1].lower() if "." in model_file.filename else ""
                if m_ext in ALLOWED_MODEL_EXTENSIONS:
                    m_filename = f"model_file_{current_user.id}_{int(datetime.utcnow().timestamp())}_{uuid.uuid4().hex[:6]}.{m_ext}"
                    m_path = os.path.join(app.config["FILES_UPLOAD_FOLDER"], m_filename)
                    model_file.save(m_path)
                    file_size_mb = round(os.path.getsize(m_path) / (1024 * 1024), 2)
                    primary_format = m_ext.upper()

            # 3. กำหนดสถานะการอนุมัติ: แอดมินโพสต์จะผ่านทันที / ผู้ใช้ทั่วไปต้องรอการตรวจสอบ
            if current_user.is_admin:
                is_approved = True
                status = "อนุมัติแล้ว"
            else:
                is_approved = False
                status = "รอการตรวจสอบ"

            # บันทึกข้อมูลโมเดล 3D ลง SQLite
            new_model = Model3D(
                title=title,
                description=description,
                category=category,
                price=price,
                is_free=(price <= 0),
                primary_format=primary_format,
                supported_formats=supported_formats,
                file_size_mb=file_size_mb,
                thumbnail_url=thumbnail_url,
                file_path=m_filename,
                user_id=current_user.id,
                status=status,
                is_approved=is_approved
            )
            db.session.add(new_model)
            db.session.flush()

            # บันทึกพารามิเตอร์การพิมพ์ (Print Settings)
            setting = PrintSetting(
                model_id=new_model.id,
                layer_height=layer_height,
                infill_percentage=infill_percentage,
                supports_required=supports_required
            )
            db.session.add(setting)

            # บันทึกสเปกเส้นพลาสติก (Filament Requirements)
            filament = FilamentRequirement(
                model_id=new_model.id,
                material_type=material_type,
                filament_weight_grams=filament_weight_grams
            )
            db.session.add(filament)
            db.session.commit()

            if is_approved:
                flash(f"เพิ่มโมเดล 3D '{title}' เข้าสู่ตลาดกลางเรียบร้อยแล้ว!", "success")
                return redirect(url_for("index"))
            else:
                flash(f"โพสต์โมเดล '{title}' สำเร็จแล้ว! สินค้าของคุณอยู่ระหว่างรอแอดมินตรวจสอบ ก่อนจะแสดงผลในตลาดกลาง", "info")
                return redirect(url_for("my_models"))

        return render_template("upload_model.html")

    @app.route("/my-models")
    @login_required
    def my_models():
        """
        หน้ารายการโมเดลที่ผู้ใช้คนนี้ลงขายทั้งหมด (My Store Listings)
        - แสดงสถานะการอนุมัติ (รอตรวจสอบ / อนุมัติแล้ว / ปฏิเสธ)
        - มีปุ่มดูรายละเอียดโมเดล และปุ่มลบโมเดลของตนเอง
        """
        models = Model3D.query.filter_by(user_id=current_user.id).order_by(Model3D.created_at.desc()).all()
        return render_template("my_models.html", models=models)

    @app.route("/models/<int:model_id>/delete", methods=["POST"])
    @login_required
    def delete_user_model(model_id):
        """
        ผู้ใช้ลบโมเดล 3D ของตนเองออกจากระบบฐานข้อมูล SQLite (.db)
        - มีการตรวจสอบความเป็นเจ้าของก่อนอนุญาตให้ลบ
        - ลบข้อมูลความสัมพันธ์และไฟล์ที่เกี่ยวข้องทั้งหมดอย่างปลอดภัย
        """
        model = Model3D.query.get_or_404(model_id)
        if model.user_id != current_user.id and not current_user.is_admin:
            flash("คุณไม่มีสิทธิ์ลบรายการสินค้านี้", "danger")
            return redirect(url_for("my_models"))
        title = model.title
        try:
            PrintSetting.query.filter_by(model_id=model.id).delete()
            FilamentRequirement.query.filter_by(model_id=model.id).delete()
            ModelLike.query.filter_by(model_id=model.id).delete()
            ModelPurchase.query.filter_by(model_id=model.id).delete()

            if model.thumbnail_url and "/uploads/" in model.thumbnail_url:
                th_name = os.path.basename(model.thumbnail_url)
                th_path = os.path.join(app.config.get("UPLOAD_FOLDER", "static/uploads"), th_name)
                if os.path.exists(th_path):
                    try:
                        os.remove(th_path)
                    except Exception:
                        pass

            if model.file_path:
                m_fp = os.path.join(app.config["FILES_UPLOAD_FOLDER"], model.file_path)
                if os.path.exists(m_fp):
                    try:
                        os.remove(m_fp)
                    except Exception:
                        pass

            db.session.delete(model)
            db.session.commit()
            flash(f"ลบโมเดล '{title}' ออกจากฐานข้อมูลเรียบร้อยแล้ว", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"เกิดข้อผิดพลาดในการลบโมเดล: {str(e)}", "danger")

        return redirect(request.referrer or url_for("my_models"))

    @app.route("/logout")
    @login_required
    def logout():
        """
        ออกจากระบบ (User Logout)
        - ล้างข้อมูลผู้ใช้ปัจจุบันออกจาก Session และเปลี่ยนเส้นทางไปยังหน้า Login
        """
        logout_user()
        flash("คุณได้ออกจากระบบเรียบร้อยแล้ว", "info")
        return redirect(url_for("login"))

    # ============================================================================
    # ส่วนที่ 10: ระบบผู้ดูแลระบบและตรวจสอบข้อมูล (Admin Panel & Moderation System)
    # ============================================================================
    from functools import wraps

    def admin_required(f):
        """
        Decorator สำหรับตรวจสอบสิทธิ์ผู้ดูแลระบบ (Admin Authorization)
        - ต้องเป็นผู้ใช้ที่ล็อกอินแล้ว (is_authenticated)
        - มีสถานะเป็นแอดมิน (is_admin == True)
        - ต้องเป็นบัญชีทางการ: official@printverse.com เท่านั้น
        - หากไม่มีสิทธิ์ จะถูกส่งกลับไปหน้าตลาดกลางพร้อมข้อความแจ้งเตือน
        """
        @wraps(f)
        def decorated(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.is_admin or current_user.email != "official@printverse.com":
                flash("คุณไม่มีสิทธิ์เข้าถึงหน้านี้ เฉพาะผู้ดูแลระบบ (official@printverse.com) เท่านั้น", "danger")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return decorated

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        """
        แดชบอร์ดภาพรวมของผู้ดูแลระบบ (Admin Overview Dashboard)
        - คำนวณสถิติภาพรวม: จำนวนผู้ใช้งาน, จำนวนโมเดล 3D, จำนวนคำสั่งซื้อ, ยอดรายได้รวม (฿), และคำขอถอนเงิน
        - แสดงรายการคำสั่งซื้อล่าสุด 10 รายการ
        - แสดงรายการสลิปเติมเงิน, รายการขอถอนเงิน, และโมเดลที่รอการตรวจสอบ
        """
        users = User.query.order_by(User.id.asc()).all()
        models = Model3D.query.order_by(Model3D.created_at.desc()).all()
        orders = (ModelPurchase.query
                  .order_by(ModelPurchase.purchased_at.desc()).all())
        topups = (TopupTransaction.query
                  .order_by(TopupTransaction.created_at.desc()).all())
        withdrawals = (WithdrawalTransaction.query
                       .order_by(WithdrawalTransaction.created_at.desc()).all())
        total_users = len(users)
        total_models = len(models)
        total_orders = len(orders)
        total_withdrawals = len(withdrawals)
        total_revenue = sum(o.price_paid for o in orders)

        return render_template("admin/dashboard.html",
                               users=users,
                               models=models,
                               orders=orders,
                               topups=topups,
                               withdrawals=withdrawals,
                               recent_orders=orders[:10],
                               total_users=total_users,
                               total_models=total_models,
                               total_orders=total_orders,
                               total_withdrawals=total_withdrawals,
                               total_revenue=total_revenue)

    # ----------------------------------------------------------------------------
    # การจัดการผู้ใช้งาน (User Management)
    # ----------------------------------------------------------------------------
    @app.route("/admin/users")
    @login_required
    @admin_required
    def admin_users():
        """
        หน้าจัดการรายชื่อผู้ใช้ทั้งหมดในระบบ (User List)
        """
        users = User.query.order_by(User.id.asc()).all()
        return render_template("admin/users.html", users=users)

    @app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def admin_delete_user(user_id):
        """
        แอดมินลบบัญชีผู้ใช้ออกจากระบบฐานข้อมูล
        - ป้องกันไม่ให้ลบบัญชีผู้ดูแลระบบหลัก หรือบัญชีตัวเอง
        - ล้างข้อมูลที่เกี่ยวข้องทั้งหมดอย่างปลอดภัย (โมเดล, ประวัติการซื้อ, ไลค์, สลิป, คำขอถอนเงิน)
        """
        user = User.query.get_or_404(user_id)
        if user.email == "official@printverse.com" or user.id == current_user.id:
            flash("ไม่สามารถลบบัญชีผู้ดูแลระบบหลักหรือตัวเองได้", "danger")
            return redirect(request.referrer or url_for("admin_dashboard"))

        username = user.username

        try:
            # 1. จัดการโมเดลที่ผู้ใช้นี้สร้างขึ้นทั้งหมด
            user_models = Model3D.query.filter_by(user_id=user.id).all()
            for m in user_models:
                PrintSetting.query.filter_by(model_id=m.id).delete()
                FilamentRequirement.query.filter_by(model_id=m.id).delete()
                ModelLike.query.filter_by(model_id=m.id).delete()
                ModelPurchase.query.filter_by(model_id=m.id).delete()

                if m.thumbnail_url and "/uploads/" in m.thumbnail_url:
                    th_name = os.path.basename(m.thumbnail_url)
                    th_path = os.path.join(app.config.get("UPLOAD_FOLDER", "static/uploads"), th_name)
                    if os.path.exists(th_path):
                        try:
                            os.remove(th_path)
                        except Exception:
                            pass

                if m.file_path:
                    m_fp = os.path.join(app.config["FILES_UPLOAD_FOLDER"], m.file_path)
                    if os.path.exists(m_fp):
                        try:
                            os.remove(m_fp)
                        except Exception:
                            pass
                db.session.delete(m)

            # 2. จัดการประวัติการซื้อ (downloads) ของผู้ใช้นี้
            ModelPurchase.query.filter_by(user_id=user.id).delete()

            # 3. จัดการรายการที่ผู้ใช้นี้เป็นคนขาย (seller_id) ให้ตั้งเป็น None เพื่อรักษาประวัติของผู้ซื้อไว้
            ModelPurchase.query.filter_by(seller_id=user.id).update({"seller_id": None})

            # 4. จัดการ Likes ของผู้ใช้นี้
            ModelLike.query.filter_by(user_id=user.id).delete()

            # 5. จัดการ Topup Transactions ของผู้ใช้นี้
            topups = TopupTransaction.query.filter_by(user_id=user.id).all()
            for t in topups:
                if t.slip_image:
                    slip_path = os.path.join(app.config.get("UPLOAD_FOLDER", "static/uploads"), t.slip_image)
                    if os.path.exists(slip_path):
                        try:
                            os.remove(slip_path)
                        except Exception:
                            pass
                db.session.delete(t)

            # 6. จัดการ Withdrawal Transactions ของผู้ใช้นี้
            WithdrawalTransaction.query.filter_by(user_id=user.id).delete()

            # 7. ลบรูป Avatar ของผู้ใช้ถ้ามี
            if user.avatar_url and "/uploads/avatars/" in user.avatar_url:
                av_name = os.path.basename(user.avatar_url)
                av_path = os.path.join(app.config["AVATARS_UPLOAD_FOLDER"], av_name)
                if os.path.exists(av_path):
                    try:
                        os.remove(av_path)
                    except Exception:
                        pass

            # 8. ลบ User
            db.session.delete(user)
            db.session.commit()
            flash(f"ลบผู้ใช้ '{username}' และข้อมูลที่เกี่ยวข้องเรียบร้อยแล้ว", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"เกิดข้อผิดพลาดในการลบผู้ใช้: {str(e)}", "danger")

        return redirect(request.referrer or url_for("admin_dashboard"))

    @app.route("/admin/users/<int:user_id>/toggle_admin", methods=["POST"])
    @login_required
    @admin_required
    def admin_toggle_admin(user_id):
        """
        แต่งตั้งหรือถอดถอนสิทธิ์ Admin ให้กับผู้ใช้รายอื่น
        """
        user = User.query.get_or_404(user_id)
        if user.id == current_user.id:
            flash("ไม่สามารถเปลี่ยนสิทธิ์ของตัวเองได้", "danger")
            return redirect(request.referrer or url_for("admin_dashboard"))
        user.is_admin = not user.is_admin
        db.session.commit()
        status = "เพิ่ม" if user.is_admin else "ถอด"
        flash(f"{status}สิทธิ์ Admin ให้ '{user.username}' เรียบร้อยแล้ว", "success")
        return redirect(request.referrer or url_for("admin_dashboard"))

    # ----------------------------------------------------------------------------
    # API สำหรับระบบแจ้งเตือนรายการรออนุมัติแบบ Real-time (Polling)
    # ----------------------------------------------------------------------------
    @app.route("/api/admin/pending-notifications")
    @login_required
    def api_pending_notifications():
        """
        API ส่งข้อมูลรายการที่รอการตรวจสอบให้ Frontend แจ้งเตือนแอดมิน:
        - pending_models_count: จำนวนโมเดลรอตรวจสอบ
        - pending_topups_count: จำนวนสลิปเติมเงินรอตรวจสอบ
        - pending_withdrawals_count: จำนวนคำขอถอนเงินรอตรวจสอบ
        - total_pending_count: ผลรวมรายการที่ต้องดำเนินการ
        - รายละเอียด 5 รายการล่าสุดสำหรับแสดงผลใน Dropdown เมนูแจ้งเตือน
        """
        if not current_user.is_admin:
            return jsonify({"error": "forbidden"}), 403

        pending_models = Model3D.query.filter(
            (Model3D.status == 'รอการตรวจสอบ') | (Model3D.is_approved == False)
        ).order_by(Model3D.created_at.desc()).all()

        pending_topups = TopupTransaction.query.filter_by(
            status='รอการตรวจสอบ'
        ).order_by(TopupTransaction.created_at.desc()).all()

        pending_withdrawals = WithdrawalTransaction.query.filter_by(
            status='รอการตรวจสอบ'
        ).order_by(WithdrawalTransaction.created_at.desc()).all()

        total_pending_count = len(pending_models) + len(pending_topups) + len(pending_withdrawals)

        return jsonify({
            "pending_models_count": len(pending_models),
            "pending_topups_count": len(pending_topups),
            "pending_withdrawals_count": len(pending_withdrawals),
            "total_pending_count": total_pending_count,
            "pending_models": [
                {
                    "id": m.id,
                    "title": m.title,
                    "author": m.author.username if m.author else "PrintVerse",
                    "price": m.price,
                    "created_at": m.created_at.strftime("%d/%m/%Y %H:%M") if m.created_at else ""
                }
                for m in pending_models[:5]
            ],
            "pending_topups": [
                {
                    "id": t.id,
                    "username": t.user.username,
                    "amount": t.amount,
                    "payment_method": t.payment_method,
                    "created_at": t.created_at.strftime("%d/%m/%Y %H:%M") if t.created_at else ""
                }
                for t in pending_topups[:5]
            ],
            "pending_withdrawals": [
                {
                    "id": w.id,
                    "username": w.user.username,
                    "amount": w.amount,
                    "bank_name": w.bank_name,
                    "account_number": w.account_number,
                    "account_name": w.account_name,
                    "created_at": w.created_at.strftime("%d/%m/%Y %H:%M") if w.created_at else ""
                }
                for w in pending_withdrawals[:5]
            ]
        })

    # ----------------------------------------------------------------------------
    # การจัดการและตรวจสอบโมเดล 3D (Model Moderation)
    # ----------------------------------------------------------------------------
    @app.route("/admin/models")
    @login_required
    @admin_required
    def admin_models():
        """
        หน้าตรวจสอบและจัดการโมเดล 3D ทั้งหมดในระบบ
        """
        models = Model3D.query.order_by(Model3D.created_at.desc()).all()
        return render_template("admin/models.html", models=models)

    @app.route("/admin/models/<int:model_id>/approve", methods=["POST"])
    @login_required
    @admin_required
    def admin_approve_model(model_id):
        """
        อนุมัติโมเดล 3D เข้าสู่ตลาดกลาง (is_approved=True, status='อนุมัติแล้ว')
        - สินค้าจะเริ่มปรากฏให้ผู้ใช้งานทั่วไปมองเห็นและสั่งซื้อได้ทันที
        """
        model = Model3D.query.get_or_404(model_id)
        model.is_approved = True
        model.status = "อนุมัติแล้ว"
        db.session.commit()
        flash(f"อนุมัติโมเดล '{model.title}' เข้าสู่ตลาดกลางเรียบร้อยแล้ว!", "success")
        return redirect(request.referrer or url_for("admin_models"))

    @app.route("/admin/models/<int:model_id>/reject", methods=["POST"])
    @login_required
    @admin_required
    def admin_reject_model(model_id):
        """
        ปฏิเสธหรือพักการวางจำหน่ายโมเดล 3D (is_approved=False, status='ปฏิเสธ')
        - สินค้าจะถูกซ่อนออกจากตลาดกลาง
        """
        model = Model3D.query.get_or_404(model_id)
        model.is_approved = False
        model.status = "ปฏิเสธ"
        db.session.commit()
        flash(f"ปฏิเสธโมเดล '{model.title}' เรียบร้อยแล้ว", "warning")
        return redirect(request.referrer or url_for("admin_models"))

    @app.route("/admin/models/<int:model_id>/delete", methods=["POST"])
    @app.route("/admin/delete_model/<int:model_id>", methods=["POST"])
    @login_required
    @admin_required
    def admin_delete_model(model_id):
        """
        ลบโมเดล 3D ออกจากฐานข้อมูล (.db) ถาวร พร้อมลบข้อมูลความสัมพันธ์และไฟล์ที่เกี่ยวข้อง
        """
        model = Model3D.query.get_or_404(model_id)
        title = model.title
        try:
            PrintSetting.query.filter_by(model_id=model.id).delete()
            FilamentRequirement.query.filter_by(model_id=model.id).delete()
            ModelLike.query.filter_by(model_id=model.id).delete()
            ModelPurchase.query.filter_by(model_id=model.id).delete()

            if model.thumbnail_url and "/uploads/" in model.thumbnail_url:
                th_name = os.path.basename(model.thumbnail_url)
                th_path = os.path.join(app.config.get("UPLOAD_FOLDER", "static/uploads"), th_name)
                if os.path.exists(th_path):
                    try:
                        os.remove(th_path)
                    except Exception:
                        pass

            if model.file_path:
                m_fp = os.path.join(app.config["FILES_UPLOAD_FOLDER"], model.file_path)
                if os.path.exists(m_fp):
                    try:
                        os.remove(m_fp)
                    except Exception:
                        pass

            db.session.delete(model)
            db.session.commit()
            flash(f"ลบโมเดล '{title}' ออกจากฐานข้อมูล (.db) เรียบร้อยแล้ว", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"เกิดข้อผิดพลาดในการลบโมเดล: {str(e)}", "danger")

        return redirect(request.referrer or url_for("admin_dashboard"))

    # ----------------------------------------------------------------------------
    # การจัดการประวัติคำสั่งซื้อ (Order History Management)
    # ----------------------------------------------------------------------------
    @app.route("/admin/orders")
    @login_required
    @admin_required
    def admin_orders():
        """
        หน้าตรวจสอบประวัติคำสั่งซื้อและรายการดาวน์โหลดทั้งหมด
        """
        orders = (ModelPurchase.query
                  .order_by(ModelPurchase.purchased_at.desc()).all())
        return render_template("admin/orders.html", orders=orders)

    @app.route("/admin/orders/<int:order_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def admin_delete_order(order_id):
        """
        ลบรายการประวัติคำสั่งซื้อออกจากระบบ
        """
        order = ModelPurchase.query.get_or_404(order_id)
        try:
            db.session.delete(order)
            db.session.commit()
            flash("ลบรายการสั่งซื้อเรียบร้อยแล้ว", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"เกิดข้อผิดพลาดในการลบรายการสั่งซื้อ: {str(e)}", "danger")

        return redirect(request.referrer or url_for("admin_dashboard"))

    # ----------------------------------------------------------------------------
    # การตรวจสอบสลิปและอนุมัติการเติมเงิน (Top-up Slip Verification & Approval)
    # ----------------------------------------------------------------------------
    @app.route("/admin/topups")
    @login_required
    @admin_required
    def admin_topups():
        """
        หน้ารายการสลิปเติมเงินทั้งหมด เพื่อให้แอดมินตรวจสอบความถูกต้อง
        """
        topups = (TopupTransaction.query
                  .order_by(TopupTransaction.created_at.desc()).all())
        return render_template("admin/topups.html", topups=topups)

    @app.route("/admin/topups/<int:topup_id>/approve", methods=["POST"])
    @login_required
    @admin_required
    def admin_approve_topup(topup_id):
        """
        แอดมินกดยืนยันอนุมัติสลิปการเติมเงิน (เมื่อตรวจแล้วว่าเงินเข้าจริง)
        - เปลี่ยนสถานะรายการเป็น 'สำเร็จ'
        - เพิ่มยอดเงินเข้ากระเป๋า (Wallet Balance) ของผู้ใช้ทันที
        """
        topup_tx = TopupTransaction.query.get_or_404(topup_id)
        if topup_tx.status != "สำเร็จ":
            topup_tx.status = "สำเร็จ"
            topup_tx.user.wallet_balance += topup_tx.net_amount
            db.session.commit()
            flash(f"อนุมัติยอดเติมเงิน #TOP-{topup_tx.id:04d} ยอดโอน ฿{topup_tx.amount:,.2f} (ฟรีค่าธรรมเนียม 0%) เพิ่มเงินเข้ากระเป๋าผู้ใช้ '{topup_tx.user.username}' เต็มจำนวน ฿{topup_tx.net_amount:,.2f} สำเร็จ!", "success")
        else:
            flash("รายการนี้ได้รับการอนุมัติไปแล้ว", "info")
        return redirect(request.referrer or url_for("admin_topups"))

    @app.route("/admin/topups/<int:topup_id>/reject", methods=["POST"])
    @login_required
    @admin_required
    def admin_reject_topup(topup_id):
        """
        แอดมินปฏิเสธสลิปการเติมเงิน (เช่น ยอดไม่ตรง, สลิปปลอม, เวลาไม่ตรง)
        - เปลี่ยนสถานะเป็น 'ปฏิเสธ'
        - หากรายการเคยสำเร็จมาก่อน จะดึงยอดเงินออกจากกระเป๋าคืน
        """
        topup_tx = TopupTransaction.query.get_or_404(topup_id)
        if topup_tx.status == "สำเร็จ":
            topup_tx.user.wallet_balance = max(0.0, topup_tx.user.wallet_balance - topup_tx.net_amount)
        topup_tx.status = "ปฏิเสธ"
        db.session.commit()
        flash(f"ปฏิเสธรายการเติมเงิน #TOP-{topup_tx.id:04d} เรียบร้อยแล้ว", "warning")
        return redirect(request.referrer or url_for("admin_topups"))

    @app.route("/admin/topups/<int:topup_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def admin_delete_topup(topup_id):
        """
        ลบรายการสลิปเติมเงินและลบไฟล์ภาพสลิปออกจากดิสก์ถาวร
        """
        topup_tx = TopupTransaction.query.get_or_404(topup_id)
        try:
            slip_path = os.path.join(app.config["UPLOAD_FOLDER"], topup_tx.slip_image)
            if os.path.exists(slip_path):
                try:
                    os.remove(slip_path)
                except Exception:
                    pass
            db.session.delete(topup_tx)
            db.session.commit()
            flash("ลบรายการประวัติการเติมเงินเรียบร้อยแล้ว", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"เกิดข้อผิดพลาดในการลบรายการเติมเงิน: {str(e)}", "danger")

        return redirect(request.referrer or url_for("admin_topups"))

    # ----------------------------------------------------------------------------
    # การตรวจสอบและอนุมัติการถอนเงิน (Withdrawal Requests Moderation)
    # ----------------------------------------------------------------------------
    @app.route("/admin/withdrawals")
    @login_required
    @admin_required
    def admin_withdrawals():
        """
        หน้ารายการคำขอถอนเงินทั้งหมดเพื่อให้แอดมินตรวจสอบและโอนเงินให้สมาชิก
        """
        withdrawals = (WithdrawalTransaction.query
                       .order_by(WithdrawalTransaction.created_at.desc()).all())
        return render_template("admin/withdrawals.html", withdrawals=withdrawals)

    @app.route("/admin/withdrawals/<int:tx_id>/approve", methods=["POST"])
    @login_required
    @admin_required
    def admin_approve_withdrawal(tx_id):
        """
        แอดมินยืนยันว่าได้โอนเงินเข้าบัญชีของผู้ใช้เรียบร้อยแล้ว
        """
        tx = WithdrawalTransaction.query.get_or_404(tx_id)
        admin_note = request.form.get("admin_note", "").strip()
        tx.status = "สำเร็จ"
        tx.processed_at = datetime.utcnow()
        if admin_note:
            tx.admin_note = admin_note
        db.session.commit()
        flash(f"อนุมัติคำขอถอนเงิน #WD-{tx.id:04d} ยอดขอถอน ฿{tx.amount:,.2f} (หักค่าบริการ 1% ฿{tx.fee:,.2f}) โอนเงินให้ '{tx.user.username}' สุทธิ ฿{tx.net_amount:,.2f} เข้า {tx.bank_name} ({tx.account_number}) สำเร็จ!", "success")
        return redirect(request.referrer or url_for("admin_withdrawals"))

    @app.route("/admin/withdrawals/<int:tx_id>/reject", methods=["POST"])
    @login_required
    @admin_required
    def admin_reject_withdrawal(tx_id):
        """
        แอดมินปฏิเสธคำขอถอนเงิน และคืนเงินเข้ากระเป๋า Wallet ให้ผู้ใช้
        """
        tx = WithdrawalTransaction.query.get_or_404(tx_id)
        admin_note = request.form.get("admin_note", "").strip() or "ข้อมูลบัญชีไม่ถูกต้อง หรือไม่สามารถโอนเงินได้"
        
        # คืนเงินเข้ากระเป๋าผู้ใช้หากเคยถูกหักไว้
        if tx.status == "รอการตรวจสอบ":
            tx.user.wallet_balance += tx.amount
        
        tx.status = "ปฏิเสธ"
        tx.admin_note = admin_note
        tx.processed_at = datetime.utcnow()
        db.session.commit()
        flash(f"ปฏิเสธคำขอถอนเงิน #WD-{tx.id:04d} และคืนเงินจำนวน ฿{tx.amount:,.2f} เข้ากระเป๋าของผู้ใช้เรียบร้อยแล้ว", "warning")
        return redirect(request.referrer or url_for("admin_withdrawals"))

    @app.route("/admin/withdrawals/<int:tx_id>/delete", methods=["POST"])
    @login_required
    @admin_required
    def admin_delete_withdrawal(tx_id):
        """
        ลบประวัติคำขอถอนเงินออกจากระบบ
        """
        tx = WithdrawalTransaction.query.get_or_404(tx_id)
        try:
            # หากอยู่ในสถานะรอตรวจสอบ ต้องคืนเงินก่อนลบ
            if tx.status == "รอการตรวจสอบ" and tx.user:
                tx.user.wallet_balance += tx.amount
            db.session.delete(tx)
            db.session.commit()
            flash("ลบรายการประวัติการถอนเงินเรียบร้อยแล้ว", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"เกิดข้อผิดพลาดในการลบรายการถอนเงิน: {str(e)}", "danger")

        return redirect(request.referrer or url_for("admin_withdrawals"))


    # ============================================================================
    # ส่วนที่ 11: การจัดการข้อผิดพลาด (Error Handling)
    # ============================================================================

    @app.errorhandler(403)
    def forbidden(e):
        """จัดการกรณีผู้ใช้พยายามเข้าถึงหน้าที่ไม่มีสิทธิ์ (HTTP 403 Forbidden)"""
        flash("คุณไม่มีสิทธิ์เข้าถึงหน้านี้ เฉพาะผู้ดูแลระบบ (official@printverse.com) เท่านั้น", "danger")
        return redirect(url_for("index"))

    return app


# ================================================================================
# ส่วนที่ 12: จุดเริ่มต้นรันเซิร์ฟเวอร์ (Application Entry Point)
# ================================================================================

if __name__ == "__main__":
    # สร้างแอปพลิเคชัน Flask
    app = create_app()
    # รันเว็บเซิร์ฟเวอร์ในโหมด Debug, เปิดรับการเชื่อมต่อจากทุกเครือข่าย (0.0.0.0), พอร์ต 5000
    app.run(debug=True, host="0.0.0.0", port=5000, threaded=True)
