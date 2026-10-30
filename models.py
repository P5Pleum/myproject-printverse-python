from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone_number = db.Column(db.String(20), nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Maker Profile & Community Ecosystem
    avatar_url = db.Column(db.String(255), nullable=True)  # รูปโปรไฟล์ผู้ใช้ (ไฟล์อัปโหลด หรือภาพถ่ายจากกล้อง)
    address = db.Column(db.Text, nullable=True)  # ที่อยู่สำหรับจัดส่งและติดต่อ
    email_verified = db.Column(db.Boolean, default=False)  # สถานะยืนยันอีเมลจริงผ่าน OTP
    maker_badge = db.Column(db.String(50), default="Hobbyist Maker")  # e.g., Hobbyist, Pro Designer, Print Master
    wallet_balance = db.Column(db.Float, default=0.00)  # ยอดเงินเริ่มต้น 0.00 THB ต้องเติมเงินเท่านั้น
    bio = db.Column(db.String(300), default="3D Printing enthusiast & CAD designer.")
    printer_setup = db.Column(db.String(150), default="Bambu Lab X1-Carbon / Ender 3 V3")

    # Relationships
    models = db.relationship("Model3D", backref="author", lazy="dynamic", cascade="all, delete-orphan")
    downloads = db.relationship("ModelPurchase", foreign_keys="ModelPurchase.user_id", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    sales = db.relationship("ModelPurchase", foreign_keys="ModelPurchase.seller_id", backref="seller", lazy="dynamic")
    likes = db.relationship("ModelLike", backref="user", lazy="dynamic", cascade="all, delete-orphan")
    withdrawals = db.relationship("WithdrawalTransaction", backref="user", lazy="dynamic", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Model3D(db.Model):
    """3D Model entity สำหรับเก็บข้อมูลโมเดลและการพิมพ์ 3 มิติ"""
    __tablename__ = "models_3d"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category = db.Column(db.String(50), default="Gadgets & Tools")
    
    # Pricing: 0.0 = Free Download, >0 = Commercial/Paid
    price = db.Column(db.Float, default=0.0)
    is_free = db.Column(db.Boolean, default=True)

    # 3D File Specifications
    primary_format = db.Column(db.String(10), nullable=False)  # STL, 3MF, OBJ, STEP
    supported_formats = db.Column(db.String(100), default="STL, 3MF")
    file_size_mb = db.Column(db.Float, default=0.0)
    download_count = db.Column(db.Integer, default=0)
    likes_count = db.Column(db.Integer, default=0)

    # Media, Files & Timestamps
    thumbnail_url = db.Column(db.String(255), nullable=True)
    file_path = db.Column(db.String(255), nullable=True)  # ชื่อไฟล์โมเดลจริงใน static/uploads/files/
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    # Moderation & Approval Status
    status = db.Column(db.String(30), default="รอการตรวจสอบ")  # 'รอการตรวจสอบ', 'อนุมัติแล้ว', 'ปฏิเสธ'
    is_approved = db.Column(db.Boolean, default=False)

    # 3D Print Configurations
    print_setting = db.relationship("PrintSetting", backref="model", uselist=False, cascade="all, delete-orphan")
    filament_info = db.relationship("FilamentRequirement", backref="model", uselist=False, cascade="all, delete-orphan")
    purchases = db.relationship("ModelPurchase", backref="model", cascade="all, delete-orphan")
    likes_list = db.relationship("ModelLike", backref="model", cascade="all, delete-orphan", lazy="dynamic")


class PrintSetting(db.Model):
    """ค่า Parameter การ Slice และการพิมพ์สำหรับโมเดล"""
    __tablename__ = "print_settings"

    id = db.Column(db.Integer, primary_key=True)
    model_id = db.Column(db.Integer, db.ForeignKey("models_3d.id"), nullable=False)
    
    layer_height = db.Column(db.String(20), default="0.20 mm (Standard)")
    infill_percentage = db.Column(db.Integer, default=20)  # e.g., 20%
    infill_pattern = db.Column(db.String(50), default="Gyroid")
    supports_required = db.Column(db.Boolean, default=False)
    support_type = db.Column(db.String(50), default="Tree / Organic")
    print_time_estimate = db.Column(db.String(50), default="3h 45m")
    recommended_nozzle_temp = db.Column(db.Integer, default=215)  # °C
    recommended_bed_temp = db.Column(db.Integer, default=60)      # °C


class FilamentRequirement(db.Model):
    """ปริมาณวัสดุและเส้นพลาสติกที่ใช้ในการพิมพ์"""
    __tablename__ = "filament_requirements"

    id = db.Column(db.Integer, primary_key=True)
    model_id = db.Column(db.Integer, db.ForeignKey("models_3d.id"), nullable=False)

    material_type = db.Column(db.String(50), default="PLA / PETG") # PLA, PETG, ABS, ASA, TPU, Resin
    filament_weight_grams = db.Column(db.Float, default=85.0)     # กรัม
    filament_length_meters = db.Column(db.Float, default=28.5)    # เมตร
    color_suggested = db.Column(db.String(50), default="Matte Black / Orange")


class ModelPurchase(db.Model):
    """ประวัติการซื้อหรือดาวน์โหลดไฟล์งานพิมพ์ และรายได้ของคนโพสต์ขาย"""
    __tablename__ = "model_purchases"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False) # ผู้ซื้อ
    model_id = db.Column(db.Integer, db.ForeignKey("models_3d.id", ondelete="CASCADE"), nullable=False)
    price_paid = db.Column(db.Float, default=0.0) # ราคาที่ผู้ซื้อจ่าย
    seller_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True) # ผู้สร้าง/คนขายที่ได้รับเงิน
    seller_income = db.Column(db.Float, default=0.0) # รายได้ที่โอนเข้ากระเป๋าคนขาย
    purchased_at = db.Column(db.DateTime, default=datetime.utcnow)


class ModelLike(db.Model):
    """รายการกดถูกใจโมเดล 3D ของผู้ใช้งาน"""
    __tablename__ = "model_likes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    model_id = db.Column(db.Integer, db.ForeignKey("models_3d.id", ondelete="CASCADE"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("user_id", "model_id", name="uq_user_model_like"),)


class TopupTransaction(db.Model):
    """ประวัติการแจ้งเติมเงินและสลิปการโอนเงิน (Mobile Banking / TrueMoney)"""
    __tablename__ = "topup_transactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)  # 'Mobile Banking (PromptPay QR)' หรือ 'TrueMoney Wallet'
    sender_phone = db.Column(db.String(30), nullable=False)    # เบอร์ที่ใช้โอน หรือ ธนาคารต้นทาง
    transfer_time = db.Column(db.String(60), nullable=False)   # วันเวลาที่โอน
    slip_image = db.Column(db.String(255), nullable=False)     # ชื่อไฟล์สลิป
    status = db.Column(db.String(30), default="รอการตรวจสอบ")   # 'รอการตรวจสอบ', 'สำเร็จ', 'ปฏิเสธ'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("topups", lazy="dynamic", cascade="all, delete-orphan"))

    @property
    def fee(self):
        """ไม่มีค่าธรรมเนียมสำหรับการเติมเงิน (ฟรี 0%)"""
        return 0.0

    @property
    def net_amount(self):
        """ยอดเงินสุทธิที่จะเข้ากระเป๋า Wallet (เติมเท่าไหร่ ได้เต็มจำนวน 100%)"""
        return round(self.amount, 2)


class WithdrawalTransaction(db.Model):
    """ประวัติและคำขอถอนเงินออกจากกระเป๋า Wallet กลับเข้าบัญชีผู้ใช้"""
    __tablename__ = "withdrawal_transactions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    bank_name = db.Column(db.String(50), nullable=False)       # ธนาคารกสิกรไทย, พร้อมเพย์, ฯลฯ
    account_number = db.Column(db.String(50), nullable=False)  # เลขบัญชี หรือ เบอร์พร้อมเพย์
    account_name = db.Column(db.String(100), nullable=False)   # ชื่อเจ้าของบัญชี
    status = db.Column(db.String(30), default="รอการตรวจสอบ")   # 'รอการตรวจสอบ', 'สำเร็จ', 'ปฏิเสธ'
    admin_note = db.Column(db.String(255), nullable=True)      # บันทึกจากแอดมิน (เช่น รหัสอ้างอิงโอนเงิน)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime, nullable=True)

    @property
    def fee(self):
        """ค่าบริการระบบ 1% สำหรับการถอนเงิน"""
        return round(self.amount * 0.01, 2)

    @property
    def net_amount(self):
        """ยอดเงินสุทธิที่จะโอนเข้าบัญชีผู้ใช้ (หักค่าบริการ 1% แล้ว)"""
        return round(self.amount - self.fee, 2)


class EmailOTP(db.Model):
    """รหัส OTP สำหรับยืนยันอีเมลจริงก่อนสมัครสมาชิกหรือทำธุรกรรม"""
    __tablename__ = "email_otps"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    otp_code = db.Column(db.String(6), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_used = db.Column(db.Boolean, default=False)

