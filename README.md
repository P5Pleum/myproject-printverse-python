# 3D Print Models Marketplace (Phase 1)

โปรเจกต์เว็บแอปพลิเคชันตลาดซื้อขายและแจกฟรีไฟล์โมเดล 3 มิติ (.STL, .OBJ, .3MF, .STEP) พัฒนาด้วย Python Flask, SQLAlchemy, SQLite และ Tailwind CSS (CDN)

---

## วิธีเปิดใช้งานใน VS Code

### 1. เปิดโฟลเดอร์นี้ใน VS Code
- เปิด VS Code
- ไปที่เมนู `File` > `Open Folder...`
- เลือกโฟลเดอร์นี้ (`threed_print_marketplace`)

### 2. สร้างและเปิดใช้งาน Virtual Environment
เปิด Terminal ใน VS Code (`Ctrl` + `~`):
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. ติดตั้ง Dependencies
```powershell
pip install -r requirements.txt
```

### 4. รันเซิร์ฟเวอร์
```powershell
python app.py
```

เมื่อรันแล้ว:
- ระบบจะสร้างไฟล์ฐานข้อมูล `instance/marketplace.db` ให้อัตโนมัติ
- เปิดเบราว์เซอร์ไปที่: `http://127.0.0.1:5000`
