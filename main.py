from fastapi import FastAPI, HTTPException, Depends, Request, Query
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, List, Dict, Any

from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey
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

from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional, List, Dict, Set
import os


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
    return RedirectResponse(url="/login")

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


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String, default=ORDER_NEW)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True)

    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)

    quantity = Column(Integer, nullable=False)
    unit_price = Column(Integer, nullable=False)

    order = relationship("Order", back_populates="items")


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
{"name": "Samsung Galaxy S25 Edge 5G 512GB", "price": 22490000, "img": "https://cdn.tgdd.vn/2026/02/timerseo/335955-600x600.jpg"},
        {"name": "iPhone 16 Pro Max 256GB", "price": 34490000, "img": "https://cdn.tgdd.vn/Products/Images/42/329149/iphone-16-pro-max-titan-sa-mac-thumb-600x600.jpg"},
        {"name": "iPhone 16 128GB", "price": 22290000, "img": "https://cdn.tgdd.vn/Products/Images/42/329142/iphone-16-hong-thumb-600x600.jpg"},
        {"name": "Samsung Galaxy S24 Ultra 256GB", "price": 27990000, "img": "https://cdn.tgdd.vn/Products/Images/42/307174/samsung-galaxy-s24-ultra-grey-thumb-600x600.jpg"},
        {"name": "OPPO Reno12 F 5G", "price": 9490000, "img": "https://cdn.tgdd.vn/Products/Images/42/327310/oppo-reno12-f-xanh-thumb-600x600.jpg"},
        {"name": "Xiaomi Redmi Note 13 Pro", "price": 8690000, "img": "https://cdn.tgdd.vn/Products/Images/42/320037/xiaomi-redmi-note-13-pro-4g-xanh-thumb-600x600.jpg"},
        {"name": "iPhone 15 128GB", "price": 19490000, "img": "https://cdn.tgdd.vn/Products/Images/42/281570/iphone-15-xanh-duong-thumb-600x600.jpg"},
        {"name": "Samsung Galaxy A55 5G 128GB", "price": 10490000, "img": "https://cdn.tgdd.vn/Products/Images/42/322096/samsung-galaxy-a55-5g-xanh-thumb-1-600x600.jpg"},
        {"name": "iPhone 13 128GB", "price": 13490000, "img": "https://cdn.tgdd.vn/Products/Images/42/250258/iphone-13-pink-thumb-600x600.jpg"},
        {"name": "Xiaomi 14T 12GB/256GB", "price": 12990000, "img": "https://cdn.tgdd.vn/Products/Images/42/329562/xiaomi-14t-den-thumb-600x600.jpg"},
        {"name": "Apple Watch Series 10 42mm", "price": 10990000, "img": "https://cdn.tgdd.vn/Products/Images/7077/329241/apple-watch-s10-42mm-nhom-den-day-cao-su-den-thumb-600x600.jpg"},
        {"name": "Samsung Galaxy Z Fold6 5G", "price": 41990000, "img": "https://cdn.tgdd.vn/Products/Images/42/320145/samsung-galaxy-z-fold6-xam-thumb-600x600.jpg"},
        {"name": "iPad Pro M4 11 inch WiFi", "price": 28490000, "img": "https://cdn.tgdd.vn/Products/Images/522/325251/ipad-pro-m4-11-inch-wifi-den-thumb-600x600.jpg"},
        {"name": "Tai nghe AirPods 3 MagSafe", "price": 4290000, "img": "https://cdn.tgdd.vn/Products/Images/54/251505/airpods-3-magsafe-check-thumb-600x600.jpg"},
        {"name": "Samsung Galaxy Watch Ultra", "price": 16990000, "img": "https://cdn.tgdd.vn/Products/Images/7077/322303/samsung-galaxy-watch-ultra-47mm-trang-thumb-600x600.jpg"},
        {"name": "Xiaomi Redmi 14C 4GB", "price": 2990000, "img": "https://cdn.tgdd.vn/Products/Images/42/329251/xiaomi-redmi-14c-den-thumb-600x600.jpg"},
        {"name": "OPPO Reno12 Pro 5G", "price": 16990000, "img": "https://cdn.tgdd.vn/Products/Images/42/325413/oppo-reno12-pro-bac-thumb-600x600.jpg"},
        {"name": "Vivo V40 Lite", "price": 7990000, "img": "https://cdn.tgdd.vn/Products/Images/42/330364/vivo-v40-lite-bac-thumb-600x600.jpg"},
        {"name": "iPhone 14 Pro 128GB", "price": 22990000, "img": "https://cdn.tgdd.vn/Products/Images/42/289691/iphone-14-pro-den-thumb-600x600.jpg"},
        {"name": "Laptop MacBook Air M3 13 inch", "price": 27490000, "img": "https://cdn.tgdd.vn/Products/Images/44/322627/apple-macbook-air-m3-2024-8gb-256gb-thumb-600x600.jpg"},
        {"name": "Cáp Type C - Type C 1m Apple", "price": 590000, "img": "https://cdn.tgdd.vn/Products/Images/58/315181/cap-type-c-type-c-1m-apple-mqw73-trang-thumb-600x600.jpg"},
        {"name": "Samsung Galaxy Buds3", "price": 3990000, "img": "https://cdn.tgdd.vn/Products/Images/54/324151/samsung-galaxy-buds3-bac-thumb-600x600.jpg"},
        {"name": "iPad Air M2 11 inch WiFi", "price": 16490000, "img": "https://cdn.tgdd.vn/Products/Images/522/325243/ipad-air-m2-11-inch-wifi-xanh-thumb-600x600.jpg"},
        {"name": "OPPO Watch X", "price": 8490000, "img": "https://cdn.tgdd.vn/Products/Images/7077/322301/oppo-watch-x-den-thumb-600x600.jpg"},
        {"name": "Sạc dự phòng MagSafe Apple", "price": 2690000, "img": "https://cdn.tgdd.vn/Products/Images/57/245842/sac-du-phong-magsafe-battery-pack-apple-mjwy3-trang-thumb-600x600.jpg"},
        {"name": "iPhone 15 Pro Max 512GB", "price": 34990000, "img": "https://cdn.tgdd.vn/Products/Images/42/305658/iphone-15-pro-max-blue-thumb-600x600.jpg"},
        {"name": "Tai nghe Marshall Minor III", "price": 2990000, "img": "https://cdn.tgdd.vn/Products/Images/54/273391/tai-nghe-bluetooth-true-wireless-marshall-minor-3-den-thumb-600x600.jpg"},
        {"name": "Xiaomi Redmi Buds 5 Pro", "price": 1790000, "img": "https://cdn.tgdd.vn/Products/Images/54/319696/xiaomi-redmi-buds-5-pro-den-thumb-600x600.jpg"},
        {"name": "Apple Watch Ultra 2", "price": 21490000, "img": "https://cdn.tgdd.vn/Products/Images/7077/315183/apple-watch-ultra-2-49mm-vien-titan-day-alpine-size-m-xanh-duong-thumb-600x600.jpg"},
        {"name": "Loa Bluetooth Marshall Emberton II", "price": 4490000, "img": "https://cdn.tgdd.vn/Products/Images/2162/285523/marshall-emberton-ii-den-thumb-600x600.jpg"},
        {"name": "iPhone 16 Pro 128GB", "price": 28490000, "img": "https://cdn.tgdd.vn/Products/Images/42/329148/iphone-16-pro-trang-thumb-600x600.jpg"},
        {"name": "Samsung Galaxy Z Flip6 256GB", "price": 26990000, "img": "https://cdn.tgdd.vn/Products/Images/42/320146/samsung-galaxy-z-flip6-xanh-duong-thumb-600x600.jpg"},
        {"name": "Xiaomi Pad 6 8GB/256GB", "price": 9490000, "img": "https://cdn.tgdd.vn/Products/Images/522/305886/xiaomi-pad-6-xam-thumb-600x600.jpg"},
        {"name": "OPPO Pad Neo WiFi", "price": 7490000, "img": "https://cdn.tgdd.vn/Products/Images/522/321151/oppo-pad-neo-wifi-thumb-600x600.jpg"},
        {"name": "Realme Note 50 4GB/128GB", "price": 2890000, "img": "https://cdn.tgdd.vn/Products/Images/42/320035/realme-note-50-4gb-128gb-xanh-thumb-600x600.jpg"},
        {"name": "iPhone 12 64GB", "price": 11990000, "img": "https://cdn.tgdd.vn/Products/Images/42/213031/iphone-12-trang-thumb-600x600.jpg"},
        {"name": "Samsung Galaxy Tab S9 FE WiFi", "price": 8990000, "img": "https://cdn.tgdd.vn/Products/Images/522/315182/samsung-galaxy-tab-s9-fe-wifi-xam-thumb-600x600.jpg"},
        {"name": "Vivo V30 5G 12GB/512GB", "price": 13490000, "img": "https://cdn.tgdd.vn/Products/Images/42/322306/vivo-v30-xanh-thumb-600x600.jpg"},
        {"name": "Nokia G42 5G", "price": 5490000, "img": "https://cdn.tgdd.vn/Products/Images/42/313506/nokia-g42-5g-tim-thumb-600x600.jpg"},
        {"name": "Apple Pencil Pro", "price": 3490000, "img": "https://cdn.tgdd.vn/Products/Images/42/325255/apple-pencil-pro-mx2d3-trang-thumb-600x600.jpg"},
        {"name": "Ốp lưng iPhone 16 Pro Max Silicone", "price": 1490000, "img": "https://cdn.tgdd.vn/Products/Images/60/329243/op-lung-iphone-16-pro-max-silicone-magsafe-den-thumb-600x600.jpg"},
        {"name": "Samsung Galaxy A35 5G", "price": 8290000, "img": "https://cdn.tgdd.vn/Products/Images/42/320036/samsung-galaxy-a35-5g-xanh-thumb-600x600.jpg"},
        {"name": "Xiaomi Redmi Note 13", "price": 4590000, "img": "https://cdn.tgdd.vn/Products/Images/42/309831/xiaomi-redmi-note-13-den-thumb-600x600.jpg"},
        {"name": "Tai nghe Sony WH-1000XM5", "price": 7990000, "img": "https://cdn.tgdd.vn/Products/Images/54/281313/sony-wh-1000xm5-den-thumb-600x600.jpg"},
        {"name": "iPad Mini 6 WiFi 64GB", "price": 12490000, "img": "https://cdn.tgdd.vn/Products/Images/522/249117/ipad-mini-6-wifi-tim-thumb-600x600.jpg"},
        {"name": "Apple Watch SE 2023 40mm", "price": 5990000, "img": "https://cdn.tgdd.vn/Products/Images/7077/315184/apple-watch-se-2023-40mm-vien-nhom-day-the-thao-thumb-600x600.jpg"},
        {"name": "Bàn phím Magic Keyboard cho iPad Pro", "price": 8990000, "img": "https://cdn.tgdd.vn/Products/Images/4547/325253/ban-phim-magic-keyboard-cho-ipad-pro-11-inch-m4-den-thumb-600x600.jpg"},
        {"name": "Samsung Galaxy M54 5G", "price": 8990000, "img": "https://cdn.tgdd.vn/Products/Images/42/275367/samsung-galaxy-m54-bac-thumb-600x600.jpg"},
        {"name": "Tai nghe JBL Live Pro 2", "price": 2990000, "img": "https://cdn.tgdd.vn/Products/Images/54/282772/tai-nghe-bluetooth-true-wireless-jbl-live-pro-2-xanh-thumb-600x600.jpg"},
        {"name": "Loa Bluetooth Sony SRS-XE200", "price": 1990000, "img": "https://cdn.tgdd.vn/Products/Images/2162/285517/sony-srs-xe200-den-thumb-600x600.jpg"}
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

class OrderCreateSchema(BaseModel):
    items: List[OrderItemSchema]

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
        # Tạo đơn hàng mới (Trạng thái mặc định là NEW)
        order = Order(user_id=user.id, status="NEW", created_at=datetime.utcnow())
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
        return {"message": "Tạo đơn hàng thành công", "order_id": order.id, "status": "NEW"}

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
            "status": o.status,
            "created_at": o.created_at,
            "updated_at": o.updated_at,
            "total": total,
            "items": [
                {"product_id": i.product_id, "quantity": i.quantity, "unit_price": i.unit_price}
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