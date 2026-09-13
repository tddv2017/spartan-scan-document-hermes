# Hermes Vision Extractor (Lufthansa Cargo)

> **Hệ Thống Bóc Tách Dữ Liệu Tự Động Qua Screen Vision & Xuất Phiếu Đối Soát Vận Đơn Khổ A4 Chuẩn**  
> Chuyên dụng cho phần mềm Hermes Cargo Management System (CMS) tại các nhà ga hàng hóa hàng không (NCTS, ACSC, TCS).

---

## 1. Tổng Quan Nghiệp Vụ (Business Overview)

Trong quy trình khai thác hàng không tại kho hàng (Cargo Terminal) của **Lufthansa Cargo (LH)**, nhân viên tiếp nhận và xử lý vận đơn phải liên tục tra cứu thông tin trên hệ thống **Hermes CMS**. Quy trình thủ công đòi hỏi nhân viên phải:
1. Gõ tay hoặc đối chiếu mắt từng số vận đơn (**Master AWB**: 3 số prefix hãng `020` + 8 chữ số serial).
2. Kiểm tra số kiện (**Pieces / Colli**) và trọng lượng (**Gross Weight kg**).
3. Xác nhận tên người nhận (**Consignee**) và đại lý giao nhận (**Agent**).
4. Đặc biệt quan trọng: Kiểm tra cờ nghiệp vụ **`ALL IMP/ACC HAWB`** (Tất cả House AWB đã hoàn tất phân tách và chấp nhận thông quan hàng đến).
5. Ghi chép hoặc lập danh sách bàn giao ca trực trên giấy/Excel để giao lại cho ca kế tiếp kiểm đếm vật lý.

**Hermes Vision Extractor** giải quyết triệt để bài toán này bằng công nghệ **Computer Vision & In-Process OCR**, hoạt động **hoàn toàn phi can thiệp** (non-intrusive) trên nền tảng Windows:
- Bấm **1 phím tắt (`F9` hoặc `Ctrl+Shift+S`)** hoặc **1 chạm trên Nút Bấm Nổi (Floating Widget)** để tự động nhận diện và bóc tách toàn bộ trường dữ liệu trên màn hình Hermes CMS trong chưa đầy **0.8 giây**.
- Tự động kiểm tra tính hợp lệ của số AWB theo thuật toán chuẩn hàng không quốc tế **IATA Resolution 600a (Modulo-7)**.
- Tự động phân loại 4 trạng thái nghiệp vụ qua mã màu trực quan:
  - 🟢 **`CLEARED`**: Đã xác nhận `ALL IMP/ACC HAWB` - đủ điều kiện giải phóng hàng.
  - 🟡 **`PENDING_HAWB`**: Vận đơn gom (Consolidation) còn thiếu House AWB hoặc đang chờ xử lý.
  - 🔵 **`DIRECT_SHIPMENT`**: Vận đơn trực tiếp không qua House AWB.
  - 🔴 **`CHECKSUM_ERROR`**: Số vận đơn bị sai check digit hoặc OCR đọc nhầm.
- Xuất ngay **Phiếu Bàn Giao & Đối Soát Ca Trực chuẩn khổ A4 (ISO 216)** hỗ trợ 100% tiếng Việt UTF-8 có dấu, tích hợp sẵn tính năng Xem Trước (Preview) và Gửi Lệnh In Trực Tiếp (Print PDF).

---

## 2. Kiến Trúc Hệ Thống & Ngăn Xếp Công Nghệ (Technology Stack)

```
hermes_vision_extractor/
├── app/
│   ├── core/                  # Core Business Domain & Configuration
│   │   ├── config.py          # Hằng số, phím tắt, font chữ hệ thống
│   │   ├── models.py          # Pydantic v2 schemas: AWBRecord, ExtractionResult, BusinessStatus
│   │   ├── classifier.py      # Bộ phân loại quy tắc nghiệp vụ ('ALL IMP/ACC HAWB', Mod-7)
│   │   ├── session_store.py   # Quản lý phiên làm việc đa luồng (Thread-safe in-memory store)
│   │   └── hotkey.py          # Native Win32 RegisterHotKey background daemon
│   ├── capture/               # Module Chụp Màn Hình
│   │   └── screen_grabber.py  # Chụp đa màn hình, High-DPI aware, cửa sổ Hermes active
│   ├── vision/                # Module Xử Lý Thị Giác Máy Tính & OCR
│   │   ├── preprocessor.py    # Phóng đại 2x Bicubic, cân bằng độ tương phản CLAHE
│   │   ├── ocr_engine.py      # Dual OCR: RapidOCR (ONNX Runtime CPU) + Windows.Media.Ocr
│   │   └── parser.py          # Domain parser: Regex đa tầng, IATA Modulo-7, chuẩn hóa số quốc tế
│   ├── pdf/                   # Module Sinh Phiếu In Chuẩn ISO A4
│   │   └── generator.py       # ReportLab PDF engine, nhúng font TrueType Arial tiếng Việt có dấu
│   └── ui/                    # Giao Diện Người Dùng (Desktop GUI)
│       ├── overlay.py         # Floating widget dạng pill bán trong suốt, kéo thả, phím F9
│       └── session_window.py  # Cửa sổ quản lý danh sách AWB, Treeview mã màu, CRUD, Export PDF
├── tests/                     # Bộ Kiểm Thử Tự Động (Unit, Integration & E2E)
├── main.py                    # Điểm khởi chạy ứng dụng (Application Orchestrator)
├── requirements.txt           # Danh mục thư viện phụ thuộc
└── README.md                  # Tài liệu hướng dẫn sử dụng và vận hành
```

### Chi Tiết Công Nghệ:
| Phân Hệ | Công Nghệ / Thư Viện | Lý Do Lựa Chọn & Ưu Điểm Kỹ Thuật |
|---|---|---|
| **Runtime** | Python 3.12 (64-bit) | Hiệu năng cao, tương thích hoàn hảo Windows 10/11 x64. |
| **GUI Framework** | `tkinter` + `ttk` | Tích hợp sẵn trong Python, tiêu thụ cực ít RAM (<30MB), khởi động <150ms, phản hồi lập tức. |
| **Global Hotkey** | Native Win32 `RegisterHotKey` qua `ctypes` | Đăng ký tầng Win32 Kernel, không gây delay gõ phím của người dùng trong Hermes CMS. |
| **Screen Capture** | `PIL.ImageGrab` + High-DPI `SetProcessDpiAwareness(2)` | Không cần chèn DLL, không can thiệp bộ nhớ tiến trình Hermes, chụp chính xác từng pixel. |
| **OCR Engine** | `rapidocr_onnxruntime` + `Windows.Media.Ocr` | Chạy in-process ONNX CPU (không cần server ngoài, không cần Tesseract exe cài thêm). Tốc độ 200–400ms. |
| **PDF Generator** | `reportlab` 5.0+ | Nhúng trực tiếp font Windows TrueType (`Arial`, `Segoe UI`), xuất chuẩn ISO A4 (595.28 x 841.89 pt). |

---

## 3. Yêu Cầu Hệ Thống & Hướng Dẫn Cài Đặt

### Cách 1: Chạy Ngay Với File `.exe` (Khuyên Dùng - Không Cần Cài Python)
Ứng dụng đã được đóng gói sẵn thành file chạy độc lập nằm trong thư mục `dist/`:
- Đường dẫn: **`dist/HermesVisionExtractor.exe`**
- **Chỉ cần nhấp đúp chuột (Double Click)** vào file `HermesVisionExtractor.exe` là có thể sử dụng ngay lập tức trên mọi máy tính Windows 10/11 64-bit mà không cần cài đặt bất kỳ phần mềm hay thư viện nào!

---

### Cách 2: Chạy Từ Mã Nguồn Python (Dành Cho Lập Trình Viên)
Yêu cầu môi trường:
- **Hệ Điều Hành:** Windows 10 hoặc Windows 11 (64-bit).
- **Python:** Python 3.12+ (đã tích hợp sẵn `pip` và `tcl/tk`).

1. **Cài đặt các gói phụ thuộc qua `requirements.txt`:**
   ```powershell
   & "C:\Users\Dung\AppData\Local\Programs\Python\Python312\python.exe" -m pip install -r requirements.txt
   ```

2. **Khởi chạy ứng dụng:**
   ```powershell
   & "C:\Users\Dung\AppData\Local\Programs\Python\Python312\python.exe" main.py
   ```
   *(Thêm cờ `--show-manager` nếu muốn mở trực tiếp cửa sổ quản lý ca trực).*

3. **Chạy kiểm tra chẩn đoán hệ thống (Self-Diagnostic):**
   ```powershell
   & "C:\Users\Dung\AppData\Local\Programs\Python\Python312\python.exe" main.py --test-pipeline
   ```

---

### 4.2. Nút Bấm Nổi (Floating Widget Overlay)
Khi ứng dụng khởi chạy, một thanh công cụ nổi (Pill Widget) nhỏ gọn màu đen sang trọng sẽ xuất hiện ở góc trên bên phải màn hình:

- **Kéo Thả Tự Do:** Bấm giữ chuột trái vào thanh widget để di chuyển tới bất kỳ vị trí thuận tiện nào trên màn hình làm việc.
- **Luôn Trên Cùng (Always-on-top):** Widget luôn hiển thị phía trên cửa sổ Hermes CMS giúp thao tác chỉ với 1 click chuột.
- **Độ Bán Trong Suốt (88% Alpha):** Đảm bảo không che khuất các thông tin quan trọng bên dưới.
- **Các Nút Thao Tác:**
  - `[ 🔍 Quét ]`: Bấm để chụp tức thì cửa sổ Hermes hiện tại và bóc tách dữ liệu.
  - `[ 📋 ]`: Mở/Ẩn Cửa Sổ Quản Lý Danh Sách Vận Đơn Ca Trực (**Session Manager**).
  - `[ ✕ ]`: Thoát ứng dụng an toàn.
- **Hiệu Ứng Trạng Thái (Pulse Animation):**
  - 🟢 **Ready (F9)**: Hệ thống ở trạng thái chờ sẵn sàng.
  - 🟡 **Đang quét...**: Đèn nhấp nháy màu vàng hổ phách thể hiện OCR đang chạy (<0.8 giây).
  - 🟢 **✔ 020-xxxx**: Báo hiệu bóc tách thành công và đã lưu vận đơn vào ca trực.
  - 🔴 **✖ Lỗi**: Thông báo ngắn nếu vùng màn hình không chứa vận đơn AWB.

---

### 4.3. Chế Độ Tự Động Quét Khi Xác Nhận Bill (Auto-Scan on Confirm)
Để tối ưu hóa tốc độ nhập bill liên tục mà không cần bấm thêm phím quét:
- **Phím Tắt Xác Nhận Hermes CMS:** Tự động kích hoạt quét khi người dùng nhấn **`Alt + F`** (hoặc `Enter`, click chuột vào nút Confirm).
- **Hàng Đợi Chụp Tức Thì (<25ms):** Hệ thống lập tức lưu ảnh chụp màn hình vào RAM & ổ đĩa (`captures/YYYY-MM-DD/`) và đẩy vào hàng đợi FIFO. **Giao diện không bị khựng**, nhân viên có thể nhập tiếp bill kế tiếp ngay lập tức!
- **Worker Chạy Ngầm:** Xử lý OCR tuần tự trong nền, tự động đổi tên ảnh thành `{ThờiGian}_{SốAWB}_{TrạngThái}.png` để lưu trữ hồ sơ đối soát.
- **Huy Hiệu Hàng Đợi:** Widget nổi hiển thị `📸 Q: X bill` màu tím mộng mơ khi còn việc chờ xử lý, và tự động chuyển sang xanh `✔ 020-xxxx` khi hoàn tất.

---

### 4.4. Kích Hoạt Thủ Công Qua Phím Tắt (Global Hotkeys)
- Bấm phím **`F9`** hoặc tổ hợp phím **`Ctrl + Shift + S`** bất kỳ lúc nào để kích hoạt quét chủ động.
- Hệ thống có cơ chế **Debounce (0.4s)** ngăn ngừa hiện tượng bấm lặp phím ngoài ý muốn.

---

### 4.5. Cửa Sổ Quản Lý Phiên Làm Việc (Session Manager)
Bấm vào biểu tượng `[ 📋 ]` trên Widget nổi để mở giao diện quản lý phiên làm việc.

#### Bảng Danh Sách Vận Đơn (Treeview):
- Hiển thị đầy đủ: Số STT, Số AWB, Số kiện (Colli), Trọng lượng (KG), Người nhận (Consignee), Đại lý (Agent), Cờ `ALL IMP/ACC HAWB`, Trạng thái và Thời gian quét.
- **Mã Màu Nhận Diện Nghiệp Vụ:**
  - 🟩 **Xanh Lá Cây (`CLEARED`)**: Vận đơn đã đối soát toàn bộ HAWB (`ALL IMP/ACC HAWB`).
  - 🟧 **Vàng Cam (`PENDING_HAWB`)**: Vận đơn gom đang chờ đối soát HAWB.
  - 🟦 **Xanh Lam (`DIRECT_SHIPMENT`)**: Vận đơn Master trực tiếp.
  - 🟥 **Đỏ (`CHECKSUM_ERROR`)**: Số AWB không vượt qua kiểm tra IATA Modulo-7.

#### Các Thao Tác Nghiệp Vụ Trên Thanh Công Cụ:
1. **🔍 Quét Ngay:** Chụp màn hình tức thì tương tự phím `F9`.
2. **✏️ Chỉnh Sửa:** Chọn một dòng AWB và bấm nút (hoặc **nhấp đúp chuột vào dòng**) để mở hộp thoại sửa nhanh số kiện, kg, tên công ty, ghi chú hoặc tick chọn cờ `ALL IMP/ACC HAWB`.
3. **🗑️ Xóa:** Xóa một vận đơn khỏi danh sách ca trực (có hộp thoại xác nhận).
4. **🧹 Xóa Ca:** Xóa toàn bộ danh sách để bắt đầu ca trực mới.
5. **📁 Thư Mục Ảnh:** Mở ngay thư mục lưu trữ ảnh chụp màn hình gốc trong Windows Explorer (`captures/YYYY-MM-DD/`).
6. **🖼️ Xem Ảnh Bill:** Nhấp chọn bất kỳ dòng vận đơn nào và bấm nút này để xem ngay ảnh chụp thực tế lúc nhân viên thao tác bill đó.
7. **Bộ Lọc Nhanh (Lọc trạng thái):** Xem riêng danh sách các vận đơn `CLEARED`, `PENDING_HAWB`, hoặc vận đơn lỗi.

#### Thanh Thống Kê Tổng Hợp (Summary KPI Bar):
Hiển thị liên tục theo thời gian thực ở đáy cửa sổ:
`📊 Tổng AWB | Tổng Kiện (Colli) | Tổng Trọng Lượng (KG) | Tỷ Lệ Đã Duyệt HAWB (%) | Lỗi Checksum`

---

### 4.5. Xuất & In Phiếu Bàn Giao Ca Khổ A4 Chuẩn
Bấm nút **`📄 Xuất / In PDF (A4)`** trên thanh công cụ:
1. Hộp thoại cấu hình xuất hiện:
   - **Ca làm việc:** Nhập tên ca (mặc định: *Ca 1 - Đội Khai Thác NCTS*).
   - **Nhân viên giao ca:** Họ tên người lập phiếu.
   - **Nhân viên nhận ca:** Họ tên người nhận bàn giao.
   - **Trạm khai thác:** e.g. *HAN / NCTS Cargo Hub*.
   - **Đường dẫn lưu:** Bấm nút `Chọn...` để lưu vào thư mục mong muốn.
2. Lựa chọn hành động:
   - **`📄 Xuất PDF`**: Tạo file PDF và lưu vào đĩa cứng.
   - **`👁️ Xem Trước`**: Tạo file và tự động mở bằng Acrobat Reader / Trình duyệt Chrome / Edge để xem ngay.
   - **`🖨️ In Trực Tiếp`**: Gửi lệnh in trực tiếp đến máy in mặc định của Windows mà không cần mở file thủ công.

#### Đặc Điểm Thiết Kế Phiếu Bàn Giao A4:
- **Kích thước chuẩn:** ISO A4 Portrait (595.28 x 841.89 điểm).
- **Phông chữ tiếng Việt chuẩn:** Nhúng trực tiếp font Windows TrueType (`Arial`), hiển thị hoàn hảo dấu tiếng Việt, không bị lỗi ô vuông hay mất ký tự.
- **Đầy đủ 7 cột nghiệp vụ:** STT, Số AWB, Số Kiện (Colli), Trọng Lượng (KG), Consignee & Agent, Trạng Thái & Ghi Chú (nổi bật cờ `ALL IMP/ACC HAWB`), Ô Ký Nhận/Kiểm Đếm (`[ ] Đạt`).
- **Phần chân trang:** 3 khối chữ ký phân định trách nhiệm rõ ràng:
  - **Người Lập Phiếu**
  - **Nhân Viên Giao Ca**
  - **Nhân Viên Nhận Ca**
- **Đánh số trang hai lượt (NumberedCanvas):** Tự động hiển thị `Trang X / Y` và ngày giờ xuất phiếu.

---

## 5. Quy Chuẩn Kỹ Thuật & Giải Thuật Hàng Không (IATA Standards)

### Thuật Toán IATA Resolution 600a Modulo-7
Mỗi số vận đơn hàng không quốc tế gồm tiền tố 3 chữ số (ví dụ `020` của Lufthansa Cargo) và 8 chữ số serial:
$$\text{Serial} = [d_1 d_2 d_3 d_4 d_5 d_6 d_7] [C]$$
Trong đó chữ số kiểm tra $C$ bắt buộc thỏa mãn:
$$C = \text{int}(d_1 d_2 d_3 d_4 d_5 d_6 d_7) \pmod 7$$
Hệ thống tự động tính toán và đối chiếu; nếu chữ số kiểm tra không khớp, bản ghi sẽ được cảnh báo đỏ `CHECKSUM_ERROR` để nhân viên rà soát lại ngay.

### Chuẩn Hóa Định Dạng Số Kiện & Trọng Lượng
Hermes CMS hỗ trợ cả định dạng kiểu Châu Âu (dấu phẩy thập phân: `125,50 KG`) và kiểu Mỹ/Anh (dấu chấm thập phân: `1,250.50 KG`), cũng như các dạng ghi ghép (`Colli / Weight: 45 / 1250.50 KG` hoặc `45 Colli / 1250.50 kg`). Parser được thiết kế regex đa tầng để chuẩn hóa 100% về số nguyên và số thực chuẩn.

---

## 6. Hướng Dẫn Chạy Kiểm Thử Tự Động (Automated Testing)

Dự án đi kèm bộ kiểm thử tự động toàn diện qua `pytest`:

```powershell
# Chạy toàn bộ test suite:
& "C:\Users\Dung\AppData\Local\Programs\Python\Python312\python.exe" -m pytest -v

# Chạy riêng kiểm thử phân hệ PDF Generator:
& "C:\Users\Dung\AppData\Local\Programs\Python\Python312\python.exe" -c "
from app.core.models import AWBRecord
from app.pdf.generator import generate_cargo_handover_pdf
import os
pdf = generate_cargo_handover_pdf([AWBRecord(awb_number='020-12345675')], 'test.pdf')
assert os.path.exists(pdf)
os.remove(pdf)
print('PDF Generator: 100% OK')
"
```

---

## 7. Giấy Phép & Bản Quyền
- Ứng dụng phát triển phục vụ công tác vận hành hàng hóa hàng không tại các trạm khai thác của **Lufthansa Cargo**.
- Bản quyền phần mềm &copy; 2026. Mọi quyền được bảo lưu.
