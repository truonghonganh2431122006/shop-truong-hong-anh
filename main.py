from fastapi import FastAPI, HTTPException, Depends, Request, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, List, Dict, Any
import uvicorn
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Set
import os

from pathlib import Path
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Text, Float
)
from sqlalchemy.orm import sessionmaker, declarative_base, Session, relationship

from passlib.context import CryptContext
from jose import jwt, JWTError

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


# --- QUAY LẠI SQLITE CHO NHANH ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./app.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}
)
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
    ensure_password_ok(pw)
    return pwd_context.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    ensure_password_ok(pw)
    return pwd_context.verify(pw, hashed)


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
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

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


# ===================== SCHEMAS =====================
class RegisterSchema(BaseModel):
    email: EmailStr
    password: str


class LoginSchema(BaseModel):
    email: EmailStr
    password: str


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


class CartItemSchema(BaseModel):
    product_id: int
    quantity: int = Field(ge=1)


class OrderCreateSchema(BaseModel):
    items: List[CartItemSchema]
    shipping_address: Optional[str] = ""
    phone_number: Optional[str] = ""
    customer_name: Optional[str] = ""


class OrderStatusUpdateSchema(BaseModel):
    status: str


# ===================== DB INIT =====================
Base.metadata.create_all(bind=engine)


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


seed_admin()


# ===================== DEPENDENCIES =====================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
    
    if user_role == "ADMIN":
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

# 2. Hàm xóa chuẩn duy nhất
@app.delete("/admin/delete")
def delete_user(data: EmailRequest, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
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
def create_product(product_data: ProductCreate, db: Session = Depends(get_db)):
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
    return new_product

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
    for p in phones:
        new_p = Product(
            name=p["name"],
            price=p["price"],
            stock=100,
            image_url=p["img"],
            description="Sản phẩm đã được update lên shop rồi Hồng Anh nhé !",
            is_active=True
        )
        db.add(new_p)
    
    db.commit()
    return {"message": "Đã biến Shop thành Thế Giới Di Động thành công!"}

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

# 1. SCHEMAS (Giữ để không lỗi 422)
class OrderItemSchema(BaseModel):
    product_id: int
    quantity: int 

#helloh
class OrderCreateSchema(BaseModel):
    items: List[CartItemSchema]
    shipping_address: Optional[str] = ""
    phone_number: Optional[str] = ""
    customer_name: Optional[str] = ""

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
            created_at=datetime.now()
        )
        db.add(order)
        db.flush()

        for it in data.items:
            p = product_map[it.product_id]
            p.stock -= it.quantity # Trừ kho
            
            oi = OrderItem(
                order_id=order.id,
                product_id=p.id,
                quantity=it.quantity,
                unit_price=p.price
            )
            db.add(oi)

        db.commit() 
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

# API Cập nhật trạng thái đơn hàng
@app.post("/admin/api/orders/{order_id}/status")
async def update_order_status(order_id: int, data: Dict[str, str], db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order: raise HTTPException(404, "Không thấy đơn")
    order.status = data.get("status")
    db.commit()
    return {"msg": "Success"}

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
        # --- THAY ĐỔI THÔNG TIN Ở ĐÂY ---
        admin_email = "honganh@gmail.com"  # Email mới của bạn
        admin_pass = "admin123"           # Mật khẩu mới của bạn
        # -------------------------------

        user = db.query(User).filter(User.email == admin_email).first()
        
        if user:
            # Nếu đã có email này, cập nhật mật khẩu và quyền
            user.role = "ADMIN"
            user.status = "ACTIVE"
            user.password = get_password_hash(admin_pass) # Dùng hàm băm pass có sẵn ở đầu file
            db.commit()
            print(f">>> HE THONG: DA CAP NHAT QUYEN ADMIN CHO {admin_email}")
        else:
            # Nếu chưa có, tạo mới hoàn toàn
            new_admin = User(
                email=admin_email,
                password=get_password_hash(admin_pass),
                role="ADMIN",
                status="ACTIVE"
            )
            db.add(new_admin)
            db.commit()
            print(f">>> HE THONG: DA TAO MOI TK ADMIN: {admin_email} / {admin_pass}")
            
    except Exception as e:
        print(f">>> LOI STARTUP: {e}")
    finally:
        db.close()

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

    except Exception as e:
        print(f">>> LOI STARTUP: {e}")
    finally:
        db.close()
# --- PHẢI NẰM Ở CUỐI FILE main.py ---
if __name__ == "__main__":
    # Render cấp cổng nào mình chạy cổng đó
    port = int(os.environ.get("PORT", 10000))
    # Host 0.0.0.0 là bắt buộc để Render "nhìn" thấy app
    uvicorn.run(app, host="0.0.0.0", port=port)