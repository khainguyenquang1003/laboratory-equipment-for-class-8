import io
import hashlib
import json
import math
import os
import re
import tempfile
import threading
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from uuid import UUID, uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, Request, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError
from starlette.concurrency import run_in_threadpool

load_dotenv()
ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
REVIEW_QUEUE = ROOT / "data" / "review_queue"
SAFETY_CONTENT_PATH = ROOT / "data" / "safety_content.json"
AI_LESSON_DRAFTS_PATH = ROOT / "data" / "ai_lesson_drafts.json"
LESSONS = json.loads((ROOT / "data" / "lessons.json").read_text(encoding="utf-8"))
app = FastAPI(title="Phòng thực hành KHTN 8")
app.mount("/static", StaticFiles(directory=WEB), name="static")
LOW_CONFIDENCE = 0.60
AI_LESSON_DRAFTS_LOCK = threading.Lock()

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
    "no_gloves": "không có găng tay",
    "photogate": "cổng quang điện",
    "resistor": "điện trở",
    "spoon": "thìa",
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
            "message": "AI chưa chắc chắn, em hãy hỏi thầy cô.",
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
        "heading": record.get("heading", f"An toàn: {record['name']}"),
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


def validate_ai_explanation(value: str) -> str:
    explanation = value.strip()[:700]
    explanation_text = normalized(explanation)
    sentences = explanation_text.replace("!", ".").replace("?", ".").split(".")
    blocked_terms = (
        "an toan", "nguy hiem", "canh bao", "rui ro", "tai nan", "can than",
        "khong tu y", "bao giao vien", "hoa chat doc", "hoa chat an mon",
        "pha tron hoa chat", "bao ho", "de vo",
        "khong cham", "khong nhin", "khong lam", "khong su dung",
        "huong dan", "quy trinh", "buoc",
        "safety", "safe", "danger", "warning", "hazard", "careful",
        "do not", "dont ", "teacher", "wear gloves", "wear goggles",
        "avoid", "burn", "fire", "procedure", "instructions", "please ",
        "must ", "should ", "never ", "wear ",
    )
    contains_safety_term = any(
        re.search(rf"(?<!\w){re.escape(term.strip())}(?!\w)", explanation_text)
        for term in blocked_terms
    )
    starts_with_instruction = any(
        sentence.strip().startswith(("hay ", "tranh ", "deo "))
        for sentence in sentences
    ) or any(
        re.match(r"(?im)^\s*(?:dùng|đừng)\b", sentence)
        for sentence in re.split(r"[.!?]", value)
    )
    if contains_safety_term or starts_with_instruction:
        raise ValueError("Nội dung AI chứa hướng dẫn hoặc thông tin an toàn không được phép tự tạo.")
    return explanation


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


def model_path() -> Path:
    path = Path(os.getenv("MODEL_PATH", "./my_custom_yolo11_model.pt"))
    return path if path.is_absolute() else ROOT / path


@lru_cache(maxsize=1)
def load_model(path: str, _modified_ns: int, _size: int):
    from ultralytics import YOLO

    model_file = Path(path)
    if not model_file.is_file():
        raise FileNotFoundError(f"Không tìm thấy mô hình: {model_file}")
    return YOLO(str(model_file))


def get_model():
    path = model_path()
    try:
        metadata = path.stat()
    except OSError as exc:
        raise FileNotFoundError(f"Không thể truy cập mô hình: {path}") from exc
    return load_model(str(path), metadata.st_mtime_ns, metadata.st_size)


def current_model_fingerprint() -> str:
    path = model_path()
    metadata = path.stat()
    model_version = f"{path.resolve()}:{metadata.st_mtime_ns}:{metadata.st_size}"
    return hashlib.sha256(model_version.encode("utf-8")).hexdigest()


def apply_remembered_corrections(
    image_sha256: str,
    model_fingerprint: str,
    detections: list[dict],
    supported_classes: list[str],
) -> None:
    if not REVIEW_QUEUE.exists():
        return

    allowed_classes = {normalized(label) for label in supported_classes}
    records = []
    try:
        metadata_files = REVIEW_QUEUE.glob("*.json")
        for metadata_path in metadata_files:
            try:
                record = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    f"Không thể đọc phản hồi nhận diện đã lưu: {metadata_path.name}"
                ) from exc
            if not isinstance(record, dict):
                raise RuntimeError(f"Bản ghi phản hồi không hợp lệ: {metadata_path.name}")
            selected_label = record.get("student_selected_label")
            if (
                record.get("image_sha256") != image_sha256
                or record.get("model_fingerprint") != model_fingerprint
                or not isinstance(selected_label, str)
                or not isinstance(record.get("detection_id"), int)
                or isinstance(record.get("detection_id"), bool)
                or not isinstance(record.get("box"), list)
                or len(record["box"]) != 4
                or normalized(selected_label) not in allowed_classes
                or normalized(selected_label) == normalized(str(record.get("predicted_label", "")))
            ):
                continue
            records.append(record)
    except OSError as exc:
        raise RuntimeError("Không thể truy cập hàng chờ phản hồi nhận diện.") from exc

    detections_by_id = {item["detection_id"]: item for item in detections}
    for record in sorted(records, key=lambda item: str(item.get("received_at", ""))):
        detection = detections_by_id.get(record.get("detection_id"))
        if (
            detection is None
            or normalized(detection["label"]) != normalized(str(record.get("predicted_label", "")))
            or detection["box"] != record.get("box")
        ):
            continue
        detection["model_label"] = detection["label"]
        detection["label"] = record["student_selected_label"]
        detection["corrected"] = True


def candidate_lessons(labels: list[str]) -> list[dict]:
    found = []
    normalized_labels = {normalized(label) for label in labels}
    for lesson in LESSONS["lessons"]:
        aliases = {normalized(alias) for alias in lesson["equipment_aliases"]}
        primary_aliases = {
            normalized(alias) for alias in lesson.get("primary_equipment_aliases", [])
        }
        if normalized_labels and (normalized_labels <= aliases or normalized_labels & primary_aliases):
            found.append(lesson)
    return found


def database_suggestion(labels: list[str], include_steps: bool = True) -> dict:
    if not labels:
        return {"status": "no_detection", "message": "Chưa thấy dụng cụ. Hãy chụp rõ hơn, đủ sáng và đưa dụng cụ vào giữa ảnh."}
    candidates = candidate_lessons(labels)
    if not candidates:
        return {"status": "no_match", "message": "Chưa tìm thấy bài học phù hợp trong dữ liệu hiện có.", "data_status": LESSONS["status"]}
    lesson = candidates[0]
    result = {
        "status": "matched_from_database",
        "title": lesson["title"],
        "objective": lesson["objective"],
        "steps": lesson["steps"] if include_steps else [],
        "source": lesson["source"],
        "data_status": LESSONS["status"],
    }
    for key in ("purpose", "use", "characteristics", "basic_knowledge"):
        value = lesson.get(key)
        if isinstance(value, str) and value.strip():
            result[key] = value.strip()
    return result


def generate_explanation(labels: list[str]) -> dict:
    candidates = candidate_lessons(labels)
    if not candidates:
        raise ValueError("Không có bài học trong dữ liệu để yêu cầu giải thích.")
    if not os.getenv("GEMINI_API_KEY"):
        return {"status": "unavailable", "message": "Chưa cấu hình Gemini để bổ sung phần giải thích."}

    lesson = candidates[0]
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    lesson_data = {
        key: lesson[key]
        for key in ("title", "objective", "purpose", "use", "characteristics", "basic_knowledge")
        if isinstance(lesson.get(key), str) and lesson[key].strip()
    }
    prompt = (
        "Bạn giải thích kiến thức KHTN cho học sinh lớp 8 bằng tiếng Việt đơn giản. "
        "Dựa vào bài học đã khớp và kiến thức KHTN phổ thông chính xác để giải thích công dụng, "
        "đặc điểm hoặc kiến thức liên quan. Không bịa tên bài, số liệu hay đặc tính riêng không có căn cứ. "
        "Không viết quy trình, bước thực hành, hướng dẫn sử dụng, cảnh báo hoặc lời khuyên an toàn. "
        "Viết tối đa 3 câu; nếu dữ liệu và kiến thức phổ thông không đủ, hãy nói rõ chưa có thông tin. "
        'Trả về JSON đúng định dạng {"explanation": "..."}.\n'
        + json.dumps({
            "equipment": labels,
            "lesson": lesson_data,
        }, ensure_ascii=False)
    )
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    generated = json.loads(response.text or "{}")
    explanation = generated.get("explanation")
    if not isinstance(explanation, str) or not explanation.strip():
        raise ValueError("Gemini không trả về nội dung giải thích hợp lệ.")
    return {"status": "generated", "explanation": validate_ai_explanation(explanation)}


def lesson_draft_key(labels: list[str]) -> list[str]:
    return sorted({normalized(label) for label in labels})


def read_ai_lesson_drafts() -> dict:
    if not AI_LESSON_DRAFTS_PATH.exists():
        return {"schema_version": 1, "drafts": []}
    try:
        content = json.loads(AI_LESSON_DRAFTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Không đọc được kho bản nháp bài học AI.") from exc
    if not isinstance(content, dict) or content.get("schema_version") != 1 or not isinstance(content.get("drafts"), list):
        raise RuntimeError("Kho bản nháp bài học AI có định dạng không hợp lệ.")
    return content


def find_pending_lesson_draft(labels: list[str]) -> dict | None:
    key = lesson_draft_key(labels)
    with AI_LESSON_DRAFTS_LOCK:
        content = read_ai_lesson_drafts()
        return next(
            (
                draft for draft in content["drafts"]
                if draft.get("status") == "pending_teacher_review"
                and lesson_draft_key(draft.get("equipment", [])) == key
            ),
            None,
        )


def save_pending_lesson_draft(
    labels: list[str],
    generated: dict,
    matched_lesson_id: str | None = None,
) -> dict:
    with AI_LESSON_DRAFTS_LOCK:
        content = read_ai_lesson_drafts()
        key = lesson_draft_key(labels)
        existing = next(
            (
                draft for draft in content["drafts"]
                if draft.get("status") == "pending_teacher_review"
                and lesson_draft_key(draft.get("equipment", [])) == key
            ),
            None,
        )
        if existing is not None:
            return existing

        draft = {
            "id": str(uuid4()),
            "status": "pending_teacher_review",
            "equipment": labels,
            "title": generated["title"].strip(),
            "objective": generated["objective"].strip(),
            "explanation": generated.get("explanation", "").strip(),
            "steps": [step.strip() for step in generated["steps"]],
            "matched_lesson_id": matched_lesson_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "reviewer": None,
            "approved_at": None,
        }
        content["drafts"].append(draft)
        AI_LESSON_DRAFTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=AI_LESSON_DRAFTS_PATH.parent,
                prefix=".ai_lesson_drafts.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = Path(temp_file.name)
                json.dump(content, temp_file, ensure_ascii=False, indent=2)
                temp_file.write("\n")
            os.replace(temp_path, AI_LESSON_DRAFTS_PATH)
        except OSError as exc:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            raise RuntimeError("Không lưu được bản nháp bài học AI.") from exc
        return draft


def generate_lesson_draft(labels: list[str]) -> dict:
    existing = find_pending_lesson_draft(labels)
    if existing is not None:
        return {
            "status": "draft_saved_pending_review",
            "draft_id": existing["id"],
            "message": "Đã ghi nhớ bản nháp và đang chờ giáo viên KHTN duyệt. Chưa được dùng làm hướng dẫn thực hành.",
        }
    if not os.getenv("GEMINI_API_KEY"):
        return {
            "status": "unavailable",
            "message": "Chưa cấu hình Gemini nên chưa thể tạo và lưu bản nháp bài học.",
        }

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    prompt = (
        "Tạo một BẢN NHÁP bài học KHTN phù hợp học sinh lớp 8 cho dụng cụ được cung cấp. "
        "Đây là tài liệu chờ giáo viên duyệt, không phải hướng dẫn đã xác nhận. "
        "Chỉ trả JSON gồm title (tên hoạt động), objective (mục tiêu ngắn) và steps (danh sách tối đa 5 ý). "
        "Không viết nội dung an toàn, cảnh báo, cách xử lý sự cố, lời khuyên bảo hộ hay pha trộn hóa chất. "
        "Không hướng dẫn thao tác có lửa, điện áp nguy hiểm, hóa chất ăn mòn/độc hoặc vật sắc nhọn; "
        "nếu không thể đề xuất hoạt động quan sát an toàn, ghi rõ trong objective rằng giáo viên cần xác định hoạt động. "
        "Không khẳng định đã được giáo viên hoặc SGK phê duyệt. "
        'Ví dụ định dạng: {"title":"...","objective":"...","steps":["..."]}.\n'
        + json.dumps({"equipment": labels}, ensure_ascii=False)
    )
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    try:
        generated = json.loads(response.text or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Gemini không trả về bản nháp ở định dạng hợp lệ.") from exc
    title = generated.get("title")
    objective = generated.get("objective")
    steps = generated.get("steps")
    if (
        not isinstance(title, str) or not title.strip() or len(title.strip()) > 180
        or not isinstance(objective, str) or not objective.strip() or len(objective.strip()) > 600
        or not isinstance(steps, list) or not 1 <= len(steps) <= 5
        or any(not isinstance(step, str) or not step.strip() or len(step.strip()) > 500 for step in steps)
    ):
        raise ValueError("Gemini không trả đủ tên, mục tiêu và các ý cho bản nháp.")
    draft = save_pending_lesson_draft(
        labels,
        {"title": title, "objective": objective, "steps": steps},
    )
    return {
        "status": "draft_saved_pending_review",
        "draft_id": draft["id"],
        "message": "Đã ghi nhớ bản nháp và đang chờ giáo viên KHTN duyệt. Chưa được dùng làm hướng dẫn thực hành.",
    }


def generate_practice_suggestion(labels: list[str]) -> dict:
    candidates = candidate_lessons(labels)
    normalized_labels = {normalized(label) for label in labels}
    primary_matches = [
        lesson for lesson in candidates
        if {
            normalized(alias) for alias in lesson.get("primary_equipment_aliases", [])
        } & normalized_labels
    ]
    existing = find_pending_lesson_draft(labels)
    if existing is not None and not candidates:
        return {
            "status": "draft_saved_pending_review",
            "draft_id": existing["id"],
            "title": existing["title"],
            "objective": existing["objective"],
            "message": "Đã ghi nhớ bản nháp và đang chờ giáo viên KHTN duyệt. Chưa được dùng làm hướng dẫn thực hành.",
        }
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
    if not gemini_api_key and not deepseek_api_key:
        return {
            "status": "unavailable",
            "message": "Chưa cấu hình API key Gemini hoặc DeepSeek nên chưa thể tìm hoặc tạo gợi ý bài thực hành.",
        }

    prompt = (
        "Bạn là trợ lý KHTN lớp 8. Dựa trên thiết bị được nhận diện và các bài hiện có, "
        "hãy chọn bài phù hợp nhất hoặc tạo bản nháp mới nếu không có bài nào phù hợp. "
        "Ưu tiên bài có mục tiêu khớp với tổ hợp dụng cụ và hiện tượng thí nghiệm; không chọn bài chung chung "
        "chỉ vì trùng một dụng cụ nếu có bài cụ thể phù hợp hơn. "
        "Nếu chọn bài có sẵn, lesson_id phải đúng một id trong danh sách; nếu không phù hợp, lesson_id là null. "
        "Trường explanation là phần bổ sung riêng, không được sửa, viết lại hoặc lặp lại nội dung bài học có sẵn. "
        "Hãy giải thích ngắn gọn bằng tiếng Việt ý nghĩa của thí nghiệm và bài học/kiến thức học sinh rút ra; "
        "chỉ dựa trên tên bài và mục tiêu được cung cấp, không tự khẳng định kết quả quan sát chưa có trong dữ liệu. "
        "Nếu không đủ căn cứ để rút ra ý nghĩa hoặc bài học cụ thể, hãy nói rõ điều đó thay vì suy đoán. "
        "Nếu chọn bài có sẵn, chỉ cần trả lesson_id và explanation. "
        "Nếu tạo mới, đặt title, objective và tối đa 5 steps ở mức bản nháp để giáo viên duyệt; "
        "không tạo cảnh báo an toàn, quy tắc xử lý hóa chất hoặc hướng dẫn nguy hiểm. "
        "Không đưa lời khuyên sử dụng lửa, điện nguy hiểm, hóa chất độc/ăn mòn hay vật sắc nhọn. "
        "Khi tạo mới, trả JSON gồm lesson_id, title, objective, explanation, steps; "
        "khi chọn bài có sẵn, trả JSON gồm lesson_id và explanation.\n"
        + json.dumps({
            "equipment": labels,
            "available_lessons": [
                {
                    "id": lesson["id"],
                    "title": lesson["title"],
                    "equipment_aliases": lesson["equipment_aliases"],
                    "objective": lesson["objective"],
                }
                for lesson in candidates
            ],
        }, ensure_ascii=False)
    )

    def generate_with_gemini() -> dict:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=gemini_api_key)
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        if not response.text:
            raise ValueError("Gemini returned an empty response.")
        return json.loads(response.text)

    def generate_with_deepseek() -> dict:
        request_body = json.dumps({
            "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            "messages": [
                {
                    "role": "system",
                    "content": "Return only a valid JSON object that follows the requested schema.",
                },
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }).encode("utf-8")
        request = urllib.request.Request(
            os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions"),
            data=request_body,
            headers={
                "Authorization": f"Bearer {deepseek_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"DeepSeek API returned HTTP {exc.code}; verify its key, model access, and quota."
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError("Could not connect to the DeepSeek API.") from exc
        try:
            content = result["choices"][0]["message"]["content"]
            generated_result = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("DeepSeek returned an invalid JSON response.") from exc
        if not isinstance(generated_result, dict):
            raise ValueError("DeepSeek returned an invalid JSON object.")
        return generated_result

    def validate_generated(generated: dict, provider: str) -> dict:
        lesson_id = generated.get("lesson_id")
        if lesson_id is not None and (
            not isinstance(lesson_id, str)
            or not any(lesson["id"] == lesson_id for lesson in candidates)
        ):
            raise ValueError(f"{provider} selected a lesson outside the candidate list.")
        if len(primary_matches) == 1:
            lesson_id = primary_matches[0]["id"]
        title = generated.get("title")
        objective = generated.get("objective")
        explanation = generated.get("explanation")
        steps = generated.get("steps")
        if not isinstance(explanation, str) or not explanation.strip() or len(explanation.strip()) > 700:
            raise ValueError(f"{provider} returned an invalid explanation.")
        explanation = validate_ai_explanation(explanation)

        if lesson_id is not None:
            lesson = next(lesson for lesson in candidates if lesson["id"] == lesson_id)
            _, all_safety_approved = safety_gate(labels)
            suggestion = {
                "status": "matched_with_ai",
                "title": lesson["title"],
                "objective": lesson["objective"],
                "steps": lesson["steps"] if all_safety_approved else [],
                "explanation": explanation,
                "ai_provider": provider,
            }
            for key in ("purpose", "use", "characteristics", "basic_knowledge"):
                value = lesson.get(key)
                if isinstance(value, str) and value.strip():
                    suggestion[key] = value.strip()
            return suggestion

        if (
            not isinstance(title, str) or not title.strip() or len(title.strip()) > 180
            or not isinstance(objective, str) or not objective.strip() or len(objective.strip()) > 600
            or not isinstance(steps, list) or not 1 <= len(steps) <= 5
            or any(not isinstance(step, str) or not step.strip() or len(step.strip()) > 500 for step in steps)
        ):
            raise ValueError(f"{provider} returned incomplete draft fields.")
        title = validate_ai_explanation(title)
        objective = validate_ai_explanation(objective)
        draft = save_pending_lesson_draft(
            labels,
            {
                "title": title,
                "objective": objective,
                "explanation": explanation,
                "steps": steps,
            },
        )
        return {
            "status": "draft_saved_pending_review",
            "draft_id": draft["id"],
            "title": draft["title"],
            "objective": draft["objective"],
            "explanation": draft["explanation"],
            "ai_provider": provider,
            "message": "AI đã tạo và ghi nhớ gợi ý mới. Nội dung đang chờ giáo viên KHTN duyệt, chưa dùng làm hướng dẫn thực hành.",
        }

    gemini_error = None
    if gemini_api_key:
        try:
            return validate_generated(generate_with_gemini(), "Gemini")
        except Exception as exc:
            gemini_error = exc

    if deepseek_api_key:
        try:
            return validate_generated(generate_with_deepseek(), "DeepSeek")
        except Exception as deepseek_error:
            if gemini_error is not None:
                raise RuntimeError(
                    "Gemini và DeepSeek đều không thể tạo gợi ý. Hãy kiểm tra trạng thái dịch vụ, API key và hạn mức."
                ) from deepseek_error
            raise

    if gemini_error is None:
        return {
            "status": "unavailable",
            "message": "Chưa cấu hình API key Gemini hoặc DeepSeek nên chưa thể tìm hoặc tạo gợi ý bài thực hành.",
        }
    if len(primary_matches) == 1:
        lesson = primary_matches[0]
        _, all_safety_approved = safety_gate(labels)
        message = (
            "Gemini đang tạm thời lỗi. Đang hiển thị gợi ý đã có trong dữ liệu; "
            "chưa cấu hình DeepSeek nên chưa có phần giải thích AI."
        )
        try:
            from google.genai.errors import ServerError
            if isinstance(gemini_error, ServerError) and gemini_error.code == 503:
                message = (
                    "Gemini đang tạm thời quá tải (503). Đang hiển thị gợi ý đã có trong dữ liệu; "
                    "chưa cấu hình DeepSeek nên chưa có phần giải thích AI."
                )
        except ImportError:
            pass
        return {
            "status": "matched_without_ai",
            "title": lesson["title"],
            "objective": lesson["objective"],
            "steps": lesson["steps"] if all_safety_approved else [],
            "message": message,
        }
    if gemini_error is not None:
        raise RuntimeError(
            "Gemini không thể tạo gợi ý và chưa cấu hình DeepSeek làm dự phòng."
        ) from gemini_error


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
    return {
        "status": "ok",
        "model_path": os.getenv("MODEL_PATH", "./my_custom_yolo11_model.pt"),
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
        "deepseek_configured": bool(os.getenv("DEEPSEEK_API_KEY")),
    }


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)):
    limit = int(os.getenv("MAX_UPLOAD_MB", "10")) * 1024 * 1024
    raw = await file.read(limit + 1)
    image = valid_image(raw, file.content_type or "", limit)
    try:
        model = get_model()
        fingerprint = current_model_fingerprint()
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
        classes = supported_labels(model)
        apply_remembered_corrections(
            hashlib.sha256(raw).hexdigest(),
            fingerprint,
            detections,
            classes,
        )
        labels = sorted({item["label"] for item in detections})
        confirmed_labels = sorted({
            item["label"] for item in detections
            if item["confidence"] >= LOW_CONFIDENCE and not item.get("corrected")
        })
        uncertain = any(
            item["confidence"] < LOW_CONFIDENCE or item.get("corrected")
            for item in detections
        )
        for item in detections:
            if item.get("corrected"):
                item["safety"] = {
                    "status": "uncertain",
                    "name": item["label"],
                    "message": "Đây là nhãn đã ghi nhớ từ lần sửa trước, chưa được giáo viên xác nhận. Hãy hỏi thầy cô.",
                }
            else:
                item["safety"] = safety_content_for(item["label"], item["confidence"])
    except Exception as exc:
        raise HTTPException(503, f"Không thể chạy mô hình nhận diện: {exc}") from exc
    safety_items, _ = safety_gate(labels)
    if not labels:
        safety_items = [{
            "label": "Chưa xác định",
            "status": "missing",
            "message": "AI chưa xác định được dụng cụ. Em hãy hỏi thầy cô trước khi tiếp tục.",
        }]
    if uncertain and not confirmed_labels:
        suggestion = {"status": "needs_confirmation", "message": "Hãy xác nhận tên dụng cụ có độ tin cậy thấp trước khi gửi yêu cầu cho AI."}
    elif labels:
        suggestion = {
            "status": "awaiting_ai",
            "message": "Đang gửi tên dụng cụ cho AI tìm gợi ý bài thực hành...",
        }
    else:
        suggestion = {"status": "no_detection", "message": "Chưa thấy dụng cụ. Hãy chụp rõ hơn, đủ sáng và đưa dụng cụ vào giữa ảnh."}
    return {
        "request_id": str(uuid4()),
        "model_fingerprint": fingerprint,
        "width": image.width,
        "height": image.height,
        "detections": detections,
        "safety": safety_items,
        "labels": labels,
        "suggestion_labels": confirmed_labels if uncertain else labels,
        "supported_classes": classes,
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
    safety_items, _ = safety_gate(labels)
    try:
        practice_suggestion = await run_in_threadpool(generate_practice_suggestion, labels)
    except Exception as exc:
        raise HTTPException(502, "AI chưa thể tìm hoặc tạo gợi ý bài thực hành.") from exc
    return {
        "suggestion": practice_suggestion,
        "safety": safety_items,
        "data_notice": LESSONS["notice"],
    }


@app.post("/api/explanation")
async def explanation(request: Request):
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(400, "Dữ liệu yêu cầu giải thích không hợp lệ.") from exc
    labels = body.get("labels") if isinstance(body, dict) else None
    if not isinstance(labels, list) or not labels or not all(isinstance(label, str) for label in labels):
        raise HTTPException(400, "Cần cung cấp tên dụng cụ đã xác nhận.")
    allowed = {normalized(label) for label in supported_labels(get_model())}
    if any(normalized(label) not in allowed for label in labels):
        raise HTTPException(400, "Tên dụng cụ không thuộc lớp mà mô hình hỗ trợ.")
    try:
        return await run_in_threadpool(generate_practice_suggestion, labels)
    except Exception as exc:
        raise HTTPException(502, "AI chưa thể tìm hoặc tạo gợi ý bài thực hành.") from exc


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
        student_selected_label = report.get("student_selected_label")
        reported_model_fingerprint = report.get("model_fingerprint")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "Thông tin nhận diện gửi kèm không hợp lệ.") from exc
    if detection_id < 0 or not 0 <= confidence <= 1 or not predicted_label or len(box) != 4 or not all(math.isfinite(value) for value in box):
        raise HTTPException(400, "Thông tin nhận diện gửi kèm không hợp lệ.")
    if student_selected_label is not None:
        if not isinstance(student_selected_label, str) or not student_selected_label.strip():
            raise HTTPException(400, "Tên dụng cụ được chọn không hợp lệ.")
        student_selected_label = student_selected_label.strip()[:120]
        if normalized(student_selected_label) not in {
            normalized(label) for label in supported_labels(get_model())
        }:
            raise HTTPException(400, "Tên dụng cụ được chọn không thuộc lớp mà mô hình hỗ trợ.")
    if reported_model_fingerprint is not None and (
        not isinstance(reported_model_fingerprint, str) or len(reported_model_fingerprint) > 500
    ):
        raise HTTPException(400, "Phiên bản mô hình gửi kèm không hợp lệ.")

    extension = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[file.content_type]
    image_path = REVIEW_QUEUE / f"{report_id}{extension}"
    metadata_path = REVIEW_QUEUE / f"{report_id}.json"
    image_sha256 = hashlib.sha256(raw).hexdigest()
    current_fingerprint = current_model_fingerprint()
    correction_remembered = bool(
        student_selected_label
        and normalized(student_selected_label) != normalized(predicted_label)
        and reported_model_fingerprint == current_fingerprint
    )
    if metadata_path.exists():
        try:
            existing_record = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(500, "Không thể đọc báo cáo đã lưu.") from exc
        if not isinstance(existing_record, dict):
            raise HTTPException(500, "Bản ghi báo cáo đã lưu không hợp lệ.")
        return {
            "status": "saved",
            "report_id": report_id,
            "correction_remembered": bool(
                existing_record.get("image_sha256") == image_sha256
                and existing_record.get("model_fingerprint") == current_fingerprint
                and isinstance(existing_record.get("student_selected_label"), str)
                and normalized(existing_record["student_selected_label"])
                != normalized(str(existing_record.get("predicted_label", "")))
            ),
        }

    REVIEW_QUEUE.mkdir(parents=True, exist_ok=True)
    record = {
        "report_id": report_id,
        "request_id": request_id,
        "detection_id": detection_id,
        "box": box,
        "predicted_label": predicted_label,
        "confidence": confidence,
        "student_selected_label": student_selected_label,
        "image_sha256": image_sha256,
        "model_fingerprint": reported_model_fingerprint,
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
    return {
        "status": "saved",
        "report_id": report_id,
        "correction_remembered": correction_remembered,
    }
