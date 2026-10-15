import io
import json
import math
import os
import unicodedata
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from uuid import UUID, uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, Request, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError

load_dotenv()
ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
REVIEW_QUEUE = ROOT / "data" / "review_queue"
SAFETY_CONTENT_PATH = ROOT / "data" / "safety_content.json"
LESSONS = json.loads((ROOT / "data" / "lessons.json").read_text(encoding="utf-8"))
app = FastAPI(title="Phòng thực hành KHTN 8")
app.mount("/static", StaticFiles(directory=WEB), name="static")
LOW_CONFIDENCE = 0.60

LABEL_TRANSLATIONS = {
    "alcohol lamp": "đèn cồn",
    "erlen": "bình tam giác",
    "iron test stand": "giá thí nghiệm",
    "joulemeter": "đồng hồ đo năng lượng",
    "measuring tube": "ống đong",
    "minor chemicals": "hóa chất",
    "pipet": "pipet",
    "rack for test tubes": "giá ống nghiệm",
    "test tube": "ống nghiệm",
    "test tube clamp": "kẹp ống nghiệm",
    "variable resistor": "biến trở",
    "voltmeter": "vôn kế",
    "ammeter": "ampe kế",
    "battery": "pin",
    "fuse": "cầu chì",
    "gloves": "găng tay",
    "goggles": "kính bảo hộ",
    "graduated beaker": "cốc có chia độ",
    "labcoat": "áo blouse",
    "magnifying glass": "kính lúp",
    "microscope": "kính hiển vi",
    "photogate": "cổng quang điện",
    "resistor": "điện trở",
    "switch": "công tắc",
}


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFD", value.lower())
    return "".join(c for c in value if unicodedata.category(c) != "Mn").replace("đ", "d").strip()


def translated_label(label: str) -> str:
    return LABEL_TRANSLATIONS.get(normalized(label), label)


def safety_content_for(label: str, confidence: float | None = None) -> dict:
    if confidence is not None and confidence < LOW_CONFIDENCE:
        return {
            "status": "uncertain",
            "name": label,
            "message": "AI chưa chắc chắn về dụng cụ này. Em hãy hỏi thầy cô trước khi tiếp tục.",
        }
    try:
        content = json.loads(SAFETY_CONTENT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "unavailable", "name": label, "message": "Chưa có nội dung an toàn đã được giáo viên KHTN duyệt. Em hãy hỏi thầy cô."}
    target = normalized(label)
    record = next(
        (item for item in content.get("items", []) if target in {normalized(alias) for alias in item.get("aliases", [])}),
        None,
    )
    if record is None or record.get("status") == "Ngừng sử dụng":
        return {"status": "missing", "name": label, "message": "Chưa có nội dung an toàn đã được giáo viên KHTN duyệt cho dụng cụ này. Em hãy hỏi thầy cô."}
    approval_time = record.get("approved_at")
    approval_is_valid = False
    if isinstance(approval_time, str):
        try:
            datetime.fromisoformat(approval_time.replace("Z", "+00:00"))
            approval_is_valid = True
        except ValueError:
            pass
    if (
        record.get("status") != "Đã duyệt"
        or not isinstance(record.get("reviewer"), str)
        or not record["reviewer"].strip()
        or not approval_is_valid
        or not isinstance(record.get("version"), str)
        or not record["version"].strip()
    ):
        return {"status": "pending", "name": record.get("name", label), "message": "Chưa có nội dung an toàn đã được giáo viên KHTN duyệt. Em hãy hỏi thầy cô trước khi tiếp tục."}
    return {
        "status": "approved",
        "id": record["id"],
        "name": record["name"],
        "hazard_level": record["hazard_level"],
        "hazards": record["hazards"],
        "avoid": record["avoid"],
        "student_action": record["student_action"],
        "reviewer": record["reviewer"],
        "approved_at": approval_time,
        "version": record["version"],
    }


def safety_gate(labels: list[str]) -> tuple[list[dict], bool]:
    entries = [{"label": label, **safety_content_for(label)} for label in labels]
    return entries, all(entry["status"] == "approved" for entry in entries)


def supported_labels(model) -> list[str]:
    names = model.names.values() if isinstance(model.names, dict) else model.names
    return sorted({translated_label(str(name)) for name in names})


def valid_image(raw: bytes, content_type: str, limit: int) -> Image.Image:
    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(415, "Chỉ nhận ảnh JPG, PNG hoặc WebP.")
    if len(raw) > limit:
        raise HTTPException(413, "Ảnh vượt quá dung lượng cho phép.")
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
        image = image.convert("RGB")
        if image.width * image.height > 20_000_000:
            raise HTTPException(413, "Kích thước ảnh quá lớn.")
        return image
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(400, "Không đọc được ảnh. Hãy chọn ảnh khác.")


@lru_cache(maxsize=1)
def get_model():
    from ultralytics import YOLO

    path = Path(os.getenv("MODEL_PATH", "./my_custom_yolo11_model.pt"))
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        raise FileNotFoundError(f"Không tìm thấy mô hình: {path}")
    return YOLO(str(path))


def candidate_lessons(labels: list[str]) -> list[dict]:
    found = []
    for lesson in LESSONS["lessons"]:
        aliases = [normalized(a) for a in lesson["equipment_aliases"]]
        if any(normalized(label) in aliases for label in labels):
            found.append(lesson)
    return found


def safe_fallback(lesson: dict, labels: list[str], reason: str) -> dict:
    return {
        "status": "matched_without_gemini",
        "title": lesson["title"],
        "reason": f"Dụng cụ nhận diện được: {', '.join(labels)}. {reason}",
        "objective": lesson["objective"],
        "steps": lesson["steps"],
        "source": lesson["source"],
        "data_status": LESSONS["status"],
    }


def lesson_suggestion(labels: list[str]) -> dict:
    if not labels:
        return {"status": "no_detection", "message": "Chưa thấy dụng cụ. Hãy chụp rõ hơn, đủ sáng và đưa dụng cụ vào giữa ảnh."}
    candidates = candidate_lessons(labels)
    if not candidates:
        return {"status": "no_match", "message": "Chưa tìm thấy bài thực hành phù hợp trong dữ liệu hiện có.", "data_status": LESSONS["status"]}
    lesson = candidates[0]
    if not os.getenv("GEMINI_API_KEY"):
        return safe_fallback(lesson, labels, "Chưa cấu hình Gemini; nội dung lấy từ dữ liệu minh họa.")
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        prompt = (
            "Bạn hỗ trợ học sinh lớp 8. Chỉ dùng dữ liệu JSON sau. "
            "Chọn đúng một lesson.id trong candidates; không thêm bước, mục tiêu hay quy tắc an toàn mới. "
            "Viết reason tiếng Việt ngắn gọn dựa trên nhãn dụng cụ. "
            "Trả JSON gồm lesson_id và reason. Nếu không phù hợp, lesson_id là null.\n"
            + json.dumps({
                "detected_labels": labels,
                "candidates": [
                    {key: value for key, value in lesson.items() if key != "safety"}
                    for lesson in candidates
                ],
            }, ensure_ascii=False)
        )
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        choice = json.loads(response.text or "{}")
        selected = next((x for x in candidates if x["id"] == choice.get("lesson_id")), None)
        if selected is None:
            return {"status": "no_match", "message": "Gemini chưa chọn được bài phù hợp từ dữ liệu hiện có.", "data_status": LESSONS["status"]}
        result = safe_fallback(selected, labels, "")
        result["status"] = "matched_with_gemini"
        result["reason"] = str(choice.get("reason", ""))[:300] or result["reason"]
        return result
    except Exception:
        return safe_fallback(lesson, labels, "Gemini tạm thời không khả dụng; nội dung lấy từ dữ liệu minh họa.")


@app.get("/")
def home():
    return FileResponse(WEB / "about.html")


@app.get("/practice")
def dashboard():
    return FileResponse(WEB / "index.html")


@app.get("/about")
def about():
    return FileResponse(WEB / "about.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "model_path": os.getenv("MODEL_PATH", "./my_custom_yolo11_model.pt"), "gemini_configured": bool(os.getenv("GEMINI_API_KEY"))}


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)):
    limit = int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024
    raw = await file.read(limit + 1)
    image = valid_image(raw, file.content_type or "", limit)
    try:
        model = get_model()
        result = model.predict(image, conf=float(os.getenv("CONFIDENCE_THRESHOLD", "0.25")), verbose=False)[0]
        detections = []
        if result.boxes is not None:
            for box in result.boxes:
                class_id = int(box.cls.item())
                raw_label = str(result.names[class_id])
                confidence = float(box.conf.item())
                if normalized(raw_label) == "goggles" and confidence < float(os.getenv("GOGGLES_MIN_CONFIDENCE", "0.55")):
                    continue
                detections.append({
                    "detection_id": len(detections),
                    "label": translated_label(raw_label),
                    "confidence": round(confidence, 3),
                    "box": [round(float(x), 1) for x in box.xyxy[0].tolist()],
                })
        labels = sorted({item["label"] for item in detections})
        uncertain = any(item["confidence"] < LOW_CONFIDENCE for item in detections)
        for item in detections:
            item["safety"] = safety_content_for(item["label"], item["confidence"])
    except Exception as exc:
        raise HTTPException(503, f"Không thể chạy mô hình nhận diện: {exc}") from exc
    safety_items, safety_approved = safety_gate(labels)
    if not labels:
        safety_items = [{
            "label": "Chưa xác định",
            "status": "missing",
            "message": "AI chưa xác định được dụng cụ. Em hãy hỏi thầy cô trước khi tiếp tục.",
        }]
    if uncertain:
        suggestion = {"status": "needs_confirmation", "message": "Hãy xác nhận tên dụng cụ có độ tin cậy thấp trước khi xem gợi ý bài học."}
    elif labels and not safety_approved:
        suggestion = {"status": "safety_review_required", "message": "Chưa có nội dung an toàn đã được giáo viên KHTN duyệt cho tất cả dụng cụ này. Em hãy hỏi thầy cô trước khi tiếp tục."}
    else:
        suggestion = lesson_suggestion(labels)
    return {
        "request_id": str(uuid4()),
        "width": image.width,
        "height": image.height,
        "detections": detections,
        "safety": safety_items,
        "labels": labels,
        "supported_classes": supported_labels(model),
        "suggestion": suggestion,
        "data_notice": LESSONS["notice"],
    }


@app.post("/api/suggestion")
async def suggestion(request: Request):
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, "Dữ liệu xác nhận không hợp lệ.") from exc
    labels = body.get("labels") if isinstance(body, dict) else None
    if not isinstance(labels, list) or not labels or not all(isinstance(label, str) for label in labels):
        raise HTTPException(400, "Cần cung cấp tên dụng cụ đã xác nhận.")
    allowed = {normalized(label) for label in supported_labels(get_model())}
    if any(normalized(label) not in allowed for label in labels):
        raise HTTPException(400, "Tên dụng cụ không thuộc lớp mà mô hình hỗ trợ.")
    safety_items, safety_approved = safety_gate(labels)
    if not safety_approved:
        return {
            "suggestion": {"status": "safety_review_required", "message": "Chưa có nội dung an toàn đã được giáo viên KHTN duyệt cho tất cả dụng cụ này. Em hãy hỏi thầy cô trước khi tiếp tục."},
            "safety": safety_items,
            "data_notice": LESSONS["notice"],
        }
    return {"suggestion": lesson_suggestion(labels), "safety": safety_items, "data_notice": LESSONS["notice"]}


@app.post("/api/feedback")
async def feedback(file: UploadFile = File(...), metadata: str = File(...)):
    limit = int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024
    raw = await file.read(limit + 1)
    valid_image(raw, file.content_type or "", limit)
    if len(metadata) > 16_384:
        raise HTTPException(413, "Thông tin báo cáo quá lớn.")
    try:
        report = json.loads(metadata)
        request_id = str(UUID(report["request_id"]))
        report_id = str(UUID(report["report_id"]))
        detection_id = int(report["detection_id"])
        confidence = float(report["confidence"])
        predicted_label = str(report["predicted_label"])[:120]
        box = [float(value) for value in report["box"]]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "Thông tin nhận diện gửi kèm không hợp lệ.") from exc
    if detection_id < 0 or not 0 <= confidence <= 1 or not predicted_label or len(box) != 4 or not all(math.isfinite(value) for value in box):
        raise HTTPException(400, "Thông tin nhận diện gửi kèm không hợp lệ.")

    extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[file.content_type]
    image_path = REVIEW_QUEUE / f"{report_id}{extension}"
    metadata_path = REVIEW_QUEUE / f"{report_id}.json"
    if metadata_path.exists():
        return {"status": "saved", "report_id": report_id}

    REVIEW_QUEUE.mkdir(parents=True, exist_ok=True)
    record = {
        "report_id": report_id,
        "request_id": request_id,
        "detection_id": detection_id,
        "box": box,
        "predicted_label": predicted_label,
        "confidence": confidence,
        "student_selected_label": str(report.get("student_selected_label", ""))[:120] or None,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "review_status": "pending",
        "training_status": "not_eligible_unverified",
    }
    temp_image = REVIEW_QUEUE / f".{report_id}{extension}.tmp"
    temp_metadata = REVIEW_QUEUE / f".{report_id}.json.tmp"
    try:
        temp_image.write_bytes(raw)
        temp_metadata.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_image.replace(image_path)
        temp_metadata.replace(metadata_path)
    except OSError as exc:
        temp_image.unlink(missing_ok=True)
        temp_metadata.unlink(missing_ok=True)
        image_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        raise HTTPException(500, "Không thể lưu ảnh vào hàng chờ kiểm duyệt.") from exc
    return {"status": "saved", "report_id": report_id}
