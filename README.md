# Lab8 · Trợ lý thực hành KHTN 8

Website demo tiếng Việt: camera hoặc ảnh tải lên → YOLO11 nhận diện dụng cụ → chọn bài học minh họa bằng Gemini → hiển thị bài thực hành và quy tắc an toàn.

## Cài đặt và chạy tại máy cá nhân

Yêu cầu:

- Python 3.10+
- pip
- kết nối mạng để cài dependency và (nếu cần) gọi Gemini API
- webcam nếu dùng chức năng camera trong trình duyệt

### 1) Clone hoặc mở project

```bash
git clone <link-repo>
cd laboratory-equipment-for-class-8
```

Nếu bạn đã có project trong máy, mở thư mục này trong terminal.

### 2) Tạo môi trường ảo

Trên Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Trên Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3) Cài đặt các package cần thiết

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4) Tạo file cấu hình môi trường

Trong thư mục dự án có sẵn file `.env.example`. Sao chép ra file `.env`:

Trên Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Trên Linux/macOS:

```bash
cp .env.example .env
```

Nội dung mặc định trong `.env` là:

```env
MODEL_PATH=./my_custom_yolo11_model.pt
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.6-flash
CONFIDENCE_THRESHOLD=0.25
MAX_UPLOAD_MB=10
```

Bạn có thể chỉnh sửa các biến sau:

- `MODEL_PATH`: đường dẫn đến file trọng số YOLO. Mặc định là `./my_custom_yolo11_model.pt`.
- `GEMINI_API_KEY`: khóa API để dùng Gemini. Nếu để trống, app vẫn hoạt động với dữ liệu cục bộ.
- `GEMINI_MODEL`: mô hình Gemini bạn muốn dùng.
- `CONFIDENCE_THRESHOLD`: ngưỡng tin cậy cho nhận diện.
- `MAX_UPLOAD_MB`: giới hạn dung lượng ảnh upload.

### 5) Khởi động ứng dụng

```bash
uvicorn app:app --host 0.0.0.0 --port 2013
```

Sau đó mở trình duyệt:

```text
http://localhost:2013
```

Trang mặc định là Giới thiệu. Mở `http://localhost:2013/practice` để vào khu vực nhận diện và thực hành.

Nếu máy bạn dùng lệnh `python` thay cho `py`, hãy thay `python -m venv ...` phù hợp.

### 6) Chạy app mà không cần Gemini

Nếu chưa có `GEMINI_API_KEY`, hệ thống vẫn chạy bình thường:

- nhận diện dụng cụ bằng YOLO,
- tìm bài học tương ứng trong `data/lessons.json`,
- hiển thị mục tiêu, bước thực hiện và an toàn từ dữ liệu cục bộ.

## Cách dùng app

### 1) Khởi chạy ứng dụng

- Mở terminal trong thư mục dự án.
- Tạo môi trường ảo và cài dependency theo hướng dẫn ở mục trên.
- Chạy lệnh:

```bash
uvicorn app:app --host 0.0.0.0 --port 2013
```

- Mở trình duyệt và truy cập `http://localhost:2013` để xem Giới thiệu hoặc `http://localhost:2013/practice` để nhận diện dụng cụ.
- Nếu đang dùng camera trong trình duyệt, hãy đảm bảo truy cập qua `localhost` hoặc HTTPS; nếu không, hãy tải ảnh lên để thử nghiệm.

### 2) Chọn chế độ nhận diện

Giao diện web có 2 cách sử dụng chính:

- Camera: cho phép chụp trực tiếp bằng webcam.
- Tải ảnh: chọn ảnh có sẵn từ máy tính, ví dụ ảnh dụng cụ thí nghiệm, dụng cụ hóa học, bình thủy tinh, ống nghiệm...

### 3) Nhận diện dụng cụ

- Đặt dụng cụ vào giữa khung hình hoặc ảnh.
- Chụp ảnh với đủ sáng, không mờ, không bị che khuất.
- Sau khi gửi ảnh, hệ thống sẽ:
  - chạy mô hình YOLO để phát hiện nhãn dụng cụ,
  - lọc ra danh sách các nhãn nhận diện được,
  - tìm bài thực hành tương ứng trong dữ liệu minh họa,
  - hiển thị mục tiêu, bước thực hiện và quy tắc an toàn.

### 4) Xem kết quả gợi ý bài học

- Nếu phát hiện đúng dụng cụ, ứng dụng sẽ hiển thị một bài học phù hợp.
- Nếu không có GEMINI_API_KEY, ứng dụng vẫn dùng dữ liệu cục bộ để hiển thị bài học minh họa.
- Nếu mô hình không phát hiện được dụng cụ hoặc không tìm thấy bài phù hợp, hệ thống sẽ báo "Chưa thấy dụng cụ" hoặc "Chưa tìm thấy bài thực hành phù hợp".

### 5) Điều chỉnh khi nhận diện sai

Nếu ứng dụng không nhận diện đúng, hãy thử:

- chụp ảnh rõ hơn, sáng hơn,
- đưa dụng cụ vào giữa khung hình,
- chọn ảnh có nền đơn giản,
- kiểm tra tên nhãn trong mô hình và cập nhật `equipment_aliases` trong `data/lessons.json` nếu cần.

### 6) Lưu ý quan trọng

- Dữ liệu trong `data/lessons.json` là minh họa, chưa phải SGK chuẩn.
- Giáo viên nên rà soát lại nội dung trước khi dùng trong lớp học.
- Luôn tuân thủ quy tắc an toàn khi làm việc với hóa chất, lửa hoặc dụng cụ thủy tinh.

## Dữ liệu bài học

`data/lessons.json` chỉ chứa **dữ liệu minh họa, chưa xác thực SGK**. Trước khi dùng trong lớp, giáo viên cần thay tên bài, mục tiêu, bước thực hiện, quy tắc an toàn và nguồn trích dẫn theo đúng bộ SGK KHTN 8 đang sử dụng. `equipment_aliases` phải khớp tên lớp trong trọng số YOLO (không phân biệt chữ hoa và dấu tiếng Việt). Nếu không khớp, ứng dụng báo chưa có bài phù hợp. Gemini chỉ chọn một bản ghi có sẵn và viết lý do; nội dung bước, mục tiêu và an toàn được lấy nguyên từ dữ liệu cục bộ.

## API

- `GET /api/health`: trạng thái cấu hình cơ bản.
- `POST /api/analyze`: form-data `file` (JPG, PNG, WebP, mặc định tối đa 10 MB). Trả `request_id`, `width`, `height`, `detections` với `box` là `[x1,y1,x2,y2]` theo pixel ảnh gốc, `labels`, `supported_classes`, `suggestion` và cảnh báo dữ liệu. Confidence trả về ở dạng thập phân từ `0` đến `1`.
- `POST /api/suggestion`: JSON `{ "labels": ["tên dụng cụ đã xác nhận"] }`; chỉ chấp nhận lớp có trong model đang cấu hình.
- `POST /api/feedback`: multipart gồm `file` (ảnh đã phân tích) và `metadata` (JSON có `report_id`, `request_id`, `detection_id`, `predicted_label`, `confidence`, tùy chọn `student_selected_label`). Trả `status: saved` sau khi lưu thành công.

Ảnh nhận diện chỉ được đọc trong bộ nhớ. Khi học sinh báo nhận diện sai, đúng ảnh đã phân tích được gửi vào `data/review_queue/` cùng JSON ghi nhãn dự đoán, mã yêu cầu, mã detection và tọa độ khung để phân biệt nhiều dụng cụ trong cùng ảnh. Đây là khu vực chờ kiểm tra, không được phục vụ công khai và đã được thêm vào `.gitignore`. Bản ghi có `review_status: pending` và `training_status: not_eligible_unverified`; việc chọn tên trong giao diện chỉ được lưu như thông tin tham khảo, không được coi là nhãn đã xác minh.

Giáo viên/người quản trị cần kiểm tra ảnh và đối chiếu `detection_id`, xác nhận nhãn chính xác bằng quy trình riêng, rồi mới chuyển ảnh đã xác minh sang tập dữ liệu huấn luyện có kiểm soát. Không có chức năng duyệt nhãn hoặc huấn luyện lại tự động trong ứng dụng này; cần sao lưu, rà soát chất lượng và chạy quy trình huấn luyện riêng trước khi cập nhật `MODEL_PATH`. Camera tự quét tối đa một yêu cầu mỗi 3 giây; có thể tắt tự quét và chụp thủ công. Camera trong trình duyệt cần `localhost` hoặc HTTPS.

### Kho cảnh báo an toàn và duyệt nội dung

`data/safety_content.json` là kho nội dung tĩnh có cấu trúc, được đọc lại theo từng yêu cầu nên cập nhật không cần sửa mã nguồn hoặc khởi động lại server. Các nội dung người dùng xác nhận đã được giáo viên KHTN duyệt được đánh dấu **Đã duyệt** và có thể hiển thị cho học sinh. Hồ sơ ghi rõ tên người duyệt chưa được cung cấp; trường reviewer hiện ghi “Giáo viên KHTN (theo xác nhận của người dùng)” và ngày ghi nhận 2026-10-15. Các mục ngoài nội dung đã xác nhận vẫn là **Chờ duyệt**, không được trình bày như hướng dẫn đã xác nhận. Giáo viên/người quản trị có thể cập nhật kho theo các bước:

1. Mở JSON trong trình soạn thảo văn bản và chọn đúng bản ghi theo `id`/`name`.
2. Kiểm tra, chỉnh `hazards`, `avoid`, `student_action` và `hazard_level` theo thiết bị thực tế, quy định phòng thực hành và hướng dẫn của nhà trường.
3. Chỉ sau khi phê duyệt chính thức, đặt `status` thành `Đã duyệt`, điền `reviewer` (tên người có thẩm quyền), `approved_at` theo ISO 8601 (ví dụ `2026-10-15T09:00:00+07:00`) và cập nhật `version`.
4. Lưu JSON hợp lệ. Server sẽ chỉ trả nội dung chi tiết khi trạng thái, người duyệt, thời gian và phiên bản đều hợp lệ. Để rút nội dung khỏi học sinh, đổi trạng thái thành `Ngừng sử dụng`.

Ứng dụng chưa có đăng nhập/phân quyền hay giao diện quản trị; quyền sửa tệp phải được giới hạn ở giáo viên/người quản trị trên máy chủ. Bản ghi chỉ được duyệt nếu thực sự đã được người có thẩm quyền kiểm tra; không sao chép trạng thái phê duyệt sang nội dung chưa được xác nhận.

## Giới hạn

Độ chính xác phụ thuộc ảnh và trọng số YOLO. Nhãn trong mô hình chưa được kiểm tra trực tiếp trong môi trường tạo dự án. Các bản ghi minh họa có thể không khớp nhãn thực tế; xem tên lớp của mô hình rồi sửa `equipment_aliases`. Luôn thực hành với giáo viên, nhất là với hóa chất, lửa hoặc thủy tinh.
