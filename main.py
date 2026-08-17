
from fastapi import FastAPI, HTTPException, Depends, Request, Query, Header, UploadFile, File, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, List, Dict, Any
import uvicorn
from typing import Optional, List, Dict, Set
import os

from pathlib import Path
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import (
    inspect, text, create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Float
)
from sqlalchemy.orm import sessionmaker, declarative_base, Session, relationship

from passlib.context import CryptContext
from jose import jwt, JWTError

from datetime import datetime, timedelta, date, timezone
from zoneinfo import ZoneInfo
import random
import requests as http_requests

try:
    VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
except Exception:
    VN_TZ = timezone(timedelta(hours=7))

def now_vn():
    return datetime.now(VN_TZ).replace(tzinfo=None)

# Sử dụng 3 dấu xuyệt (/) sau sqlite: và đường dẫn dùng dấu xuyệt xuôi (/)

# Thay thế cho dòng bị lỗi
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)


# --- Lên đầu file, dưới các dòng import, thêm 2 dòng này ---
BANNED_LOGIN_MESSAGE = "Tài khoản của bạn đã bị cấm. Vui lòng liên hệ Admin!"
class LoginRequest(BaseModel):
    email: str
    password: str
# ===================== CONFIG =====================
# --- Sửa lại cấu hình DATABASE để chạy được trên Render ---
raw_db_url = os.getenv("DATABASE_URL", "sqlite:///./app.db")
if raw_db_url.startswith("postgres://"):
    DATABASE_URL = raw_db_url.replace("postgres://", "postgresql+psycopg2://", 1)
else:
    DATABASE_URL = raw_db_url

SECRET_KEY = os.getenv("SECRET_KEY", "SUPER_SECRET_KEY_CHANGE_LATER")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Gán trực tiếp email và password bạn muốn dùng
ADMIN_EMAIL = "admin@gmail.com"
ADMIN_PASSWORD = "admin123"

# ===================== EMAIL / OTP CONFIG =====================
# QUAN TRỌNG: KHÔNG để cứng App Password trong code khi đẩy lên GitHub công khai.
# Vào Render -> Environment -> thêm 2 biến EMAIL_SENDER và EMAIL_APP_PASSWORD với
# giá trị thật, rồi XOÁ 2 giá trị mặc định bên dưới (hoặc để trống).
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
EMAIL_SENDER   = os.getenv("EMAIL_SENDER", "truonghonganh.shop@gmail.com")
SENDER_NAME    = "Shop Truong Hong Anh"

OTP_EXPIRE_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 30

# Lưu tạm thông tin đăng ký chờ xác thực OTP (email -> dict)
# Lưu ý: đây là bộ nhớ RAM, nếu server restart thì các đăng ký đang chờ sẽ mất
# (không ảnh hưởng user đã xác thực xong, vì họ đã được lưu vào DB thật).
PENDING_REGISTRATIONS: Dict[str, Dict[str, Any]] = {}
PENDING_RESETS: Dict[str, Dict[str, Any]] = {}  # Quên mật khẩu


def generate_otp_code() -> str:
    return f"{random.randint(0, 999999):06d}"


def send_otp_email(to_email: str, otp_code: str):
    """Gui OTP qua Brevo API HTTPS - Render khong chan cong 443."""
    if not BREVO_API_KEY:
        raise HTTPException(status_code=500, detail="Chua cau hinh BREVO_API_KEY tren Render!")

    html_body = (
        "<div style='font-family:Arial,sans-serif;max-width:480px;margin:auto;"
        "background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.10)'>"
        "<div style='background:linear-gradient(135deg,#f97316,#ea580c);padding:28px 32px'>"
        "<h2 style='color:#fff;margin:0;font-size:22px'>Shop Truong Hong Anh</h2>"
        "<p style='color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:14px'>Xac thuc tai khoan dang ky</p>"
        "</div>"
        "<div style='padding:32px'>"
        "<p style='color:#374151;font-size:15px'>Xin chao! Ma OTP xac thuc cua ban la:</p>"
        "<div style='text-align:center;margin:24px 0'>"
        f"<span style='font-size:40px;font-weight:700;letter-spacing:10px;color:#f97316;"
        f"background:#fff7ed;padding:16px 24px;border-radius:12px;border:2px dashed #fed7aa'>{otp_code}</span>"
        "</div>"
        f"<p style='color:#6b7280;font-size:13px;text-align:center'>Ma co hieu luc trong <b>{OTP_EXPIRE_MINUTES} phut</b></p>"
        "<p style='color:#ef4444;font-size:12px;text-align:center;margin-top:8px'>Khong chia se ma nay cho bat ky ai!</p>"
        "</div>"
        "<div style='background:#f9fafb;padding:16px 32px;text-align:center'>"
        "<p style='color:#9ca3af;font-size:12px;margin:0'>2025 Shop Truong Hong Anh</p>"
        "</div></div>"
    )

    brevo_payload = {
        "sender": {"name": SENDER_NAME, "email": EMAIL_SENDER},
        "to": [{"email": to_email}],
        "subject": "Ma OTP xac thuc - Shop Truong Hong Anh",
        "htmlContent": html_body
    }
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }
    try:
        res = http_requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=brevo_payload,
            headers=headers,
            timeout=12
        )
        if res.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail=f"Brevo loi {res.status_code}: {res.text[:200]}")
    except http_requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Khong gui duoc email OTP: {str(e)}")

def send_order_confirmation_email(to_email: str, order_id: int, items: list, total: int):
    if not BREVO_API_KEY:
        return  # không chặn luồng tạo đơn nếu thiếu config email
    rows_html = "".join(
        f"<tr><td style='padding:8px'>{it['name']}</td>"
        f"<td style='padding:8px;text-align:center'>{it['quantity']}</td>"
        f"<td style='padding:8px;text-align:right'>{it['unit_price']:,}đ</td></tr>"
        for it in items
    )
    html_body = (
        "<div style='font-family:Arial,sans-serif;max-width:520px;margin:auto'>"
        f"<h2>Đơn hàng #{order_id} đã được xác nhận!</h2>"
        f"<table style='width:100%;border-collapse:collapse'>{rows_html}</table>"
        f"<p style='font-weight:700;text-align:right;margin-top:12px'>Tổng: {total:,}đ</p>"
        "<p>Cảm ơn bạn đã mua hàng tại Shop Trương Hồng Anh!</p></div>"
    )
    brevo_payload = {
        "sender": {"name": SENDER_NAME, "email": EMAIL_SENDER},
        "to": [{"email": to_email}],
        "subject": f"Xác nhận đơn hàng #{order_id} - Shop Trương Hồng Anh",
        "htmlContent": html_body,
    }
    headers = {"accept": "application/json", "api-key": BREVO_API_KEY, "content-type": "application/json"}
    try:
        http_requests.post("https://api.brevo.com/v3/smtp/email", json=brevo_payload, headers=headers, timeout=12)
    except Exception as e:
        print(f">>> [LỖI GỬI EMAIL ĐƠN HÀNG]: {e}")

# Roles / Status
ROLE_USER = "USER"
ROLE_STAFF = "STAFF"
ROLE_ADMIN = "ADMIN"

STATUS_ACTIVE = "ACTIVE"
STATUS_BANNED = "BANNED"

# Order statuses
ORDER_NEW = "NEW"
ORDER_CONFIRMED = "CONFIRMED"
ORDER_SHIPPED = "SHIPPED"
ORDER_DONE = "DONE"
ORDER_CANCELED = "CANCELED"
ORDER_STATUSES: Set[str] = {ORDER_NEW, ORDER_CONFIRMED, ORDER_SHIPPED, ORDER_DONE, ORDER_CANCELED}

app = FastAPI(
    title="May Chu Shop Truong Hong Anh ",
    docs_url="/api-docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# CORS (dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===================== STATIC (serve HTML) =====================

from fastapi.responses import FileResponse
from pathlib import Path

# Xác định thư mục gốc của dự án
BASE_DIR = Path(__file__).resolve().parent

# 1. Phải có dòng này để Server biết chỗ tìm ảnh
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# 2. Định nghĩa các đường dẫn (Route)
@app.get("/")
def read_root():
    file_path = os.path.join(os.getcwd(), "templates", "shop_3_2.html")
    return FileResponse(file_path)

@app.get("/login")
def login_p():
    return FileResponse(str(BASE_DIR / "templates" / "login.html"))

@app.get("/register")
def reg_p():
    return FileResponse(str(BASE_DIR / "templates" / "register.html"))

@app.get("/verify-otp")
def verify_otp_p():
    return FileResponse(str(BASE_DIR / "templates" / "verify-otp.html"))

@app.get("/admin")
def admin_p():
    return FileResponse(str(BASE_DIR / "templates" / "admin.html"))

@app.get("/shop", response_class=HTMLResponse)
async def shop_p():
    # Đưa về cách đơn giản nhất: Chỉ trả về file, không truyền request, không dùng TemplateResponse
    file_path = os.path.join(os.getcwd(), "templates", "shop_3_2.html")
    return FileResponse(file_path)

# --- Tìm và sửa đoạn này trong file main.py của bạn ---

# Tìm và thay thế toàn bộ đoạn liên quan đến order-history bằng đoạn này:
@app.get("/order-history.html", response_class=HTMLResponse)
async def get_order_history_page():
    # Sử dụng Path để tìm đường dẫn chính xác tuyệt đối
    base_path = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(base_path, "templates", "order-history.html")
    
    if os.path.exists(file_path):
        return FileResponse(file_path)
    else:
        return HTMLResponse(content=f"Lỗi: Không tìm thấy file tại {file_path}", status_code=404)

# ------------------------------------------------------

# (Tuỳ chọn) nếu bạn muốn có staff.html thì tạo trong static/
@app.get("/staff")
def page_staff():
    staff_file = STATIC_DIR = Path(__file__).parent / "static"
    if staff_file.exists():
        return FileResponse(staff_file)
    return {"message": "Optional: create static/staff.html to use staff UI."}


# --- DÙNG DATABASE_URL từ ENV (PostgreSQL trên Render hoặc SQLite local) ---
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Tự động tạo bảng mỗi khi khởi động (Dữ liệu sẽ mới tinh)
Base.metadata.create_all(bind=engine)

# ===================== PASSWORD =====================
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def ensure_password_ok(pw: str):
    # bcrypt giới hạn 72 bytes
    if len(pw.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Mật khẩu quá dài (tối đa 72 bytes)")


def hash_password(pw: str) -> str:
    pw_safe = pw.encode("utf-8")[:72].decode("utf-8", errors="ignore")
    return pwd_context.hash(pw_safe)


def verify_password(pw: str, hashed: str) -> bool:
    pw_safe = pw.encode("utf-8")[:72].decode("utf-8", errors="ignore")
    return pwd_context.verify(pw_safe, hashed)


# ===================== JWT =====================
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def create_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


# ===================== MODELS =====================
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)

    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)

    role = Column(String, default=ROLE_USER)         # USER/STAFF/ADMIN
    status = Column(String, default=STATUS_ACTIVE)   # ACTIVE/BANNED
    created_at = Column(DateTime, default=datetime.utcnow)

    orders = relationship("Order", back_populates="user")


class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)

    name = Column(String, index=True, nullable=False)
    price = Column(Integer, nullable=False)          # VND
    stock = Column(Integer, default=0)
    description = Column(String, default="")
    image_url = Column(String, default="")
    is_active = Column(Boolean, default=True)

    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    category = relationship("Category", back_populates="products")

    created_at = Column(DateTime, default=datetime.utcnow)


class Coupon(Base):
    __tablename__ = "coupons"
    id = Column(Integer, primary_key=True)
    code = Column(String, unique=True, index=True, nullable=False)
    label = Column(String, default="")
    discount_type = Column(String, default="percent")  # "percent" hoặc "fixed"
    discount_value = Column(Integer, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now_vn)


class FlashSale(Base):
    __tablename__ = "flash_sales"
    id = Column(Integer, primary_key=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    sale_price = Column(Integer, nullable=False)   # giá sale, VND
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now_vn)

    product = relationship("Product")


class ProductEmbedding(Base):
    """Lưu vector đặc trưng (CLIP embedding) của ảnh sản phẩm, dùng để tìm kiếm bằng ảnh."""
    __tablename__ = "product_embeddings"
    product_id = Column(Integer, ForeignKey("products.id"), primary_key=True)
    vector = Column(Text, nullable=False)          # JSON-encoded list[float], đã chuẩn hoá (L2-normalized)
    image_url = Column(String, default="")          # ảnh đã dùng để encode, để biết khi nào cần encode lại
    updated_at = Column(DateTime, default=now_vn)


# Tìm đến phần Schema (BaseModel) và sửa lại cho chuẩn:
class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int
    unit_price: float

class OrderCreate(BaseModel):
    items: List[OrderItemCreate]
    shipping_address: str
    phone_number: str


# 1. Định nghĩa sẵn các trạng thái để dùng cho đồng bộ
ORDER_NEW = "Chờ xác nhận"
ORDER_CONFIRMED = "Đã xác nhận"
ORDER_SHIPPING = "Đang giao"
ORDER_COMPLETED = "Đã giao"
ORDER_CANCELLED = "Đã hủy"

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # --- THÔNG TIN THÊM CHO ADMIN ---
    shipping_address = Column(Text, nullable=True, default="") # Địa chỉ nhận hàng
    phone_number = Column(String(15), nullable=True, default="") # Số điện thoại khách
    note = Column(String(255), nullable=True) # Ghi chú của khách (nếu có)
    
    # --- TRẠNG THÁI ---
    status = Column(String, default=ORDER_NEW)

    # --- THỜI GIAN (Dùng datetime.now thay vì utcnow cho dễ theo dõi giờ VN) ---
    created_at = Column(DateTime, default=now_vn)
    updated_at = Column(DateTime, default=now_vn, onupdate=now_vn)

    # Quan hệ
    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")

class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True, index=True)

    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)

    quantity = Column(Integer, nullable=False)
    unit_price = Column(Integer, nullable=False) # Giá lúc mua (để sau này sản phẩm đổi giá đơn cũ không bị đổi)

    # Quan hệ
    order = relationship("Order", back_populates="items")
    # Thêm dòng này để Admin xem được tên sản phẩm dễ dàng
    product = relationship("Product")



class Review(Base):
    __tablename__ = "reviews"
    id         = Column(Integer, primary_key=True, index=True)
    order_id   = Column(Integer, ForeignKey("orders.id"), unique=True, nullable=False)
    rating     = Column(Integer, nullable=False)   # 1-5 sao
    comment    = Column(Text, default="")
    created_at = Column(DateTime, default=now_vn)

    order = relationship("Order")



class Wishlist(Base):
    __tablename__ = "wishlists"
    id         = Column(Integer, primary_key=True, index=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    created_at = Column(DateTime, default=now_vn)
    user    = relationship("User")
    product = relationship("Product")

# ===================== SCHEMAS =====================
class RegisterSchema(BaseModel):
    email: EmailStr
    password: str


class LoginSchema(BaseModel):
    email: EmailStr
    password: str


class SendOtpSchema(BaseModel):
    email: EmailStr
    password: str


class VerifyOtpSchema(BaseModel):
    email: EmailStr
    otp: str


class ResendOtpSchema(BaseModel):
    email: EmailStr

class ForgotPasswordSchema(BaseModel):
    email: EmailStr

class ResetPasswordSchema(BaseModel):
    email: EmailStr
    otp: str
    new_password: str


class AdminKeySchema(BaseModel):
    admin_key: str


class AdminActionSchema(BaseModel):
    email: EmailStr


class CreateStaffSchema(BaseModel):
    email: EmailStr
    password: str


class CategoryCreateSchema(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class CategoryUpdateSchema(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ProductCreateSchema(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    price: int = Field(ge=0)
    stock: int = Field(ge=0, default=0)
    description: str = ""
    image_url: str = ""
    category_id: Optional[int] = None
    is_active: bool = True


class ProductUpdateSchema(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    price: Optional[int] = Field(default=None, ge=0)
    stock: Optional[int] = Field(default=None, ge=0)
    description: Optional[str] = None
    image_url: Optional[str] = None
    category_id: Optional[int] = None
    is_active: Optional[bool] = None


class CouponCreateSchema(BaseModel):
    code: str
    label: str = ""
    discount_type: str = "percent"
    discount_value: int
    user_id: Optional[int] = None
    expires_at: Optional[datetime] = None


class FlashSaleCreateSchema(BaseModel):
    product_id: int
    sale_price: int
    start_time: datetime
    end_time: datetime



class CartItemSchema(BaseModel):
    product_id: int
    quantity: int = Field(ge=1)
    unit_price: Optional[float] = None


class OrderCreateSchema(BaseModel):
    items: List[CartItemSchema]
    shipping_address: Optional[str] = ""
    phone_number: Optional[str] = ""
    customer_name: Optional[str] = ""
    voucher_code: Optional[str] = None



class OrderStatusUpdateSchema(BaseModel):
    status: str


class ReviewCreateSchema(BaseModel):
    rating:  int = Field(ge=1, le=5)
    comment: str = ""



# ===================== DB INIT & MIGRATIONS =====================
Base.metadata.create_all(bind=engine)

def ensure_column(engine, table_name: str, column_name: str, column_def_sql: str):
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        if table_name not in tables:
            return
        columns = [c['name'] for c in inspector.get_columns(table_name)]
        if column_name not in columns:
            print(f"[migration] Column '{column_name}' missing in table '{table_name}'. Adding...")
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def_sql}"))
            print(f"[migration] Successfully added column '{column_name}' to '{table_name}'.")
    except Exception as e:
        print(f"[migration warning] Error checking/adding column {table_name}.{column_name}: {e}")

def run_auto_migrations(engine):
    # 1. Coupons table
    ensure_column(engine, "coupons", "user_id", "INTEGER")
    ensure_column(engine, "coupons", "label", "VARCHAR DEFAULT ''")
    ensure_column(engine, "coupons", "discount_type", "VARCHAR DEFAULT 'percent'")
    ensure_column(engine, "coupons", "discount_value", "INTEGER DEFAULT 0")
    ensure_column(engine, "coupons", "is_active", "BOOLEAN DEFAULT TRUE")
    ensure_column(engine, "coupons", "expires_at", "TIMESTAMP")
    ensure_column(engine, "coupons", "created_at", "TIMESTAMP")

    # 2. FlashSales table
    ensure_column(engine, "flash_sales", "product_id", "INTEGER")
    ensure_column(engine, "flash_sales", "sale_price", "INTEGER DEFAULT 0")
    ensure_column(engine, "flash_sales", "start_time", "TIMESTAMP")
    ensure_column(engine, "flash_sales", "end_time", "TIMESTAMP")
    ensure_column(engine, "flash_sales", "is_active", "BOOLEAN DEFAULT TRUE")
    ensure_column(engine, "flash_sales", "created_at", "TIMESTAMP")

    # 3. Users table
    ensure_column(engine, "users", "status", "VARCHAR DEFAULT 'ACTIVE'")
    ensure_column(engine, "users", "role", "VARCHAR DEFAULT 'USER'")

    # 4. Products table
    ensure_column(engine, "products", "image_url", "VARCHAR DEFAULT ''")
    ensure_column(engine, "products", "is_active", "BOOLEAN DEFAULT TRUE")
    ensure_column(engine, "products", "category_id", "INTEGER")

run_auto_migrations(engine)


# ===================== TÌM KIẾM BẰNG HÌNH ẢNH (CLIP) =====================
# Dùng model CLIP đã huấn luyện sẵn (OpenAI, ~400 triệu cặp ảnh-văn bản) để biến
# ảnh thành vector đặc trưng rồi so khớp cosine similarity. Model KHÔNG học thêm
# gì từ ảnh của shop — chỉ dùng để trích xuất đặc trưng (inference), nên tải rất
# nhẹ (không cần GPU, không cần huấn luyện).
#
# Model được load "lười" (lazy) — chỉ tải vào bộ nhớ ở lần gọi đầu tiên, tránh
# làm chậm lúc khởi động server (quan trọng khi deploy trên Render free tier).

import io
import json
import base64
import concurrent.futures
from starlette.concurrency import run_in_threadpool

_clip_model = None
_clip_preprocess = None
_clip_device = "cpu"


def _load_clip():
    """Tải model CLIP vào bộ nhớ (chỉ chạy 1 lần, các lần sau dùng lại).
    Có timeout 120s để tránh treo vô hạn khi mạng chậm / không tải được checkpoint."""
    global _clip_model, _clip_preprocess
    if _clip_model is not None:
        return _clip_model, _clip_preprocess
    try:
        import torch
        import open_clip
    except ImportError as e:
        raise RuntimeError(
            "Chưa cài thư viện cho tính năng tìm kiếm bằng ảnh. "
            "Chạy: pip install open_clip_torch torch pillow numpy"
        ) from e

    print("[clip] Đang tải model CLIP (ViT-B-32, openai)... lần đầu có thể mất 30-60s")

    def _do_load():
        return open_clip.create_model_and_transforms("ViT-B-32", pretrained="openai")

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_do_load)
            model, _, preprocess = future.result(timeout=120)
    except concurrent.futures.TimeoutError:
        raise RuntimeError(
            "Tải model CLIP quá lâu (>120s). Có thể do mạng chậm hoặc bộ nhớ không đủ. "
            "Vui lòng thử lại sau hoặc liên hệ admin."
        )
    except Exception as e:
        raise RuntimeError(f"Lỗi khi tải model CLIP: {e}") from e

    model.eval()
    _clip_model, _clip_preprocess = model, preprocess
    print("[clip] Đã tải xong model CLIP.")
    return _clip_model, _clip_preprocess


def _encode_image_bytes(image_bytes: bytes):
    """Ảnh (bytes) -> vector đặc trưng đã chuẩn hoá (list[float])."""
    import torch
    from PIL import Image
    import numpy as np

    model, preprocess = _load_clip()
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as e:
        raise HTTPException(status_code=400, detail="File ảnh không hợp lệ hoặc bị hỏng") from e

    tensor = preprocess(img).unsqueeze(0)
    with torch.no_grad():
        features = model.encode_image(tensor)
        features = features / features.norm(dim=-1, keepdim=True)  # chuẩn hoá về vector đơn vị
    return features.squeeze(0).cpu().numpy().astype("float32")


def _fetch_image_bytes(image_url: str) -> Optional[bytes]:
    """Lấy bytes ảnh từ URL (http...) hoặc đường dẫn local (/static/...)."""
    if not image_url:
        return None
    try:
        if image_url.startswith("http://") or image_url.startswith("https://"):
            resp = http_requests.get(image_url, timeout=10)
            resp.raise_for_status()
            return resp.content
        # đường dẫn local kiểu /static/xxx.jpg
        local_path = BASE_DIR / image_url.lstrip("/")
        if local_path.is_file():
            return local_path.read_bytes()
    except Exception as e:
        print(f"[clip] Không tải được ảnh '{image_url}': {e}")
    return None


def _encode_product_image(db: Session, product: "Product") -> bool:
    """Encode ảnh của 1 sản phẩm và lưu/cập nhật vào bảng product_embeddings.
    Trả về True nếu thành công."""
    if not product.image_url:
        return False
    img_bytes = _fetch_image_bytes(product.image_url)
    if not img_bytes:
        return False
    try:
        vec = _encode_image_bytes(img_bytes)
    except Exception as e:
        print(f"[clip] Lỗi encode sản phẩm #{product.id}: {e}")
        return False

    row = db.query(ProductEmbedding).filter(ProductEmbedding.product_id == product.id).first()
    vec_json = json.dumps(vec.tolist())
    if row:
        row.vector = vec_json
        row.image_url = product.image_url
        row.updated_at = now_vn()
    else:
        row = ProductEmbedding(
            product_id=product.id, vector=vec_json,
            image_url=product.image_url, updated_at=now_vn()
        )
        db.add(row)
    db.commit()
    return True


def _cosine_search(query_vec, top_k: int = 12):
    """So query_vec với toàn bộ vector đã lưu, trả về [(product_id, score), ...] giảm dần."""
    import numpy as np

    db = SessionLocal()
    try:
        rows = db.query(ProductEmbedding).all()
        if not rows:
            return []
        ids = []
        mat = []
        for r in rows:
            try:
                ids.append(r.product_id)
                mat.append(json.loads(r.vector))
            except Exception:
                continue
        if not mat:
            return []
        mat = np.array(mat, dtype="float32")          # (N, D), đã chuẩn hoá sẵn lúc lưu
        q = np.array(query_vec, dtype="float32")
        sims = mat @ q                                  # cosine similarity (vì đã L2-normalize)
        order = np.argsort(-sims)[:top_k]
        return [(ids[i], float(sims[i])) for i in order]
    finally:
        db.close()


def seed_admin():
    """Luôn đồng bộ admin trong DB với ENV: email, password, role=ADMIN, status=ACTIVE."""
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        return
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.email == ADMIN_EMAIL).first()
        if not admin:
            admin = User(
                email=ADMIN_EMAIL,
                password=hash_password(ADMIN_PASSWORD),
                role=ROLE_ADMIN,
                status=STATUS_ACTIVE,
            )
            db.add(admin)
        else:
            admin.password = hash_password(ADMIN_PASSWORD)
            admin.role = ROLE_ADMIN
            admin.status = STATUS_ACTIVE
        db.commit()
    finally:
        db.close()


def seed_initial_data():
    seed_admin()
    db = SessionLocal()
    try:
        welcome = db.query(Coupon).filter(Coupon.code == "WELCOME10").first()
        if not welcome:
            c = Coupon(
                code="WELCOME10",
                label="Giảm 10% đơn đầu tiên",
                discount_type="percent",
                discount_value=10,
                is_active=True
            )
            db.add(c)
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


seed_initial_data()



# ===================== DEPENDENCIES =====================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user_optional(authorization: Optional[str] = Header(default=None), db: Session = Depends(get_db)) -> Optional[User]:
    if not authorization:
        return None
    try:
        token = authorization
        if authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            return None
        user = db.query(User).filter(User.email == email).first()
        if not user or user.status == STATUS_BANNED:
            return None
        return user
    except Exception:
        return None


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Token không hợp lệ")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token không hợp lệ")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Không tìm thấy user")

    # chặn token cũ nếu bị BAN
    if user.status == STATUS_BANNED:
        raise HTTPException(status_code=403, detail=BANNED_LOGIN_MESSAGE)

    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Chỉ admin mới được phép")
    return user


def require_staff_or_admin(user: User = Depends(get_current_user)) -> User:
    if user.role not in {ROLE_STAFF, ROLE_ADMIN}:
        raise HTTPException(status_code=403, detail="Chỉ staff hoặc admin mới được phép")
    return user


# ===================== HEALTH =====================
@app.get("/health")
def health():
    return {"status": "ok"}


# ✅ FIX: bạn bị trùng route /register ở bản trước.
# Mình giữ nguyên hàm serve_html nhưng đổi đường dẫn để KHÔNG đè route /register.
@app.get("/register-page")
def page_register_duplicate_fixed():
    return serve_html("register.html")


# ===================== AUTH =====================
@app.post("/auth/register")
def register(data: RegisterSchema, db: Session = Depends(get_db)):
    ensure_password_ok(data.password)

    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email đã tồn tại")

    # Chỉ user thường: không cho đăng ký trùng mail admin
    if ADMIN_EMAIL and _normalize_email(data.email) == _normalize_email(ADMIN_EMAIL):
        raise HTTPException(status_code=400, detail="Email này không dùng để đăng ký")

    user = User(
        email=data.email,
        password=hash_password(data.password),
        role=ROLE_USER,
        status=STATUS_ACTIVE,
    )
    db.add(user)
    db.commit()
    return {"message": "Đăng ký thành công"}


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


# ===================== AUTH: ĐĂNG KÝ QUA OTP EMAIL =====================
@app.post("/auth/send-otp")
def send_otp(data: SendOtpSchema, db: Session = Depends(get_db)):
    ensure_password_ok(data.password)
    email_norm = _normalize_email(data.email)

    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email đã tồn tại")

    if ADMIN_EMAIL and email_norm == _normalize_email(ADMIN_EMAIL):
        raise HTTPException(status_code=400, detail="Email này không dùng để đăng ký")

    otp_code = generate_otp_code()
    PENDING_REGISTRATIONS[email_norm] = {
        "email": data.email,
        "password_hash": hash_password(data.password),
        "otp": otp_code,
        "expires_at": now_vn() + timedelta(minutes=OTP_EXPIRE_MINUTES),
        "attempts": 0,
        "last_sent_at": now_vn(),
    }

    send_otp_email(data.email, otp_code)
    return {"message": "Đã gửi mã OTP đến email của bạn"}


@app.post("/auth/verify-otp")
def verify_otp(data: VerifyOtpSchema, db: Session = Depends(get_db)):
    email_norm = _normalize_email(data.email)
    pending = PENDING_REGISTRATIONS.get(email_norm)

    if not pending:
        raise HTTPException(status_code=400, detail="Không tìm thấy yêu cầu đăng ký, vui lòng đăng ký lại")

    if now_vn() > pending["expires_at"]:
        del PENDING_REGISTRATIONS[email_norm]
        raise HTTPException(status_code=400, detail="Mã OTP đã hết hạn, vui lòng đăng ký lại")

    if pending["otp"] != data.otp.strip():
        pending["attempts"] += 1
        if pending["attempts"] >= OTP_MAX_ATTEMPTS:
            del PENDING_REGISTRATIONS[email_norm]
            raise HTTPException(status_code=400, detail="Sai mã quá nhiều lần, vui lòng đăng ký lại")
        raise HTTPException(status_code=400, detail="Mã OTP không đúng")

    # OTP đúng -> tạo tài khoản thật trong DB
    if db.query(User).filter(User.email == pending["email"]).first():
        del PENDING_REGISTRATIONS[email_norm]
        raise HTTPException(status_code=400, detail="Email đã tồn tại")

    user = User(
        email=pending["email"],
        password=pending["password_hash"],
        role=ROLE_USER,
        status=STATUS_ACTIVE,
    )
    db.add(user)
    db.commit()
    del PENDING_REGISTRATIONS[email_norm]
    return {"message": "Xác thực thành công! Tài khoản đã được tạo"}


@app.post("/auth/resend-otp")
def resend_otp(data: ResendOtpSchema):
    email_norm = _normalize_email(data.email)
    pending = PENDING_REGISTRATIONS.get(email_norm)

    if not pending:
        raise HTTPException(status_code=400, detail="Không tìm thấy yêu cầu đăng ký, vui lòng đăng ký lại")

    elapsed = (now_vn() - pending["last_sent_at"]).total_seconds()
    if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
        wait = int(OTP_RESEND_COOLDOWN_SECONDS - elapsed)
        raise HTTPException(status_code=429, detail=f"Vui lòng đợi {wait}s trước khi gửi lại")

    otp_code = generate_otp_code()
    pending["otp"] = otp_code
    pending["expires_at"] = now_vn() + timedelta(minutes=OTP_EXPIRE_MINUTES)
    pending["attempts"] = 0
    pending["last_sent_at"] = now_vn()

    send_otp_email(pending["email"], otp_code)
    return {"message": "Đã gửi lại mã OTP mới"}



# ===================== QUÊN MẬT KHẨU =====================

@app.post("/auth/forgot-password")
def forgot_password(data: ForgotPasswordSchema, db: Session = Depends(get_db)):
    email_norm = _normalize_email(data.email)
    user = db.query(User).filter(User.email == email_norm).first()
    if not user:
        raise HTTPException(status_code=404, detail="Email này chưa được đăng ký!")
    if user.status == STATUS_BANNED:
        raise HTTPException(status_code=403, detail="Tài khoản đã bị khoá!")

    # Kiểm tra cooldown
    existing = PENDING_RESETS.get(email_norm)
    if existing:
        elapsed = (now_vn() - existing["last_sent_at"]).total_seconds()
        if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
            wait = int(OTP_RESEND_COOLDOWN_SECONDS - elapsed)
            raise HTTPException(status_code=429, detail=f"Vui lòng đợi {wait}s trước khi gửi lại")

    otp_code = generate_otp_code()
    PENDING_RESETS[email_norm] = {
        "otp":         otp_code,
        "expires_at":  now_vn() + timedelta(minutes=OTP_EXPIRE_MINUTES),
        "attempts":    0,
        "last_sent_at": now_vn(),
    }

    # Gửi email OTP
    html_body = (
        "<div style='font-family:Arial,sans-serif;max-width:480px;margin:auto;"
        "background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.10)'>"
        "<div style='background:linear-gradient(135deg,#3b82f6,#1d4ed8);padding:28px 32px'>"
        "<h2 style='color:#fff;margin:0;font-size:22px'>Shop Truong Hong Anh</h2>"
        "<p style='color:rgba(255,255,255,0.85);margin:6px 0 0;font-size:14px'>Dat lai mat khau</p>"
        "</div>"
        "<div style='padding:32px'>"
        "<p style='color:#374151;font-size:15px'>Ban vua yeu cau dat lai mat khau.</p>"
        "<p style='color:#374151;font-size:15px'>Ma OTP xac thuc cua ban la:</p>"
        "<div style='text-align:center;margin:24px 0'>"
        f"<span style='font-size:40px;font-weight:700;letter-spacing:10px;color:#3b82f6;"
        f"background:#eff6ff;padding:16px 24px;border-radius:12px;border:2px dashed #bfdbfe'>{otp_code}</span>"
        "</div>"
        f"<p style='color:#6b7280;font-size:13px;text-align:center'>Ma co hieu luc trong <b>{OTP_EXPIRE_MINUTES} phut</b></p>"
        "<p style='color:#ef4444;font-size:12px;text-align:center;margin-top:8px'>Khong chia se ma nay cho bat ky ai!</p>"
        "</div>"
        "<div style='background:#f9fafb;padding:16px 32px;text-align:center'>"
        "<p style='color:#9ca3af;font-size:12px;margin:0'>2025 Shop Truong Hong Anh</p>"
        "</div></div>"
    )
    brevo_payload = {
        "sender": {"name": SENDER_NAME, "email": EMAIL_SENDER},
        "to": [{"email": data.email}],
        "subject": "Ma OTP dat lai mat khau - Shop Truong Hong Anh",
        "htmlContent": html_body
    }
    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }
    try:
        res = http_requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=brevo_payload, headers=headers, timeout=12
        )
        if res.status_code not in (200, 201):
            raise HTTPException(status_code=500, detail=f"Brevo loi: {res.text[:200]}")
    except http_requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Khong gui duoc email: {str(e)}")

    return {"message": "Da gui ma OTP ve email cua ban!"}



@app.post("/auth/verify-reset-otp")
def verify_reset_otp(data: VerifyOtpSchema, db: Session = Depends(get_db)):
    email_norm = _normalize_email(data.email)
    pending = PENDING_RESETS.get(email_norm)
    if not pending:
        raise HTTPException(status_code=400, detail="OTP khong hop le hoac da het han!")
    if now_vn() > pending["expires_at"]:
        PENDING_RESETS.pop(email_norm, None)
        raise HTTPException(status_code=400, detail="OTP da het han! Vui long gui lai.")
    if data.otp.strip() != pending["otp"]:
        pending["attempts"] += 1
        if pending["attempts"] >= OTP_MAX_ATTEMPTS:
            PENDING_RESETS.pop(email_norm, None)
            raise HTTPException(status_code=400, detail="Sai OTP qua nhieu lan!")
        raise HTTPException(status_code=400, detail="Ma OTP khong dung!")
    return {"message": "OTP hop le!"}


@app.post("/auth/reset-password")
def reset_password(data: ResetPasswordSchema, db: Session = Depends(get_db)):
    email_norm = _normalize_email(data.email)
    pending = PENDING_RESETS.get(email_norm)

    if not pending:
        raise HTTPException(status_code=400, detail="OTP không hợp lệ hoặc đã hết hạn!")
    if now_vn() > pending["expires_at"]:
        PENDING_RESETS.pop(email_norm, None)
        raise HTTPException(status_code=400, detail="OTP đã hết hạn! Vui lòng gửi lại.")
    if data.otp.strip() != pending["otp"]:
        pending["attempts"] += 1
        if pending["attempts"] >= OTP_MAX_ATTEMPTS:
            PENDING_RESETS.pop(email_norm, None)
            raise HTTPException(status_code=400, detail="Sai OTP quá nhiều lần! Vui lòng thử lại.")
        raise HTTPException(status_code=400, detail="Mã OTP không đúng!")

    ensure_password_ok(data.new_password)
    user = db.query(User).filter(User.email == email_norm).first()
    if not user:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản!")

    user.password = hash_password(data.new_password)
    db.commit()
    PENDING_RESETS.pop(email_norm, None)
    return {"message": "Đặt lại mật khẩu thành công! Vui lòng đăng nhập."}


# --- Sửa hàm LOGIN để phân quyền và trả về Redirect ---
@app.post("/auth/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    # 1. Tìm user
    user = db.query(User).filter(User.email == data.email).first()
    
    # 2. Kiểm tra mật khẩu
    if not user or not verify_password(data.password, user.password):
        return {"success": False, "message": "Sai email hoặc mật khẩu!"}

    # 3. Kiểm tra bị khóa
    if user.status == "BANNED":
        return {"success": False, "message": "Tài khoản của bạn đã bị cấm. Vui lòng liên hệ Admin!"}

    # 4. Tạo Token
    token = create_token({"sub": user.email, "role": user.role})
    
    # Logic phân quyền chuẩn
    # Lấy role từ DB, nếu không có thì mặc định là USER, sau đó viết HOA hết lên để so sánh
    # Kiểm tra lại đoạn này trong main.py
    user_role = (user.role or "USER").upper()
    
    if user_role in ("ADMIN", "STAFF"):
        redirect_url = "/admin"
    else:
        redirect_url = "/shop"
        
    return {
        "success": True,
        "access_token": token,
        "redirect": redirect_url  # Đảm bảo có dòng này
    }

@app.post("/auth/admin-key")
def auth_admin_key(
    data: AdminKeySchema,
    user: User = Depends(get_current_user),
):
    """Bước 2: yêu cầu ROLE_ADMIN, so sánh admin_key với ADMIN_SECRET_KEY từ env. Đúng → redirect /static/admin.html."""
    if user.role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Không phải admin")
    secret = os.getenv("ADMIN_SECRET_KEY")
    if not secret:
        raise HTTPException(status_code=500, detail="Chưa cấu hình ADMIN_SECRET_KEY")
    if data.admin_key != secret:
        return {"success": False, "message": "Admin key không đúng"}
    return {"success": True, "redirect": "/static/admin.html"}

@app.post("/auth/token")
def token_for_swagger(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """OAuth2/Swagger: Hỗ trợ đăng nhập trực tiếp trên trang tài liệu"""
    email = form_data.username
    password = form_data.password
    
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password):
        raise HTTPException(status_code=401, detail="Sai thông tin đăng nhập")
        
    if user.status == STATUS_BANNED:
        raise HTTPException(status_code=403, detail="Tài khoản bị khóa")

    token = create_token({"sub": user.email, "role": user.role})
    return {"access_token": token, "token_type": "bearer"}


@app.get("/me")
def get_me(user: User = Depends(get_current_user)):
    # Phải trả về đúng role viết HOA để khớp với JavaScript ở trên
    return {
        "email": user.email,
        "role": user.role.upper() if user.role else "USER"
    }


# ===================== ADMIN: USERS/STAFF =====================
@app.get("/admin/users")
def admin_list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id.asc()).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "role": u.role,
            "status": u.status,
            "created_at": u.created_at,
        }
        for u in users
    ]

# --- PHẦN QUẢN LÝ USER DÀNH CHO ADMIN ---

# 1. API Lấy danh sách tất cả người dùng
# 1. API Lấy danh sách tất cả người dùng (Dùng cột status)
@app.get("/users")
async def get_all_users(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    users = db.query(User).all()
    return [{
        "id": u.id, 
        "email": u.email, 
        "role": u.role, 
        "status": u.status # Trả về ACTIVE hoặc BANNED
    } for u in users]

# 2. API Khóa hoặc Mở khóa tài khoản (Toggle ACTIVE/BANNED)
@app.put("/users/{user_id}/toggle-active")
async def toggle_user_active(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    # Không cho tự khóa chính mình
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Bạn không thể tự khóa chính mình!")
        
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại")
    
    # Logic đổi trạng thái dựa trên cột status cũ của bạn
    if user.status == "ACTIVE":
        user.status = "BANNED"
        msg = f"Đã khóa tài khoản {user.email}"
    else:
        user.status = "ACTIVE"
        msg = f"Đã mở khóa tài khoản {user.email}"
        
    db.commit()
    return {"message": msg}

# 3. API Xóa tài khoản (Giữ nguyên logic bảo vệ Admin)
@app.delete("/users/{user_id}")
async def delete_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Không thể tự xóa chính mình!")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại")
        
    if user.role.upper() == "ADMIN":
        raise HTTPException(status_code=400, detail="Không được xóa Admin khác!")
        
    db.delete(user)
    db.commit()
    return {"message": "Đã xóa người dùng thành công"}


@app.post("/admin/create-staff")
def admin_create_staff(data: CreateStaffSchema, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    ensure_password_ok(data.password)

    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email đã tồn tại")

    staff = User(
        email=data.email,
        password=hash_password(data.password),
        role=ROLE_STAFF,
        status=STATUS_ACTIVE
    )
    db.add(staff)
    db.commit()
    return {"message": f"Đã tạo STAFF: {data.email}"}


@app.post("/admin/ban")
def ban_user(data: AdminActionSchema, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == data.email).first()
    if not u:
        raise HTTPException(status_code=404, detail="Không tìm thấy user")
    if u.role == ROLE_ADMIN:
        raise HTTPException(status_code=400, detail="Không thể khóa admin")
    u.status = STATUS_BANNED
    db.commit()
    return {"message": f"Đã khóa {data.email}"}


@app.post("/admin/unban")
def unban_user(data: AdminActionSchema, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == data.email).first()
    if not u:
        raise HTTPException(status_code=404, detail="Không tìm thấy user")
    u.status = STATUS_ACTIVE
    db.commit()
    return {"message": f"Đã mở khóa {data.email}"}

# BƯỚC 1: ĐỊNH NGHĨA CLASS TRƯỚC (Đây là cái Python đang báo thiếu)
class EmailRequest(BaseModel):
    email: str

# 2. Hàm xóa chuẩn duy nhất (theo email)
@app.delete("/admin/delete")
def delete_user_by_email(data: EmailRequest, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    # Tìm user dựa trên email gửi từ giao diện
    user_to_delete = db.query(User).filter(User.email == data.email).first()
    
    if not user_to_delete:
        raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")

    # Không cho phép Admin tự xóa chính mình
    if user_to_delete.email == current_user.email:
        raise HTTPException(status_code=400, detail="Không thể tự xóa tài khoản admin của mình")

    db.delete(user_to_delete)
    db.commit()
    
    print(f">>> DA XOA USER: {data.email}")
    return {"success": True, "message": f"Đã xóa tài khoản {data.email}"}


# ===================== CATEGORIES =====================
@app.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    cats = db.query(Category).order_by(Category.id.asc()).all()
    return [{"id": c.id, "name": c.name} for c in cats]


@app.post("/admin/categories")
def create_category(data: CategoryCreateSchema, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    name = data.name.strip()
    if db.query(Category).filter(Category.name == name).first():
        raise HTTPException(status_code=400, detail="Category đã tồn tại")
    c = Category(name=name)
    db.add(c)
    db.commit()
    return {"message": "Tạo category thành công", "id": c.id}


@app.put("/admin/categories/{category_id}")
def update_category(category_id: int, data: CategoryUpdateSchema, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.query(Category).filter(Category.id == category_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Không tìm thấy category")
    new_name = data.name.strip()
    exists = db.query(Category).filter(Category.name == new_name, Category.id != category_id).first()
    if exists:
        raise HTTPException(status_code=400, detail="Tên category đã tồn tại")
    c.name = new_name
    db.commit()
    return {"message": "Cập nhật category thành công"}


@app.delete("/admin/categories/{category_id}")
def delete_category(category_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.query(Category).filter(Category.id == category_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Không tìm thấy category")
    # bỏ liên kết của product trước (an toàn)
    for p in c.products:
        p.category_id = None
    db.delete(c)
    db.commit()
    return {"message": "Xóa category thành công"}


# ===================== COUPONS =====================
@app.get("/coupons/validate")
def validate_coupon(code: str, user: Optional[User] = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    c = db.query(Coupon).filter(Coupon.code == code.strip().upper(), Coupon.is_active == True).first()
    if not c:
        raise HTTPException(status_code=404, detail="Mã giảm giá không hợp lệ")
    if c.expires_at and c.expires_at < now_vn():
        raise HTTPException(status_code=400, detail="Mã đã hết hạn")
    if c.user_id is not None and (not user or user.id != c.user_id):
        raise HTTPException(status_code=403, detail="Mã này không áp dụng cho tài khoản của bạn")
    return {"code": c.code, "label": c.label, "discount_type": c.discount_type, "discount_value": c.discount_value}

@app.get("/coupons/mine")
def get_my_coupons(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = now_vn()
    coupons = db.query(Coupon).filter(
        Coupon.is_active == True,
        (Coupon.expires_at == None) | (Coupon.expires_at >= now),
        (Coupon.user_id == None) | (Coupon.user_id == user.id)
    ).order_by(Coupon.id.desc()).all()
    return [{
        "code": c.code,
        "label": c.label,
        "discount_type": c.discount_type,
        "discount_value": c.discount_value,
        "personal": c.user_id is not None
    } for c in coupons]

@app.post("/admin/coupons")
def create_coupon(data: CouponCreateSchema, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    data_dict = data.dict()
    code = data_dict['code'].strip().upper()
    data_dict['code'] = code
    
    existing = db.query(Coupon).filter(Coupon.code == code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Mã giảm giá đã tồn tại")

    if data_dict.get("user_id"):
        target_u = db.query(User).filter(User.id == data_dict["user_id"]).first()
        if not target_u:
            raise HTTPException(status_code=404, detail="Không tìm thấy người dùng")
    c = Coupon(**data_dict)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c

@app.get("/admin/coupons")
def list_coupons(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    coupons = db.query(Coupon).order_by(Coupon.id.desc()).all()
    result = []
    for c in coupons:
        u_email = None
        if c.user_id:
            u = db.query(User).filter(User.id == c.user_id).first()
            u_email = u.email if u else None
        result.append({
            "id": c.id,
            "code": c.code,
            "label": c.label,
            "discount_type": c.discount_type,
            "discount_value": c.discount_value,
            "is_active": c.is_active,
            "expires_at": c.expires_at.isoformat() if c.expires_at else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "user_id": c.user_id,
            "user_email": u_email
        })
    return result

@app.delete("/admin/coupons/{coupon_id}")
def delete_coupon(coupon_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    c = db.query(Coupon).filter(Coupon.id == coupon_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Không tìm thấy")
    db.delete(c)
    db.commit()
    return {"message": "Đã xoá"}


# ===================== FLASH SALES =====================
@app.get("/flash-sales/active")
def get_active_flash_sales(db: Session = Depends(get_db)):
    now = now_vn()
    sales = db.query(FlashSale).filter(
        FlashSale.is_active == True,
        FlashSale.start_time <= now,
        FlashSale.end_time >= now,
    ).all()
    return [{
        "id": s.id,
        "product_id": s.product_id,
        "sale_price": s.sale_price,
        "start_time": s.start_time.isoformat() if s.start_time else None,
        "end_time": s.end_time.isoformat() if s.end_time else None,
        "product": {
            "id": s.product.id,
            "name": s.product.name,
            "price": s.product.price,
            "image_url": s.product.image_url,
            "description": s.product.description
        } if s.product else None
    } for s in sales]

@app.post("/admin/flash-sales")
def create_flash_sale(data: FlashSaleCreateSchema, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    data_dict = data.dict()
    from datetime import timezone, timedelta
    if data_dict.get('start_time') and data_dict['start_time'].tzinfo is not None:
        data_dict['start_time'] = data_dict['start_time'].astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)
    if data_dict.get('end_time') and data_dict['end_time'].tzinfo is not None:
        data_dict['end_time'] = data_dict['end_time'].astimezone(timezone(timedelta(hours=7))).replace(tzinfo=None)
    fs = FlashSale(**data_dict)
    db.add(fs)
    db.commit()
    db.refresh(fs)
    return fs

@app.get("/admin/flash-sales")
def list_flash_sales(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    sales = db.query(FlashSale).order_by(FlashSale.id.desc()).all()
    return [{
        "id": s.id,
        "product_id": s.product_id,
        "product_name": s.product.name if s.product else f"SP #{s.product_id}",
        "product_img": s.product.image_url if (s.product and s.product.image_url) else "",
        "original_price": s.product.price if s.product else 0,
        "sale_price": s.sale_price,
        "start_time": s.start_time.isoformat() if s.start_time else None,
        "end_time": s.end_time.isoformat() if s.end_time else None,
        "is_active": s.is_active
    } for s in sales]

@app.delete("/admin/flash-sales/{sale_id}")
def delete_flash_sale(sale_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    fs = db.query(FlashSale).filter(FlashSale.id == sale_id).first()
    if not fs:
        raise HTTPException(status_code=404, detail="Không tìm thấy")
    db.delete(fs)
    db.commit()
    return {"message": "Đã xoá"}


@app.get("/admin/products/low-stock")
def get_low_stock_products(threshold: int = 10, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(Product).filter(Product.stock < threshold, Product.is_active == True).all()


# ===================== PRODUCTS (PUBLIC) =====================


# --- 1. Khai báo cấu trúc dữ liệu gửi lên (Thêm cái này trên các hàm @app) ---
class ImportProductItem(BaseModel):
    name: str
    price: int
    image_url: str

# --- 2. Các hàm API ---

@app.get("/products")
def list_products(
    q: Optional[str] = None,
    category_id: Optional[int] = None,
    sort: str = "new", 
    include_inactive: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(Product)
    if not include_inactive:
        query = query.filter(Product.is_active == True)
    if q:
        query = query.filter(Product.name.ilike(f"%{q.strip()}%"))
    if category_id is not None:
        query = query.filter(Product.category_id == category_id)

    if sort == "price_asc":
        query = query.order_by(Product.price.asc())
    elif sort == "price_desc":
        query = query.order_by(Product.price.desc())
    else:
        query = query.order_by(Product.id.desc())
    return query.all()

# Thêm Schema để FastAPI hiểu cấu trúc dữ liệu gửi lên
from pydantic import BaseModel

class ProductCreate(BaseModel):
    name: str
    price: int
    image_url: str
    description: str = "Sản phẩm từ TGDD"

# ĐÂY LÀ HÀM CẬU ĐANG THIẾU:
@app.post("/products")
def create_product(product_data: ProductCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    # Tạo đối tượng Product mới để lưu vào Database
    new_product = Product(
        name=product_data.name,
        price=product_data.price,
        image_url=product_data.image_url,
        description=product_data.description,
        is_active=True  # Đảm bảo nó hiện lên ngay
    )
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    # Encode ảnh sản phẩm ngầm (không làm chậm response) để phục vụ tìm kiếm bằng ảnh
    background_tasks.add_task(_encode_product_image_bg, new_product.id)
    return new_product


def _encode_product_image_bg(product_id: int):
    """Chạy trong background: encode ảnh sản phẩm và lưu vector. Tự mở session riêng."""
    db = SessionLocal()
    try:
        p = db.query(Product).filter(Product.id == product_id).first()
        if p:
            _encode_product_image(db, p)
    except Exception as e:
        print(f"[clip] Lỗi encode ngầm sản phẩm #{product_id}: {e}")
    finally:
        db.close()


# ===================== ENDPOINT: TÌM KIẾM BẰNG HÌNH ẢNH =====================

@app.post("/search-by-image")
async def search_by_image(file: UploadFile = File(...), top_k: int = 12, db: Session = Depends(get_db)):
    """Nhận 1 ảnh, dùng Gemini Vision API phân tích → tìm sản phẩm phù hợp trong shop.
    Thay thế CLIP (quá nặng cho Render free tier) bằng Gemini (chỉ cần 1 HTTP call)."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Vui lòng tải lên 1 file ảnh (jpg, png...)")

    img_bytes = await file.read()
    if len(img_bytes) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Ảnh quá lớn (tối đa 8MB)")

    # Lấy Gemini API key (có key dự phòng giống chatbot)
    gemini_key = os.getenv("GEMINI_API_KEY", "AIzaSyAJKjMcv0vhlG-KDfeOZGNxtppZ6lyN3B4")
    if not gemini_key:
        raise HTTPException(status_code=503, detail="Chưa cấu hình GEMINI_API_KEY. Vui lòng liên hệ admin.")

    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"

    # Lấy danh sách sản phẩm đang bán
    products = db.query(Product).filter(Product.is_active == True).all()
    if not products:
        return {"results": [], "message": "Chưa có sản phẩm nào trong cửa hàng."}

    # Gửi ảnh tới Gemini Vision API
    img_b64 = base64.b64encode(img_bytes).decode("utf-8")
    mime_type = file.content_type or "image/jpeg"

    # Chuẩn bị payload cho Gemini Vision (gửi kèm ảnh sản phẩm thực tế để Gemini so sánh trực quan)
    parts = [
        {"inlineData": {"mimeType": mime_type, "data": img_b64}},
        {"text": "ĐÂY LÀ ẢNH KHÁCH HÀNG TẢI LÊN. Dưới đây là danh sách sản phẩm trong shop để so sánh:\n"}
    ]

    for p in products:
        p_img_bytes = None
        if p.image_url and not (p.image_url.startswith("http://") or p.image_url.startswith("https://")):
            p_img_bytes = _fetch_image_bytes(p.image_url)

        if p_img_bytes:
            p_mime = "image/png" if p.image_url.lower().endswith(".png") else "image/jpeg"
            parts.append({"text": f"\nSản phẩm ID {p.id}: {p.name} ({p.price:,}đ)"})
            parts.append({"inlineData": {"mimeType": p_mime, "data": base64.b64encode(p_img_bytes).decode("utf-8")}})
        else:
            parts.append({"text": f"\nSản phẩm ID {p.id}: {p.name} ({p.price:,}đ)"})

    parts.append({"text": (
        "\n\nNHIỆM VỤ: Hãy phân tích hình ảnh khách hàng tải lên (về thiết kế, thương hiệu, loại thiết bị, cụm camera, màu sắc...). "
        "Đối chiếu trực quan với danh sách sản phẩm của shop ở trên và chọn ra tối đa 6 sản phẩm GIỐNG NHẤT hoặc PHÙ HỢP NHẤT.\n"
        "Trả lời ĐÚNG FORMAT, mỗi dòng một sản phẩm: ID,điểm_giống(0-100)\n"
        "Ví dụ:\n5,95\n12,80\n3,60\n"
        "CHỈ trả lời theo format trên, KHÔNG viết gì thêm.\n"
        "Nếu không có sản phẩm nào giống, trả lời: NONE"
    )})

    gemini_payload = {"contents": [{"parts": parts}]}

    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(gemini_url, json=gemini_payload)
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Gemini API lỗi (HTTP {resp.status_code}). Vui lòng thử lại.")
            data = resp.json()

        # Parse Gemini response
        raw_text = ""
        try:
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except (KeyError, IndexError):
            raise HTTPException(status_code=500, detail="Không thể phân tích ảnh. Vui lòng thử lại.")

        if not raw_text or raw_text.strip().upper() == "NONE":
            return {"results": [], "message": "Không nhận diện được sản phẩm phù hợp trong ảnh."}

        # Parse kết quả: mỗi dòng "ID,similarity"
        prod_map = {p.id: p for p in products}
        results = []
        for line in raw_text.strip().split("\n"):
            line = line.strip()
            if not line or line.upper() == "NONE":
                continue
            parts = line.replace("|", ",").split(",")
            if len(parts) >= 2:
                try:
                    pid = int(parts[0].strip())
                    sim = min(100.0, max(0.0, float(parts[1].strip())))
                    p = prod_map.get(pid)
                    if p:
                        results.append({
                            "id": p.id,
                            "name": p.name,
                            "price": p.price,
                            "image_url": p.image_url,
                            "description": p.description,
                            "similarity": round(sim, 1),
                        })
                except (ValueError, TypeError):
                    continue

        results.sort(key=lambda x: x["similarity"], reverse=True)
        results = results[:top_k]

        if not results:
            return {"results": [], "message": "Không tìm thấy sản phẩm phù hợp với ảnh này trong shop."}

        return {"results": results}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[search-by-image] Lỗi: {e}")
        raise HTTPException(status_code=500, detail=f"Lỗi phân tích ảnh: {str(e)}")


@app.post("/admin/rebuild-image-index")
def rebuild_image_index(background_tasks: BackgroundTasks, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Admin bấm nút này để encode lại (hoặc encode lần đầu) toàn bộ ảnh sản phẩm.
    Chạy nền vì có thể mất vài phút nếu nhiều sản phẩm."""
    product_ids = [p.id for p in db.query(Product.id).filter(Product.is_active == True).all()]
    background_tasks.add_task(_rebuild_index_bg, product_ids)
    return {"message": f"Đã bắt đầu dựng chỉ mục ảnh cho {len(product_ids)} sản phẩm (chạy ngầm, có thể mất vài phút)."}


def _rebuild_index_bg(product_ids: List[int]):
    db = SessionLocal()
    ok, fail = 0, 0
    try:
        for pid in product_ids:
            p = db.query(Product).filter(Product.id == pid).first()
            if p and _encode_product_image(db, p):
                ok += 1
            else:
                fail += 1
        print(f"[clip] Dựng chỉ mục ảnh xong: {ok} thành công, {fail} thất bại.")
    finally:
        db.close()


@app.get("/admin/image-index-status")
def image_index_status(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    total_products = db.query(Product).filter(Product.is_active == True).count()
    total_indexed = db.query(ProductEmbedding).count()
    return {"total_products": total_products, "total_indexed": total_indexed}

@app.post("/admin/seed-products")
def seed_products(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # 1. Xóa sạch rác cũ
    db.query(OrderItem).delete()
    db.query(Order).delete()
    db.query(Product).delete()
    
    # 2. Danh sản phẩm 
    phones = [
        {"name": "Xiaomi Redmi Note 13", "price": 4590000, "category": "điện thoại", "img": "static/a1.jpg"},
        {"name": "iPhone 14 Pro 128GB", "price": 22990000, "category": "điện thoại", "img": "static/a2.jpg"},
        {"name": "iPhone 15 Pro Max 512GB", "price": 34990000, "category": "điện thoại", "img": "static/a3.jpg"},
        {"name": "Samsung Galaxy A55 5G", "price": 10490000, "category": "điện thoại", "img": "static/a4.jpg"},
        {"name": "Samsung Galaxy S24 Ultra", "price": 27990000, "category": "điện thoại", "img": "static/a5.jpg"},
        {"name": "Tai nghe AirPods Pro 2", "price": 5990000, "category": "phụ kiện", "img": "static/a6.jpg"},
        {"name": "MacBook Air M3 2024", "price": 27490000, "category": "laptop", "img": "static/a7.jpg"},
        {"name": "Dell XPS 13 Plus", "price": 35000000, "category": "laptop", "img": "static/a8.jpg"},
        {"name": "ASUS ROG Strix G16", "price": 32990000, "category": "laptop", "img": "static/a9.jpg"},
        {"name": "HP Spectre x360", "price": 29000000, "category": "laptop", "img": "static/a10.jpg"},
        {"name": "Màn hình Dell UltraSharp 27", "price": 12500000, "category": "màn hình máy in", "img": "static/a11.jpg"},
        {"name": "Máy in HP LaserJet Pro", "price": 4500000, "category": "màn hình máy in", "img": "static/a12.jpg"},
        {"name": "iPad Pro M4 11 inch", "price": 28490000, "category": "tablet", "img": "static/a13.jpg"},
        {"name": "Samsung Galaxy Tab S9 Ultra", "price": 22990000, "category": "tablet", "img": "static/a14.jpg"},
        {"name": "Chuột Logitech MX Master 3S", "price": 2490000, "category": "phụ kiện", "img": "https://images.unsplash.com/photo-1527864550417-7fd91fc51a46?q=80&w=600&auto=format&fit=crop"},
        {"name": "Màn hình Gaming Samsung", "price": 6500000, "category": "màn hình máy in", "img": "https://images.unsplash.com/photo-1616763355548-1b606f439f86?w=600&h=600&fit=crop"},
        {"name": "Màn hình Dell 24 inch", "price": 3500000, "category": "màn hình máy in", "img": "https://images.unsplash.com/photo-1547119957-637f8679db1e?w=600&h=600&fit=crop"},
        {"name": "Máy cũ iPhone 15", "price": 15000000, "category": "thu cũ", "img": "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-15-1.jpg"},
        {"name": "iPhone 11 cũ", "price": 6500000, "category": "máy cũ", "img": "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-11-1.jpg"},
        {"name": "Samsung S21 cũ", "price": 7000000, "category": "máy cũ", "img": "https://fdn2.gsmarena.com/vv/pics/samsung/samsung-galaxy-s21-5g-1.jpg"},
        {"name": "Laptop Dell cũ", "price": 9000000, "category": "máy cũ", "img": "https://images.unsplash.com/photo-1588702547919-26089e690ecc?w=600&h=600&fit=crop"},
        {"name": "Huawei MatePad", "price": 6500000, "category": "tablet", "img": "https://fdn2.gsmarena.com/vv/pics/huawei/huawei-matepad-11-2023-1.jpg"},
        {"name": "iPad Mini 6", "price": 12000000, "category": "tablet", "img": "https://fdn2.gsmarena.com/vv/pics/apple/apple-ipad-mini-2021-1.jpg"},
        {"name": "Nokia T21", "price": 5000000, "category": "tablet", "img": "https://fdn2.gsmarena.com/vv/pics/nokia/nokia-t21-1.jpg"},
        {"name": "Casio G-Shock Smart", "price": 4000000, "category": "đồng hồ", "img": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=600&h=600&fit=crop"},
        {"name": "Oppo Watch X", "price": 8500000, "category": "smartwatch", "img": "https://fdn2.gsmarena.com/vv/pics/oppo/oppo-watch-x-1.jpg"},
        {"name": "Xiaomi Watch S3", "price": 3500000, "category": "đồng hồ", "img": "https://fdn2.gsmarena.com/vv/pics/xiaomi/xiaomi-watch-s3-1.jpg"},
        {"name": "Apple Watch Ultra 2", "price": 21000000, "category": "đồng hồ", "img": "https://fdn2.gsmarena.com/vv/pics/apple/apple-watch-ultra2-1.jpg"},
        {"name": "Samsung Watch 7 Ultra", "price": 16000000, "category": "đồng hồ", "img": "https://fdn2.gsmarena.com/vv/pics/samsung/samsung-galaxy-watch-ultra-1.jpg"},
        {"name": "Máy ảnh", "price": 250000, "category": "phụ kiện", "img": "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=600&h=600&fit=crop"},
        {"name": "Microphone Shure", "price": 5000000, "category": "phụ kiện", "img": "https://images.unsplash.com/photo-1590602847861-f357a9332bbc?w=600&h=600&fit=crop"},
        {"name": "Webcam Logitech C922", "price": 2200000, "category": "phụ kiện", "img": "https://images.unsplash.com/photo-1587825140708-dfaf72ae4b04?w=600&h=600&fit=crop"},
        {"name": "Túi chống sốc Laptop", "price": 350000, "category": "phụ kiện", "img": "https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=600&h=600&fit=crop"},
        {"name": "Bàn phím cơ AKKO", "price": 1800000, "category": "phụ kiện", "img": "https://images.unsplash.com/photo-1618384887929-16ec33fab9ef?w=600&h=600&fit=crop"},
        {"name": "Sạc dự phòng Anker 20k", "price": 1200000, "category": "phụ kiện", "img": "https://images.unsplash.com/photo-1609091839311-d5365f9ff1c5?w=600&h=600&fit=crop"},
        {"name": "Dell XPS 15", "price": 45000000, "category": "laptop", "img": "https://images.unsplash.com/photo-1593642632559-0c6d3fc62b89?w=600&h=600&fit=crop"},
        {"name": "HP Spectre x360", "price": 32000000, "category": "laptop", "img": "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=600&h=600&fit=crop"},
        {"name": "Asus Zenbook Duo", "price": 38000000, "category": "laptop", "img": "https://images.unsplash.com/photo-1541807084-5c52b6b3adef?w=600&h=600&fit=crop"},
        {"name": "Lenovo Legion 5", "price": 28000000, "category": "laptop", "img": "https://images.unsplash.com/photo-1603302576837-37561b2e2302?w=600&h=600&fit=crop"},
        {"name": "Acer Predator Helios", "price": 35000000, "category": "laptop", "img": "https://images.unsplash.com/photo-1593642634315-48f5414c3ad9?w=600&h=600&fit=crop"},
        {"name": "MSI Katana GF66", "price": 22000000, "category": "laptop", "img": "https://images.unsplash.com/photo-1587202372634-32705e3bf49c?w=600&h=600&fit=crop"},
        {"name": "Surface Laptop 5", "price": 25000000, "category": "laptop", "img": "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=600&h=600&fit=crop"},
        {"name": "LG Gram 17", "price": 31000000, "category": "laptop", "img": "https://images.unsplash.com/photo-1525547719571-a2d4ac8945e2?w=600&h=600&fit=crop"},
        {"name": "Gigabyte Aero 16", "price": 42000000, "category": "laptop", "img": "https://images.unsplash.com/photo-1611078489935-0cb964de46d6?w=600&h=600&fit=crop"},
        {"name": "Huawei MateBook X", "price": 29000000, "category": "laptop", "img": "https://images.unsplash.com/photo-1484788984921-03950022c9ef?w=600&h=600&fit=crop"},
        {"name": "iPhone SE 2022", "price": 9000000, "category": "điện thoại", "img": "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-se-2022-1.jpg"},
        {"name": "Redmi Note 13 Pro", "price": 8500000, "category": "điện thoại", "img": "https://fdn2.gsmarena.com/vv/pics/xiaomi/xiaomi-redmi-note-13-pro-1.jpg"},
        {"name": "Xiaomi 14 Ultra", "price": 22000000, "category": "điện thoại", "img": "https://fdn2.gsmarena.com/vv/pics/xiaomi/xiaomi-14-ultra-1.jpg"},
        {"name": "Google Pixel 9 Pro", "price": 21500000, "category": "điện thoại", "img": "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-9-pro-1.jpg"},
        {"name": "iPhone 14 Plus", "price": 18900000, "category": "điện thoại", "img": "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-14-plus-1.jpg"},
        {"name": "Samsung Z Fold 6", "price": 41000000, "category": "điện thoại", "img": "https://fdn2.gsmarena.com/vv/pics/samsung/samsung-galaxy-z-fold6-1.jpg"},
        {"name": "Samsung Z Flip 6", "price": 26000000, "category": "điện thoại", "img": "https://fdn2.gsmarena.com/vv/pics/samsung/samsung-galaxy-z-flip6-1.jpg"},
        {"name": "Sony Xperia 1 V", "price": 23000000, "category": "điện thoại", "img": "https://fdn2.gsmarena.com/vv/pics/sony/sony-xperia-1-v-1.jpg"},
        {"name": "Asus ROG Phone 8", "price": 25000000, "category": "điện thoại", "img": "https://fdn2.gsmarena.com/vv/pics/asus/asus-rog-phone-8-1.jpg"},
        {"name": "Realme GT 5", "price": 12000000, "category": "điện thoại", "img": "https://fdn2.gsmarena.com/vv/pics/realme/realme-gt5-1.jpg"},
        {"name": "Vivo X100 Pro", "price": 19000000, "category": "điện thoại", "img": "https://fdn2.gsmarena.com/vv/pics/vivo/vivo-x100-pro-1.jpg"},
        {"name": "Nokia G42 5G", "price": 5500000, "category": "điện thoại", "img": "https://fdn2.gsmarena.com/vv/pics/nokia/nokia-g42-5g-1.jpg"},
        {"name": "iPhone 16 Pro Max", "price": 34490000, "category": "điện thoại", "img": "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-16-pro-max-1.jpg"},
        {"name": "iPhone 15 Pro", "price": 24900000, "category": "điện thoại", "img": "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-15-pro-1.jpg"}
    ]

    
    # 3. Nạp vào database
    # hellokitty
    for p in phones:
        new_p = Product(
            name=p["name"],
            price=p["price"],
            stock=100,
            image_url=p["img"],
            description="Sản phẩm chính hãng, bảo hành 12 tháng. Cam kết chất lượng tốt nhất, lỗi 1 đổi 1 trong 30 ngày đầu sử dụng. Hỗ trợ trả góp 0%.",
            is_active=True
        )
        db.add(new_p)
    
    db.commit()
    return {"message": "Đã cập nhật sản phẩm lên shop!"}

@app.post("/admin/import-from-html")
def import_from_html(data: List[ImportProductItem], admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    count = 0
    for item in data:
        # Kiểm tra trùng tên
        exists = db.query(Product).filter(Product.name == item.name).first()
        if not exists:
            new_p = Product(
                name=item.name,
                price=item.price,
                image_url=item.image_url,
                stock=100,
                is_active=True
            )
            db.add(new_p)
            count += 1
    db.commit()
    return {"message": f"Đã nạp thành công {count} sản phẩm vào SQL!"}

@app.post("/admin/products/{product_id}/hide")
def hide_product(product_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p: raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    p.is_active = False
    db.commit()
    return {"message": "Sản phẩm đã được ẩn"}

@app.post("/admin/products/{product_id}/show")
def show_product(product_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p: raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    p.is_active = True
    db.commit()
    return {"message": "Sản phẩm đã hiện lại"}

@app.delete("/admin/products/{product_id}")
def delete_product(product_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p: raise HTTPException(status_code=404, detail="Không tìm thấy")
    try:
        db.delete(p)
        db.commit()
    except:
        db.rollback()
        p.is_active = False # Nếu dính khóa ngoại thì chỉ ẩn đi
        db.commit()
        return {"message": "Đã ẩn sản phẩm (do có lịch sử đơn hàng)"}
    return {"message": "Xóa thành công"}


# ===================== ORDERS (USER & ADMIN) =====================

# (Đã gộp OrderCreateSchema về 1 định nghĩa duy nhất ở trên, có đủ field voucher_code
#  — trước đây có 1 class OrderCreateSchema TRÙNG TÊN bị khai báo lại ở đây và THIẾU
#  field voucher_code, khiến Python ghi đè lên class gốc. Do đó dòng `if data.voucher_code:`
#  trong create_order() bị AttributeError -> mọi đơn hàng đều lỗi 500 "Lỗi hệ thống khi lưu đơn hàng".)

# 2. API: USER XEM ĐƠN HÀNG CỦA CHÍNH MÌNH (Sửa lỗi 405 & Phân quyền)
@app.get("/orders")
def get_orders_list(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Nếu là Admin -> Cho xem hết (tùy chọn)
    if current_user.email == "honganh@gmail.com":
        return db.query(Order).order_by(Order.id.desc()).all()
    
    # Nếu là User -> Chỉ trả về đơn hàng của chính User đó
    orders = db.query(Order).filter(Order.user_id == current_user.id).order_by(Order.id.desc()).all()
    return orders

# 3. API: TẠO ĐƠN HÀNG (Đã tối ưu check kho)
@app.post("/orders")
def create_order(data: OrderCreateSchema, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not data.items:
        raise HTTPException(status_code=400, detail="Giỏ hàng trống")

    product_map = {}
    for it in data.items:
        p = db.query(Product).filter(Product.id == it.product_id).first() 
        if not p:
            raise HTTPException(status_code=400, detail=f"Sản phẩm ID {it.product_id} không tồn tại")
        if it.quantity > p.stock:
            raise HTTPException(status_code=400, detail=f"Sản phẩm '{p.name}' chỉ còn {p.stock}")
        product_map[it.product_id] = p

    try:
        # Tạo đơn hàng mới (Trạng thái mặc định là Chờ xác nhận)
        order = Order(
            user_id=user.id,
            status="Chờ xác nhận",
            shipping_address=getattr(data, 'shipping_address', '') or '',
            phone_number=getattr(data, 'phone_number', '') or '',
            note=getattr(data, 'customer_name', '') or '',
            created_at=now_vn()
        )
        db.add(order)
        db.flush()

        # Server-side discount & coupon verification
        now = now_vn()
        valid_coupon = None
        if data.voucher_code:
            c = db.query(Coupon).filter(Coupon.code == data.voucher_code.strip().upper(), Coupon.is_active == True).first()
            if c and (not c.expires_at or c.expires_at >= now) and (c.user_id is None or c.user_id == user.id):
                valid_coupon = c

        for it in data.items:
            p = product_map[it.product_id]
            p.stock -= it.quantity # Trừ kho
            
            # Check active flash sale for product
            fs = db.query(FlashSale).filter(
                FlashSale.product_id == p.id,
                FlashSale.is_active == True,
                FlashSale.start_time <= now,
                FlashSale.end_time >= now,
            ).first()
            base_price = fs.sale_price if fs else p.price
            
            # Apply coupon if valid
            if valid_coupon:
                if valid_coupon.discount_type == "percent":
                    saved_price = int(base_price * max(0, (100 - valid_coupon.discount_value)) / 100)
                elif valid_coupon.discount_type == "fixed":
                    saved_price = max(0, base_price - valid_coupon.discount_value)
                else:
                    saved_price = base_price
            else:
                saved_price = base_price
            
            oi = OrderItem(
                order_id=order.id,
                product_id=p.id,
                quantity=it.quantity,
                unit_price=saved_price
            )
            db.add(oi)

        db.commit() 
        try:
            email_items = [{"name": product_map[it.product_id].name, "quantity": it.quantity, "unit_price": oi.unit_price} for it, oi in zip(data.items, order.items)]
            total_val = sum(it["unit_price"] * it["quantity"] for it in email_items)
            send_order_confirmation_email(user.email, order.id, email_items, total_val)
        except Exception:
            pass  # tuyệt đối không để lỗi email làm hỏng response tạo đơn
        return {"message": "Tạo đơn hàng thành công", "order_id": order.id, "id": order.id, "status": "Chờ xác nhận"}

    except Exception as e:
        db.rollback()
        print(f">>> [LỖI TẠO ĐƠN]: {str(e)}")
        raise HTTPException(status_code=500, detail="Lỗi hệ thống khi lưu đơn hàng")

# 4. API: ADMIN XEM TOÀN BỘ ĐƠN HÀNG (Chi tiết)
@app.get("/admin/orders")
async def get_all_orders_admin(db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    try:
        db.expire_all() 
        orders = db.query(Order).order_by(Order.created_at.desc()).all()
        
        print(f">>> [DEBUG ADMIN] Tìm thấy {len(orders)} đơn hàng.")

        result = []
        for o in orders:
            try:
                # Tính tổng tiền từ danh sách OrderItems
                total = sum(i.quantity * i.unit_price for i in o.items) if o.items else 0
                
                result.append({
                    "id": o.id,
                    "email": o.user.email if o.user else "Khách vãng lai",
                    "status": o.status or "NEW",
                    "total": total,
                    "created_at": o.created_at.strftime("%Y-%m-%d %H:%M") if o.created_at else "N/A",
                    "items": [
                        {
                            "name": i.product.name if hasattr(i, 'product') and i.product else f"SP #{i.product_id}",
                            "qty": i.quantity, 
                            "price": i.unit_price
                        } 
                        for i in o.items
                    ]
                })
            except Exception as e_item:
                print(f">>> [LỖI DÒNG] Đơn hàng #{o.id}: {e_item}")
        
        return result

    except Exception as e:
        print(f">>> [LỖI TỔNG] API Admin thất bại: {str(e)}")
        return []

# 5. API: ADMIN CẬP NHẬT TRẠNG THÁI ĐƠN HÀNG
@app.put("/admin/orders/{order_id}/status")
async def update_order_status(
    order_id: int, 
    new_status: str, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(require_admin)
):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Đơn hàng không tồn tại")
    
    # Cập nhật trạng thái (Ví dụ: PROCESSING, SHIPPING, COMPLETED, CANCELLED)
    order.status = new_status
    db.commit()
    print(f">>> [ADMIN] Đã đổi trạng thái đơn #{order_id} sang {new_status}")
    return {"message": "Cập nhật trạng thái thành công", "new_status": new_status}


@app.get("/orders/me")
def my_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    orders = db.query(Order).filter(Order.user_id == user.id).order_by(Order.id.desc()).all()
    result = []
    for o in orders:
        total = sum(i.quantity * i.unit_price for i in o.items)
        result.append({
            "id": o.id,
            "status": o.status or "Chờ xác nhận",
            "date": o.created_at.strftime("%H:%M %d/%m/%Y") if o.created_at else "N/A",
            "total": total,
            "shipping_address": o.shipping_address or "",
            "phone_number": o.phone_number or "",
            "customer_name": o.note or "",
            "items": [
                {
                    "name": i.product.name if i.product else f"Sản phẩm #{i.product_id}",
                    "qty": i.quantity,
                    "price": i.unit_price
                }
                for i in o.items
            ]
        })
    return result


# ===================== ORDERS (STAFF/ADMIN) =====================
@app.get("/staff/orders")
def staff_list_orders(user: User = Depends(require_staff_or_admin), db: Session = Depends(get_db)):
    orders = db.query(Order).order_by(Order.id.desc()).all()
    result = []
    for o in orders:
        total = sum(i.quantity * i.unit_price for i in o.items)
        result.append({
            "id": o.id,
            "user_id": o.user_id,
            "status": o.status,
            "created_at": o.created_at,
            "updated_at": o.updated_at,
            "total": total,
        })
    return result


@app.put("/staff/orders/{order_id}/status")
def staff_update_order_status(
    order_id: int,
    data: OrderStatusUpdateSchema,
    user: User = Depends(require_staff_or_admin),
    db: Session = Depends(get_db),
):
    new_status = data.status.strip().upper()
    if new_status not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail=f"Status không hợp lệ: {sorted(list(ORDER_STATUSES))}")

    o = db.query(Order).filter(Order.id == order_id).first()
    if not o:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")

    allowed = {
        ORDER_NEW: {ORDER_CONFIRMED, ORDER_CANCELED},
        ORDER_CONFIRMED: {ORDER_SHIPPED, ORDER_CANCELED},
        ORDER_SHIPPED: {ORDER_DONE},
        ORDER_DONE: set(),
        ORDER_CANCELED: set(),
    }
    if new_status not in allowed.get(o.status, set()):
        raise HTTPException(status_code=400, detail=f"Không thể chuyển từ {o.status} -> {new_status}")

    # nếu hủy -> hoàn kho
    if new_status == ORDER_CANCELED:
        for i in o.items:
            p = db.query(Product).filter(Product.id == i.product_id).first()
            if p:
                p.stock += i.quantity

    o.status = new_status
    o.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Cập nhật trạng thái thành công", "order_id": o.id, "status": o.status}

# Tìm đến phần Schema (BaseModel) và sửa lại cho chuẩn:
class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int
    unit_price: float

class OrderCreate(BaseModel):
    items: List[OrderItemCreate]
    shipping_address: str
    phone_number: str

@app.get("/admin/api/orders")
async def get_admin_orders(db: Session = Depends(get_db)):
    orders = db.query(Order).order_by(Order.created_at.desc()).all()
    result = []
    for o in orders:
        total = sum(item.unit_price * item.quantity for item in o.items)
        result.append({
            "id": o.id,
            "email": o.user.email if o.user else "Khách vãng lai",
            "customer_name": o.note or "",
            "phone_number": o.phone_number or "",
            "shipping_address": o.shipping_address or "",
            "total": total,
            "status": o.status or "Chờ xác nhận",
            "created_at": o.created_at.isoformat() if o.created_at else "",
            "items": [
                {
                    "name": item.product.name if item.product else f"SP #{item.product_id}",
                    "qty": item.quantity,
                    "price": item.unit_price
                }
                for item in o.items
            ]
        })
    return result

# API cập nhật trạng thái đơn (dùng cho admin.html và order-history.html)
@app.put("/admin/api/orders/{order_id}/status")
async def update_order_status_api(
    order_id: int, 
    new_status: str = Query(...),
    db: Session = Depends(get_db)
):
    db_order = db.query(Order).filter(Order.id == order_id).first()
    if not db_order: raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
    db_order.status = new_status
    db_order.updated_at = now_vn()
    db.commit()
    return {"status": "success", "new_status": new_status}

# ===================== REPORTS (ADMIN) =====================
@app.get("/admin/reports/revenue")
def report_revenue(
    start: date,
    end: date,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())

    orders = db.query(Order).filter(
        Order.status == ORDER_DONE,
        Order.updated_at >= start_dt,
        Order.updated_at <= end_dt
    ).all()

    revenue = 0
    total_orders = 0
    for o in orders:
        total_orders += 1
        revenue += sum(i.quantity * i.unit_price for i in o.items)

    return {
        "start": start,
        "end": end,
        "total_orders_done": total_orders,
        "revenue": revenue,
    }

@app.get("/dev/set-admin")
def set_admin(db: Session = Depends(get_db)):
    hashed = get_password_hash(ADMIN_PASSWORD)

    user = db.query(User).filter(User.email == ADMIN_EMAIL).first()

    if user:
        user.password = hashed
        user.role = ROLE_ADMIN
        user.status = STATUS_ACTIVE
    else:
        user = User(
            email=ADMIN_EMAIL,
            password=hashed,
            role=ROLE_ADMIN,
            status=STATUS_ACTIVE
        )
        db.add(user)

    db.commit()

    return {
        "success": True,
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
        "admin_key": ADMIN_SECRET_KEY
    }

@app.get("/admin/reports/top-products")
def report_top_products(
    start: date,
    end: date,
    limit: int = 10,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())

    orders = db.query(Order).filter(
        Order.status == ORDER_DONE,
        Order.updated_at >= start_dt,
        Order.updated_at <= end_dt
    ).all()

    qty_map: Dict[int, int] = {}
    for o in orders:
        for i in o.items:
            qty_map[i.product_id] = qty_map.get(i.product_id, 0) + i.quantity

    top = sorted(qty_map.items(), key=lambda x: x[1], reverse=True)[:max(1, limit)]

    results = []
    for product_id, qty in top:
        p = db.query(Product).filter(Product.id == product_id).first()
        if p:
            results.append({"product_id": p.id, "name": p.name, "quantity_sold": qty})

    return {"start": start, "end": end, "top": results}
# Đảm bảo các dòng này nằm sát lề trái, không thụt đầu dòng
# ==========================================
# API QUẢN LÝ ĐƠN HÀNG (DÀNH CHO ADMIN & KHÁCH)
# ==========================================

# 1. Khách gửi đơn lên Server (Dùng trong shop_3_2.html)
@app.post("/api/orders")
async def create_new_order(data: dict, db: Session = Depends(get_db)):
    try:
        # Tìm user để gán đơn hàng (Ưu tiên user_id từ data hoặc user đầu tiên)
        u_id = data.get('user_id')
        if not u_id:
            first_user = db.query(User).first()
            u_id = first_user.id if first_user else 1

        # Tạo đơn hàng mới
        new_order = Order(
            user_id=u_id,
            status="Chờ xác nhận", # Trạng thái ban đầu
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(new_order)
        db.commit()
        db.refresh(new_order)
        
        # Lưu từng món hàng vào chi tiết đơn
        for item in data.get('items', []):
            order_item = OrderItem(
                order_id=new_order.id,
                product_id=int(item['product_id']),
                quantity=int(item.get('quantity', 1)),
                unit_price=int(item['price'])
            )
            db.add(order_item)
        
        db.commit()
        return {"message": "Thành công", "order_id": new_order.id}
    except Exception as e:
        db.rollback()
        return {"error": str(e)}, 500

# 2. Admin lấy danh sách đơn để hiển thị (Dùng trong admin.html)
@app.get("/api/admin/all-orders")
async def admin_get_all_orders(db: Session = Depends(get_db)):
    # Lấy đơn mới nhất lên đầu
    orders = db.query(Order).order_by(Order.id.desc()).all()
    results = []
    for o in orders:
        # Lấy chi tiết sản phẩm
        item_details = []
        for i in o.items:
            p = db.query(Product).filter(Product.id == i.product_id).first()
            item_details.append({
                "name": p.name if p else "Sản phẩm không tồn tại",
                "qty": i.quantity,
                "price": i.unit_price
            })
            
        results.append({
            "id": o.id,
            "email": o.user.email if o.user else "Khách vãng lai",
            "status": o.status,
            "date": o.created_at.strftime("%H:%M %d/%m/%Y"),
            "items": item_details
        })
    return results

# 3. Admin cập nhật trạng thái đơn (Duyệt/Giao/Hủy)
@app.put("/api/admin/update-order/{order_id}")
async def admin_update_status(order_id: int, data: dict, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        return {"error": "Không tìm thấy đơn hàng"}, 404
    
    order.status = data.get('status')
    order.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Cập nhật thành công"}

@app.on_event("startup")
def startup_event():
    db = SessionLocal()
    try:
        # 1. Định nghĩa Admin DUY NHẤT được phép
        super_admin = "honganh@gmail.com"
        admin_pass = "admin123"

        # 2. HẠ QUYỀN tất cả các tài khoản khác đang giữ quyền ADMIN
        # (Để đảm bảo không ai khác ngoài honganh@gmail.com có quyền Admin)
        others = db.query(User).filter(User.role == "ADMIN", User.email != super_admin).all()
        for u in others:
            u.role = "USER" # Chuyển họ về làm người dùng thường
            print(f">>> DA TUOC QUYEN ADMIN CUA: {u.email}")
        db.commit()

        # 3. CẬP NHẬT HOẶC TẠO MỚI Admin chính
        user = db.query(User).filter(User.email == super_admin).first()
        if user:
            user.role = "ADMIN"
            user.status = "ACTIVE"
            user.password = get_password_hash(admin_pass)
            db.commit()
            print(f">>> ADMIN HIEN TAI: {super_admin}")
        else:
            new_admin = User(
                email=super_admin,
                password=get_password_hash(admin_pass),
                role="ADMIN",
                status="ACTIVE"
            )
            db.add(new_admin)
            db.commit()
            print(f">>> DA TAO MOI ADMIN: {super_admin}")

        # 4. AUTO-SEED SAN PHAM neu bang dang trong
        product_count = db.query(Product).count()
        if product_count == 0:
            print(">>> BANG PRODUCTS TRONG — BAT DAU SEED SAN PHAM...")
            seed_data = [
                {"name": "Xiaomi Redmi Note 13", "price": 4590000, "img": "static/a1.jpg"},
                {"name": "iPhone 14 Pro 128GB", "price": 22990000, "img": "static/a2.jpg"},
                {"name": "iPhone 15 Pro Max 512GB", "price": 34990000, "img": "static/a3.jpg"},
                {"name": "Samsung Galaxy A55 5G", "price": 10490000, "img": "static/a4.jpg"},
                {"name": "Samsung Galaxy S24 Ultra", "price": 27990000, "img": "static/a5.jpg"},
                {"name": "Tai nghe AirPods Pro 2", "price": 5990000, "img": "static/a6.jpg"},
                {"name": "MacBook Air M3 2024", "price": 27490000, "img": "static/a7.jpg"},
                {"name": "Dell XPS 13 Plus", "price": 35000000, "img": "static/a8.jpg"},
                {"name": "ASUS ROG Strix G16", "price": 32990000, "img": "static/a9.jpg"},
                {"name": "HP Spectre x360", "price": 29000000, "img": "static/a10.jpg"},
                {"name": "Man hinh Dell UltraSharp 27", "price": 12500000, "img": "static/a11.jpg"},
                {"name": "May in HP LaserJet Pro", "price": 4500000, "img": "static/a12.jpg"},
                {"name": "iPad Pro M4 11 inch", "price": 28490000, "img": "static/a13.jpg"},
                {"name": "Samsung Galaxy Tab S9 Ultra", "price": 22990000, "img": "static/a14.jpg"},
                {"name": "Chuot Logitech MX Master 3S", "price": 2490000, "img": "https://images.unsplash.com/photo-1527864550417-7fd91fc51a46?q=80&w=600&auto=format&fit=crop"},
                {"name": "Man hinh Gaming Samsung", "price": 6500000, "img": "https://images.unsplash.com/photo-1616763355548-1b606f439f86?w=600&h=600&fit=crop"},
                {"name": "Man hinh Dell 24 inch", "price": 3500000, "img": "https://images.unsplash.com/photo-1547119957-637f8679db1e?w=600&h=600&fit=crop"},
                {"name": "May cu iPhone 15", "price": 15000000, "img": "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-15-1.jpg"},
                {"name": "iPhone 11 cu", "price": 6500000, "img": "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-11-1.jpg"},
                {"name": "Samsung S21 cu", "price": 7000000, "img": "https://fdn2.gsmarena.com/vv/pics/samsung/samsung-galaxy-s21-5g-1.jpg"},
                {"name": "Laptop Dell cu", "price": 9000000, "img": "https://images.unsplash.com/photo-1588702547919-26089e690ecc?w=600&h=600&fit=crop"},
                {"name": "Huawei MatePad", "price": 6500000, "img": "https://fdn2.gsmarena.com/vv/pics/huawei/huawei-matepad-11-2023-1.jpg"},
                {"name": "iPad Mini 6", "price": 12000000, "img": "https://fdn2.gsmarena.com/vv/pics/apple/apple-ipad-mini-2021-1.jpg"},
                {"name": "Nokia T21", "price": 5000000, "img": "https://fdn2.gsmarena.com/vv/pics/nokia/nokia-t21-1.jpg"},
                {"name": "Casio G-Shock Smart", "price": 4000000, "img": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=600&h=600&fit=crop"},
                {"name": "Oppo Watch X", "price": 8500000, "img": "https://fdn2.gsmarena.com/vv/pics/oppo/oppo-watch-x-1.jpg"},
                {"name": "Xiaomi Watch S3", "price": 3500000, "img": "https://fdn2.gsmarena.com/vv/pics/xiaomi/xiaomi-watch-s3-1.jpg"},
                {"name": "Apple Watch Ultra 2", "price": 21000000, "img": "https://fdn2.gsmarena.com/vv/pics/apple/apple-watch-ultra2-1.jpg"},
                {"name": "Samsung Watch 7 Ultra", "price": 16000000, "img": "https://fdn2.gsmarena.com/vv/pics/samsung/samsung-galaxy-watch-ultra-1.jpg"},
                {"name": "May anh", "price": 250000, "img": "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=600&h=600&fit=crop"},
                {"name": "Microphone Shure", "price": 5000000, "img": "https://images.unsplash.com/photo-1590602847861-f357a9332bbc?w=600&h=600&fit=crop"},
                {"name": "Webcam Logitech C922", "price": 2200000, "img": "https://images.unsplash.com/photo-1587825140708-dfaf72ae4b04?w=600&h=600&fit=crop"},
                {"name": "Tui chong soc Laptop", "price": 350000, "img": "https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=600&h=600&fit=crop"},
                {"name": "Ban phim co AKKO", "price": 1800000, "img": "https://images.unsplash.com/photo-1618384887929-16ec33fab9ef?w=600&h=600&fit=crop"},
                {"name": "Sac du phong Anker 20k", "price": 1200000, "img": "https://images.unsplash.com/photo-1609091839311-d5365f9ff1c5?w=600&h=600&fit=crop"},
                {"name": "Dell XPS 15", "price": 45000000, "img": "https://images.unsplash.com/photo-1593642632559-0c6d3fc62b89?w=600&h=600&fit=crop"},
                {"name": "HP Spectre x360 Pro", "price": 32000000, "img": "https://images.unsplash.com/photo-1517336714731-489689fd1ca8?w=600&h=600&fit=crop"},
                {"name": "Asus Zenbook Duo", "price": 38000000, "img": "https://images.unsplash.com/photo-1541807084-5c52b6b3adef?w=600&h=600&fit=crop"},
                {"name": "Lenovo Legion 5", "price": 28000000, "img": "https://images.unsplash.com/photo-1603302576837-37561b2e2302?w=600&h=600&fit=crop"},
                {"name": "Acer Predator Helios", "price": 35000000, "img": "https://images.unsplash.com/photo-1593642634315-48f5414c3ad9?w=600&h=600&fit=crop"},
                {"name": "MSI Katana GF66", "price": 22000000, "img": "https://images.unsplash.com/photo-1587202372634-32705e3bf49c?w=600&h=600&fit=crop"},
                {"name": "Surface Laptop 5", "price": 25000000, "img": "https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=600&h=600&fit=crop"},
                {"name": "LG Gram 17", "price": 31000000, "img": "https://images.unsplash.com/photo-1525547719571-a2d4ac8945e2?w=600&h=600&fit=crop"},
                {"name": "Gigabyte Aero 16", "price": 42000000, "img": "https://images.unsplash.com/photo-1611078489935-0cb964de46d6?w=600&h=600&fit=crop"},
                {"name": "Huawei MateBook X", "price": 29000000, "img": "https://images.unsplash.com/photo-1484788984921-03950022c9ef?w=600&h=600&fit=crop"},
                {"name": "iPhone SE 2022", "price": 9000000, "img": "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-se-2022-1.jpg"},
                {"name": "Redmi Note 13 Pro", "price": 8500000, "img": "https://fdn2.gsmarena.com/vv/pics/xiaomi/xiaomi-redmi-note-13-pro-1.jpg"},
                {"name": "Xiaomi 14 Ultra", "price": 22000000, "img": "https://fdn2.gsmarena.com/vv/pics/xiaomi/xiaomi-14-ultra-1.jpg"},
                {"name": "Google Pixel 9 Pro", "price": 21500000, "img": "https://fdn2.gsmarena.com/vv/pics/google/google-pixel-9-pro-1.jpg"},
                {"name": "iPhone 14 Plus", "price": 18900000, "img": "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-14-plus-1.jpg"},
                {"name": "Samsung Z Fold 6", "price": 41000000, "img": "https://fdn2.gsmarena.com/vv/pics/samsung/samsung-galaxy-z-fold6-1.jpg"},
                {"name": "Samsung Z Flip 6", "price": 26000000, "img": "https://fdn2.gsmarena.com/vv/pics/samsung/samsung-galaxy-z-flip6-1.jpg"},
                {"name": "Sony Xperia 1 V", "price": 23000000, "img": "https://fdn2.gsmarena.com/vv/pics/sony/sony-xperia-1-v-1.jpg"},
                {"name": "Asus ROG Phone 8", "price": 25000000, "img": "https://fdn2.gsmarena.com/vv/pics/asus/asus-rog-phone-8-1.jpg"},
                {"name": "Realme GT 5", "price": 12000000, "img": "https://fdn2.gsmarena.com/vv/pics/realme/realme-gt5-1.jpg"},
                {"name": "Vivo X100 Pro", "price": 19000000, "img": "https://fdn2.gsmarena.com/vv/pics/vivo/vivo-x100-pro-1.jpg"},
                {"name": "Nokia G42 5G", "price": 5500000, "img": "https://fdn2.gsmarena.com/vv/pics/nokia/nokia-g42-5g-1.jpg"},
                {"name": "iPhone 16 Pro Max", "price": 34490000, "img": "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-16-pro-max-1.jpg"},
                {"name": "iPhone 15 Pro", "price": 24900000, "img": "https://fdn2.gsmarena.com/vv/pics/apple/apple-iphone-15-pro-1.jpg"},
            ]
            for item in seed_data:
                db.add(Product(
                    name=item["name"],
                    price=item["price"],
                    stock=100,
                    image_url=item["img"],
                    description="San pham chinh hang, bao hanh 12 thang. Loi 1 doi 1 trong 30 ngay. Ho tro tra gop 0%.",
                    is_active=True
                ))
            db.commit()
            print(f">>> DA SEED {len(seed_data)} SAN PHAM THANH CONG!")
        else:
            print(f">>> BANG PRODUCTS DA CO {product_count} SAN PHAM — BO QUA SEED.")

    except Exception as e:
        print(f">>> LOI STARTUP: {e}")
    finally:
        db.close()
# ===================== API BO SUNG =====================

# 1. Cập nhật sản phẩm (tên, giá, ảnh, mô tả) - Staff & Admin
@app.put("/admin/products/{product_id}/update")
def update_product_info(
    product_id: int,
    data: ProductUpdateSchema,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_staff_or_admin),
    db: Session = Depends(get_db)
):
    p = db.query(Product).filter(Product.id == product_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Không tìm thấy sản phẩm")
    if data.name is not None:
        p.name = data.name.strip()
    if data.price is not None:
        p.price = data.price
    image_changed = data.image_url is not None and data.image_url != p.image_url
    if data.image_url is not None:
        p.image_url = data.image_url
    if data.description is not None:
        p.description = data.description
    if data.stock is not None:
        p.stock = data.stock
    db.commit()
    if image_changed:
        # Ảnh vừa đổi -> encode lại vector cho đúng, chạy ngầm để không làm chậm response
        background_tasks.add_task(_encode_product_image_bg, p.id)
    return {"message": "Đã cập nhật sản phẩm thành công"}


# 2. Thêm sản phẩm mới có xác thực - Staff & Admin
@app.post("/admin/products/new")
def admin_create_product(
    data: ProductCreateSchema,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_staff_or_admin),
    db: Session = Depends(get_db)
):
    p = Product(
        name=data.name.strip(),
        price=data.price,
        image_url=data.image_url or "",
        description=data.description or "",
        stock=data.stock if data.stock is not None else 100,
        is_active=True
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    background_tasks.add_task(_encode_product_image_bg, p.id)
    return {"message": "Đã thêm sản phẩm mới", "id": p.id, "name": p.name}


# 3. Bổ nhiệm / hạ chức user (USER ↔ STAFF) - chỉ Admin
@app.put("/users/{user_id}/set-role")
def set_user_role(
    user_id: int,
    role: str = Query(..., description="USER hoặc STAFF"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Không thể thay đổi vai trò của chính mình")
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Không tìm thấy user")
    if u.role.upper() == ROLE_ADMIN:
        raise HTTPException(status_code=400, detail="Không thể thay đổi quyền của Admin")
    new_role = role.upper()
    if new_role not in {ROLE_USER, ROLE_STAFF}:
        raise HTTPException(status_code=400, detail="Role không hợp lệ (USER hoặc STAFF)")
    u.role = new_role
    db.commit()
    return {"message": f"Đã cập nhật {u.email} → {u.role}"}


# 4. Xóa user - Staff KHÔNG được xóa Admin
@app.delete("/users/{user_id}/safe")
def safe_delete_user(
    user_id: int,
    current_user: User = Depends(require_staff_or_admin),
    db: Session = Depends(get_db)
):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Không thể tự xóa chính mình!")
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Không tìm thấy user")
    if u.role.upper() == ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Không được phép xóa tài khoản Admin!")
    db.delete(u)
    db.commit()
    return {"message": f"Đã xóa {u.email}"}


# 5. Tổng doanh thu - Staff & Admin (chỉ đơn Đã giao)
@app.get("/admin/revenue")
def get_total_revenue(
    user: User = Depends(require_staff_or_admin),
    db: Session = Depends(get_db)
):
    from collections import defaultdict
    done_orders = db.query(Order).filter(Order.status == "Đã giao").all()
    total = 0
    monthly: dict = defaultdict(int)
    for o in done_orders:
        amt = sum(i.quantity * i.unit_price for i in o.items)
        total += amt
        if o.created_at:
            key = o.created_at.strftime("%m/%Y")
            monthly[key] += amt
    return {
        "total_revenue": total,
        "total_orders_done": len(done_orders),
        "monthly": dict(sorted(monthly.items()))
    }



# ===================== REVIEW (ĐÁNH GIÁ ĐƠN HÀNG) =====================

@app.post("/orders/{order_id}/review")
def create_review(
    order_id: int,
    data: ReviewCreateSchema,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.id == order_id, Order.user_id == user.id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Không tìm thấy đơn hàng")
    if order.status != "Đã giao":
        raise HTTPException(status_code=400, detail="Chỉ đánh giá được đơn đã giao")
    existing = db.query(Review).filter(Review.order_id == order_id).first()
    if existing:
        # Cho phép cập nhật lại đánh giá
        existing.rating  = data.rating
        existing.comment = data.comment.strip()
        existing.created_at = now_vn()
        db.commit()
        return {"message": "Đã cập nhật đánh giá", "rating": existing.rating}
    review = Review(
        order_id=order_id,
        rating=data.rating,
        comment=data.comment.strip()
    )
    db.add(review)
    db.commit()
    return {"message": "Đánh giá thành công", "rating": review.rating}


@app.get("/orders/{order_id}/review")
def get_review(
    order_id: int,
    db: Session = Depends(get_db)
):
    review = db.query(Review).filter(Review.order_id == order_id).first()
    if not review:
        return {"reviewed": False}
    return {
        "reviewed":  True,
        "rating":    review.rating,
        "comment":   review.comment,
        "created_at": review.created_at.strftime("%H:%M %d/%m/%Y") if review.created_at else ""
    }



# ===================== WISHLIST =====================

@app.post("/wishlist/toggle")
def wishlist_toggle(data: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    pid = data.get("product_id")
    if not pid:
        raise HTTPException(status_code=400, detail="Thiếu product_id")
    existing = db.query(Wishlist).filter(
        Wishlist.user_id == user.id, Wishlist.product_id == int(pid)
    ).first()
    if existing:
        db.delete(existing)
        db.commit()
        return {"action": "removed"}
    db.add(Wishlist(user_id=user.id, product_id=int(pid)))
    db.commit()
    return {"action": "added"}


@app.get("/wishlist/ids")
def wishlist_ids(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Wishlist.product_id).filter(Wishlist.user_id == user.id).all()
    return [r[0] for r in rows]


@app.get("/wishlist")
def get_wishlist(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Wishlist).filter(Wishlist.user_id == user.id).all()
    result = []
    for w in rows:
        p = w.product
        if p and p.is_active:
            result.append({
                "id": p.id, "name": p.name, "price": p.price,
                "stock": p.stock, "image_url": p.image_url,
                "description": p.description or ""
            })
    return result


@app.get("/admin/wishlist/stats")
def wishlist_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role not in ["ADMIN", "STAFF"]:
        raise HTTPException(status_code=403, detail="Không có quyền")
    from sqlalchemy import func
    rows = db.query(
        Wishlist.product_id,
        func.count(Wishlist.id).label("cnt")
    ).group_by(Wishlist.product_id).order_by(func.count(Wishlist.id).desc()).limit(50).all()
    result = []
    for r in rows:
        p = db.query(Product).filter(Product.id == r.product_id).first()
        if p:
            result.append({
                "product_id": p.id, "name": p.name, "price": p.price,
                "image_url": p.image_url, "stock": p.stock, "wish_count": r.cnt
            })
    return result


# ===================== CHATBOT AI (GEMINI PROXY) =====================
import httpx
import asyncio

# 1. Lấy Key từ Environment của Render (Nếu không có thì dùng Key dự phòng)
# Lưu ý: Bạn nên dán Key vào mục Environment trên Render như tớ hướng dẫn ở trên
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyAJKjMcv0vhlG-KDfeOZGNxtppZ6lyN3B4")

# 2. Sửa lại URL: Dùng bản 1.5-flash để ổn định nhất và sửa lỗi 404
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

# 3. Giữ nguyên System Prompt của bạn (Rất tốt)
CHATBOT_SYSTEM_BASE = (
    "Bạn là Hồng Anh AI - trợ lý bán hàng của shop Trương Hồng Anh chuyên điện thoại, "
    "laptop, tablet, phụ kiện và đồng hồ thông minh chính hãng. "
    "Trả lời thân thiện, ngắn gọn 2-3 câu bằng tiếng Việt có dấu. "
    "Chỉ tư vấn đúng sản phẩm có trong danh sách shop — KHÔNG được tự bịa ra sản phẩm không có. "
    "Nếu shop chưa có mặt hàng khách hỏi → thành thật nói chưa có."
)

def build_chatbot_system(db: Session) -> str:
    """Tạo system prompt ĐỘNG, inject danh sách sản phẩm thực từ DB."""
    try:
        products = db.query(Product).filter(Product.is_active == True).all()
        if products:
            lines = [
                f"- {p.name} | Giá: {int(p.price):,}đ | Tồn kho: {p.stock}".replace(",", ".")
                for p in products
            ]
            catalog = (
                "\n\nDANH SÁCH SẢN PHẨM HIỆN CÓ TRONG SHOP (CHỈ tư vấn các sản phẩm này):\n"
                + "\n".join(lines)
                + "\n\nNẾU khách hỏi sản phẩm KHÔNG có trong danh sách → trả lời thật thà là shop chưa có mặt hàng đó."
            )
            return CHATBOT_SYSTEM_BASE + catalog
    except Exception:
        pass
    return CHATBOT_SYSTEM_BASE

class ChatMessage(BaseModel):
    role: str       # "user" hoặc "assistant"
    content: str
