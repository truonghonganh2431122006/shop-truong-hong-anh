# Shop Trương Hồng Anh — Backend Server

FastAPI Shop Backend (login, admin, products, orders, RAG Chatbot AI)

---

## Tính Năng

- 🛒 Bán hàng: sản phẩm, giỏ hàng, đặt hàng, lịch sử đơn hàng
- 👤 Tài khoản: đăng ký OTP qua email, đăng nhập JWT, quên mật khẩu
- 👑 Admin/Staff: quản lý sản phẩm, đơn hàng, khuyến mãi, flash sale
- 🔍 Tìm kiếm bằng ảnh (CLIP)
- 🤖 **Chatbot AI với RAG** (Retrieval-Augmented Generation) — *tính năng mới*

---

## 🤖 Chatbot AI RAG

### Tổng quan

Chatbot **Hồng Anh AI** sử dụng RAG (Retrieval-Augmented Generation):
1. Câu hỏi của người dùng được nhúng thành vector (Gemini Embedding API).
2. Vector store (`vector_store.json`) được tìm kiếm bằng cosine similarity.
3. Top 5 đoạn văn bản gần nhất được đưa vào system prompt.
4. Gemini AI sinh câu trả lời chỉ dựa trên ngữ cảnh đó — không hallucinate.

### Cấu trúc thư mục RAG

```
shop-server/
├── knowledge-base/          ← Tài liệu tri thức (thêm/sửa tại đây)
│   ├── faq.md               ← Câu hỏi thường gặp
│   ├── chinh-sach.md        ← Chính sách bảo hành, đổi trả, vận chuyển
│   ├── huong-dan-mua-hang.md← Hướng dẫn đặt hàng từng bước
│   └── san-pham.md          ← Thông tin sản phẩm theo dòng
├── embed.py                 ← Script tạo embeddings
├── vector_store.json        ← Vector store (tự sinh, đừng edit tay)
├── .env                     ← Biến môi trường (KHÔNG commit lên Git!)
└── main.py                  ← FastAPI server (RAG endpoints ở cuối file)
```

---

## ⚙️ Cài Đặt & Chạy

### 1. Cài dependencies

```bash
pip install -r requirements.txt
```

### 2. Cấu hình biến môi trường

Tạo file `.env` (hoặc set trực tiếp trên Render):

```env
GEMINI_API_KEY=your_gemini_api_key_here
ADMIN_REINDEX_KEY=your_secret_reindex_key_here
```

> **Lấy Gemini API key:** https://aistudio.google.com/apikey (miễn phí)

### 3. Chạy embedding lần đầu (bắt buộc trước khi dùng chatbot)

```bash
python embed.py
```

Script sẽ:
- Đọc tất cả file `.md`/`.txt` trong `knowledge-base/`
- Chia nhỏ thành chunks ~400 từ
- Gọi Gemini Embedding API để tạo vector cho từng chunk
- Lưu kết quả vào `vector_store.json`

### 4. Chạy server

```bash
uvicorn main:app --reload
```

Hoặc trên Render: server tự chạy theo cấu hình.

---

## 📚 Quản Lý Knowledge Base

### Thêm tài liệu mới

1. Tạo file `.md` hoặc `.txt` trong thư mục `knowledge-base/`
2. Viết nội dung bằng tiếng Việt, rõ ràng, có cấu trúc
3. Chạy lại embedding:

```bash
python embed.py
```

### Cập nhật tài liệu hiện có

1. Sửa file trong `knowledge-base/`
2. Chạy lại: `python embed.py`

### Reindex qua API (production/Render)

Khi đã deploy trên Render, không thể chạy `embed.py` trực tiếp.  
Dùng endpoint `/api/reindex`:

```bash
curl -X POST https://your-app.onrender.com/api/reindex \
  -H "X-Admin-Key: your_secret_reindex_key_here"
```

---

## 🔌 API Endpoints (RAG)

### POST `/api/rag-chat`

Gửi câu hỏi và nhận câu trả lời từ chatbot RAG.

**Request body:**
```json
{
  "question": "Chính sách bảo hành là bao lâu?",
  "history": []
}
```

**Response:**
```json
{
  "answer": "Shop bảo hành chính hãng 12 tháng cho điện thoại và laptop...",
  "sources": ["chinh-sach.md"]
}
```

### POST `/api/reindex`

Chạy lại toàn bộ embedding cho knowledge-base. Cần `X-Admin-Key` header.

**Request:**
```bash
curl -X POST /api/reindex -H "X-Admin-Key: your_secret_key"
```

**Response:**
```json
{
  "status": "started",
  "chunks_indexed": 0,
  "message": "Reindex đã được khởi động trong background..."
}
```

---

## 🧪 Test Câu Hỏi Mẫu

Sau khi chạy `embed.py`, thử các câu hỏi sau để kiểm tra chatbot:

| Câu hỏi | Nguồn dữ liệu | Kết quả mong đợi |
|---------|---------------|-------------------|
| "Chính sách bảo hành điện thoại là bao nhiêu tháng?" | `chinh-sach.md` | "12 tháng chính hãng" |
| "Tôi muốn đổi hàng, có được không?" | `chinh-sach.md` | Điều kiện đổi trong 7 ngày |
| "Làm sao để đặt hàng trên web?" | `huong-dan-mua-hang.md` | Hướng dẫn 8 bước |
| "Có mã giảm giá nào không?" | `faq.md` | Mã WELCOME10 giảm 10% |
| "Thời gian giao hàng ngoại tỉnh là bao lâu?" | `chinh-sach.md` | "2-5 ngày làm việc" |

---

## 🔐 Bảo Mật

- `GEMINI_API_KEY` và `ADMIN_REINDEX_KEY` **không được commit lên Git**.
- File `.env` đã được thêm vào `.gitignore`.
- Trên Render: set biến môi trường trong **Dashboard → Environment**.
- Chatbot RAG dùng `GEMINI_API_KEY` từ environment — không hardcode.

---

## 🚀 Deploy Trên Render

1. Push code lên GitHub (không có `.env`, không có `vector_store.json`).
2. Trên Render Dashboard → **Environment** → thêm:
   - `GEMINI_API_KEY` = your_key
   - `ADMIN_REINDEX_KEY` = your_secret
3. Deploy và gọi `/api/reindex` để tạo vector store trên server.
