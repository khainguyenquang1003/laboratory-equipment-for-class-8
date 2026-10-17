# Lab8 · Trợ lý thực hành KHTN 8

Website demo tiếng Việt: camera hoặc ảnh tải lên → YOLO11 nhận diện dụng cụ → hiển thị ngay tên và độ tin cậy → Gemini tìm bài phù hợp hoặc tạo bản nháp không đồng bộ.

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
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_API_URL=https://api.deepseek.com/chat/completions
CONFIDENCE_THRESHOLD=0.25
MAX_UPLOAD_MB=10
```

Bạn có thể chỉnh sửa các biến sau:

- `MODEL_PATH`: đường dẫn đến file trọng số YOLO. Mặc định là `./my_custom_yolo11_model.pt`. Nếu thay nội dung file khi server đang chạy, app sẽ tự nạp lại model khi kích thước hoặc thời gian sửa file thay đổi.
- `GEMINI_API_KEY`: khóa API để dùng Gemini. Nếu để trống, app vẫn hoạt động với dữ liệu cục bộ.
- `GEMINI_MODEL`: mô hình Gemini bạn muốn dùng.
- `DEEPSEEK_API_KEY`: khóa API DeepSeek dùng dự phòng khi Gemini thiếu khóa hoặc không gọi thành công. Chỉ lưu khóa trong `.env` trên máy chủ; không đưa vào JavaScript, HTML hoặc Git.
- `DEEPSEEK_MODEL`: model DeepSeek tương thích Chat Completions, mặc định `deepseek-chat`.
- `DEEPSEEK_API_URL`: endpoint Chat Completions của DeepSeek; mặc định `https://api.deepseek.com/chat/completions`.
- `CONFIDENCE_THRESHOLD`: ngưỡng tin cậy cho nhận diện.
- `MAX_UPLOAD_MB`: giới hạn dung lượng ảnh upload.

### 5) Khởi động ứng dụng

Trên Windows PowerShell, chạy bằng Python trong môi trường ảo của project:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 2013
```

Trên Linux/macOS:

```bash
./.venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 2013
```

Sau đó mở trình duyệt:

```text
http://localhost:2013
```

Trang mặc định là Giới thiệu. Mở `http://localhost:2013/practice` để vào khu vực nhận diện và thực hành.

Nếu máy bạn dùng lệnh `python` thay cho `py`, hãy thay `python -m venv ...` phù hợp.

### 6) Cấu hình DeepSeek dự phòng

Tạo hoặc mở `.env` và đặt khóa DeepSeek mới:

```env
DEEPSEEK_API_KEY=<khóa DeepSeek của bạn>
```

Không gửi khóa trong chat, không đặt trong file `.js`/`.html` và không commit `.env`. Khóa DeepSeek bạn vừa dán vào cuộc trò chuyện đã bị lộ; hãy thu hồi khóa đó trong trang quản lý DeepSeek và tạo khóa mới trước khi cấu hình. Khởi động lại server sau khi sửa `.env`.

Khi Gemini lỗi hoặc chưa cấu hình, server tự thử DeepSeek với cùng nội dung JSON. Câu trả lời vẫn được kiểm tra theo các ràng buộc hiện tại: chỉ bài trong kho mới được chọn, nội dung an toàn không do AI tạo, và các bước bài mới vẫn chờ giáo viên duyệt. API `/api/health` chỉ báo `deepseek_configured: true/false`, không trả khóa.

### 7) Chạy app mà không cần AI bên ngoài

Nếu chưa cấu hình cả `GEMINI_API_KEY` lẫn `DEEPSEEK_API_KEY`, hệ thống vẫn chạy bình thường:

- nhận diện dụng cụ bằng YOLO,
- hiển thị ngay tên dụng cụ và độ tin cậy,
- báo rõ rằng không thể tìm hoặc tạo gợi ý bài thực hành bằng AI.

## Cách dùng app

### 1) Khởi chạy ứng dụng

- Mở terminal trong thư mục dự án.
- Tạo môi trường ảo và cài dependency theo hướng dẫn ở mục trên.
- Khởi động bằng Python của môi trường ảo để bảo đảm có đủ thư viện mô hình:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 2013
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
  - chạy mô hình YOLO để phát hiện nhãn dụng cụ và độ tin cậy,
  - hiển thị ngay dụng cụ và độ tin cậy, sau đó hỏi Gemini tìm gợi ý phù hợp,
  - cập nhật gợi ý trên trang khi Gemini hoàn tất; không tải lại trang.
- Độ tin cậy dưới 60% có màu đỏ, 60% đến dưới 80% màu vàng, từ 80% màu xanh lá. Với nhãn đỏ, chọn lại tên dụng cụ trước khi yêu cầu AI gợi ý; chưa gửi tên chưa xác nhận cho AI và không hiển thị các bước thực hành chưa duyệt.
- Tên lớp dụng cụ của mô hình được chuyển sang tiếng Việt khi hiển thị.

### 4) Xem kết quả gợi ý bài học

- Gemini chọn bài từ các bài phù hợp trong kho dữ liệu và giải thích lựa chọn. Nếu không có bài phù hợp, Gemini tạo và lưu bản nháp mới vào `data/ai_lesson_drafts.json`.
- Kho dữ liệu có thêm gợi ý đun nóng hỗn hợp bột sắt và lưu huỳnh; nhãn thiết bị chính như đèn cồn được ưu tiên ghép bài kể cả khi ảnh có thêm vật dụng khác. Đây là dữ liệu tham khảo theo yêu cầu, chưa xác thực SGK; không có bước thao tác và cần giáo viên đối chiếu nội dung trước khi sử dụng.
- Bản nháp mới được ghi trạng thái **Chờ giáo viên duyệt**; giao diện học sinh chỉ hiển thị tên, mục tiêu và giải thích, không hiển thị các bước chưa duyệt để thực hành.
- Bản nháp cùng dụng cụ đang chờ duyệt được dùng lại, không tạo bản trùng khi gửi yêu cầu lần nữa. Sau khi giáo viên duyệt, người quản trị cần tự kiểm tra và chuyển nội dung phù hợp vào `data/lessons.json`; ứng dụng không tự duyệt hay công khai bản nháp.
- Nếu Gemini không được cấu hình hoặc gọi thất bại, ứng dụng thử DeepSeek nếu đã cấu hình. Nếu cả hai dịch vụ lỗi, kết quả nhận diện vẫn được giữ; với đèn cồn, bài phù hợp trong kho sẽ được hiển thị kèm thông báo AI dự phòng chưa khả dụng. Không hiển thị bước thực hành chưa được phép.
- Khi chưa có nội dung an toàn đã duyệt, ứng dụng chỉ thông báo **Chưa có thông tin an toàn được duyệt. Hãy hỏi giáo viên**; không suy diễn rằng dụng cụ an toàn. Chỉ thông tin an toàn đã được giáo viên duyệt mới được hiển thị chi tiết.

### 5) Kiểm thử luồng nhận diện và gợi ý

1. Chạy server và mở `http://localhost:2013/practice`. Có thể kiểm tra trạng thái Gemini tại `http://localhost:2013/api/health` (chỉ xem trường `gemini_configured`, không chia sẻ khóa API).
2. Với ảnh có dụng cụ dễ nhận biết và độ tin cậy từ 60%: tên cùng độ tin cậy phải xuất hiện trước; trong lúc chờ, giao diện báo AI đang tìm gợi ý. Khi AI trả lời, nội dung được cập nhật mà không tải lại trang.
3. Với kết quả dưới 60%: kiểm tra cảnh báo màu đỏ và xác nhận rằng chưa có yêu cầu gợi ý nào được gửi. Chọn lại tên dụng cụ rồi mới bấm tìm gợi ý.
4. Thử đèn cồn cùng nhãn hóa chất: kho có gợi ý đun nóng hỗn hợp bột sắt và lưu huỳnh (không có các bước thao tác). Thử thêm một nhãn không có bài phù hợp: bản nháp mới phải được lưu trong `data/ai_lesson_drafts.json` ở trạng thái chờ duyệt, không hiển thị các bước chưa duyệt.
5. Để kiểm tra lỗi Gemini, tạm thời bỏ `GEMINI_API_KEY`, khởi động lại server rồi phân tích ảnh: kết quả nhận diện phải còn nguyên và giao diện phải báo AI chưa khả dụng. Khôi phục khóa sau khi kiểm tra.
6. Khi kho an toàn chưa có mục được duyệt, giao diện chỉ nhắc hỏi giáo viên; chi tiết an toàn chỉ xuất hiện từ mục có trạng thái duyệt hợp lệ.

### 6) Điều chỉnh khi nhận diện sai

Nếu ứng dụng không nhận diện đúng, hãy thử:

- chụp ảnh rõ hơn, sáng hơn,
- đưa dụng cụ vào giữa khung hình,
- chọn ảnh có nền đơn giản,
- kiểm tra tên nhãn trong mô hình và cập nhật `equipment_aliases` trong `data/lessons.json` nếu cần.

### 7) Lưu ý quan trọng

- Dữ liệu trong `data/lessons.json` là minh họa, chưa phải SGK chuẩn.
- Giáo viên nên rà soát lại nội dung trước khi dùng trong lớp học.
- Luôn tuân thủ quy tắc an toàn khi làm việc với hóa chất, lửa hoặc dụng cụ thủy tinh.

## Dữ liệu bài học

`data/lessons.json` chỉ chứa **dữ liệu minh họa, chưa xác thực SGK**. Trước khi dùng trong lớp, giáo viên cần thay tên bài, mục tiêu, bước thực hiện, quy tắc an toàn và nguồn trích dẫn theo đúng bộ SGK KHTN 8 đang sử dụng. `equipment_aliases` phải khớp tên lớp trong trọng số YOLO (không phân biệt chữ hoa và dấu tiếng Việt). Danh sách bài có alias phù hợp được gửi cho Gemini lựa chọn; nếu không có bài phù hợp, Gemini tạo bản nháp chờ duyệt nếu có cấu hình khóa. Gemini không được tạo cảnh báo an toàn; dữ liệu an toàn chi tiết chỉ lấy từ `data/safety_content.json` sau khi được duyệt. Có thể thêm các trường `purpose`/`use`, `characteristics` và `basic_knowledge` vào bản ghi bài học để hiển thị công dụng, đặc điểm và kiến thức cơ bản.

## API

- `GET /api/health`: trạng thái cấu hình cơ bản.
- `POST /api/analyze`: form-data `file` (JPG, PNG, WebP, mặc định tối đa 10 MB). Trả `request_id`, `width`, `height`, `detections` với `box` là `[x1,y1,x2,y2]` theo pixel ảnh gốc, `labels`, `suggestion_labels`, `supported_classes` và trạng thái đang chờ AI. Confidence trả về ở dạng thập phân từ `0` đến `1`. Nếu có nhãn dưới 60%, `suggestion_labels` chỉ gồm các nhãn đạt ngưỡng; endpoint này không chờ Gemini.
- `POST /api/suggestion`: JSON `{ "labels": ["tên dụng cụ đã xác nhận"] }`; chỉ chấp nhận lớp có trong model đang cấu hình. Gemini lựa chọn bài phù hợp từ dữ liệu bài học hoặc tạo/lưu bản nháp; khi Gemini hoặc việc lưu tệp lỗi, endpoint trả lỗi rõ ràng.
- `POST /api/explanation`: giữ tương thích cho client cũ; nhận cùng JSON và dùng chung luồng AI tìm bài/tạo bản nháp của `/api/suggestion`.
- `POST /api/feedback`: multipart gồm `file` (ảnh đã phân tích) và `metadata` (JSON có `report_id`, `request_id`, `detection_id`, `predicted_label`, `confidence`, tùy chọn `student_selected_label`). Trả `status: saved` sau khi lưu thành công.

Ảnh nhận diện chỉ được đọc trong bộ nhớ. Khi học sinh báo nhận diện sai, đúng ảnh đã phân tích được gửi vào `data/review_queue/` cùng JSON ghi nhãn dự đoán, mã yêu cầu, mã detection và tọa độ khung để phân biệt nhiều dụng cụ trong cùng ảnh. Đây là khu vực chờ kiểm tra, không được phục vụ công khai và đã được thêm vào `.gitignore`. Bản ghi có `review_status: pending` và `training_status: not_eligible_unverified`; việc chọn tên trong giao diện chỉ được lưu như thông tin tham khảo, không được coi là nhãn đã xác minh. Nếu học sinh chọn nhãn khác với dự đoán, ứng dụng ghi nhớ nhãn đó chỉ cho đúng ảnh (SHA-256 giống hệt) và đúng phiên bản model; khi tải lại ảnh đó, nhãn đã nhớ hiện ra để học sinh xác nhận lại. Cơ chế này không thay đổi trọng số hoặc độ chính xác model cho ảnh khác.

Bản nháp do AI tạo được lưu riêng trong `data/ai_lesson_drafts.json`, không được đưa vào kết quả thực hành học sinh hoặc dùng làm hướng dẫn an toàn. Giáo viên/người quản trị phải rà soát nội dung và các bước theo quy định phòng thực hành trước khi duyệt; chỉ sau khi duyệt mới được chuyển thủ công nội dung phù hợp vào `data/lessons.json`. Tệp bản nháp được loại khỏi Git và không có chức năng duyệt tự động trong ứng dụng.

Giáo viên/người quản trị cần kiểm tra ảnh và đối chiếu `detection_id`, xác nhận nhãn chính xác bằng quy trình riêng, rồi mới chuyển ảnh đã xác minh sang tập dữ liệu huấn luyện có kiểm soát. Không có chức năng duyệt nhãn hoặc huấn luyện lại tự động trong ứng dụng này; cần sao lưu, rà soát chất lượng và chạy quy trình huấn luyện riêng trước khi cập nhật `MODEL_PATH`. Camera tự quét tối đa một yêu cầu mỗi 3 giây; có thể tắt tự quét và chụp thủ công. Camera trong trình duyệt cần `localhost` hoặc HTTPS.

### Kho cảnh báo an toàn và duyệt nội dung

`data/safety_content.json` là kho nội dung tĩnh có cấu trúc, được đọc lại theo từng yêu cầu nên cập nhật không cần sửa mã nguồn hoặc khởi động lại server. Các nội dung người dùng xác nhận đã được giáo viên KHTN duyệt được đánh dấu **Đã duyệt** và có thể hiển thị cho học sinh. Hồ sơ ghi rõ tên người duyệt chưa được cung cấp; trường reviewer hiện ghi “Giáo viên KHTN (theo xác nhận của người dùng)”; cảnh báo đèn cồn được cập nhật ngày 2026-10-16, các mục khác theo ngày phê duyệt riêng trong JSON. Các mục ngoài nội dung đã xác nhận vẫn là **Chờ duyệt**, không được trình bày như hướng dẫn đã xác nhận. Giáo viên/người quản trị có thể cập nhật kho theo các bước:

1. Mở JSON trong trình soạn thảo văn bản và chọn đúng bản ghi theo `id`/`name`.
2. Kiểm tra, chỉnh `hazards`, `avoid`, `student_action` và `hazard_level` theo thiết bị thực tế, quy định phòng thực hành và hướng dẫn của nhà trường.
3. Chỉ sau khi phê duyệt chính thức, đặt `status` thành `Đã duyệt`, điền `reviewer` (tên người có thẩm quyền), `approved_at` theo ISO 8601 (ví dụ `2026-10-15T09:00:00+07:00`) và cập nhật `version`.
4. Lưu JSON hợp lệ. Server sẽ chỉ trả nội dung chi tiết khi trạng thái, người duyệt, thời gian và phiên bản đều hợp lệ. Để rút nội dung khỏi học sinh, đổi trạng thái thành `Ngừng sử dụng`.

Ứng dụng chưa có đăng nhập/phân quyền hay giao diện quản trị; quyền sửa tệp phải được giới hạn ở giáo viên/người quản trị trên máy chủ. Bản ghi chỉ được duyệt nếu thực sự đã được người có thẩm quyền kiểm tra; không sao chép trạng thái phê duyệt sang nội dung chưa được xác nhận.

## Giới hạn

Độ chính xác phụ thuộc ảnh và trọng số YOLO. Nhãn trong mô hình chưa được kiểm tra trực tiếp trong môi trường tạo dự án. Các bản ghi minh họa có thể không khớp nhãn thực tế; xem tên lớp của mô hình rồi sửa `equipment_aliases`. Luôn thực hành với giáo viên, nhất là với hóa chất, lửa hoặc thủy tinh.
