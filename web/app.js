const $ = id => document.getElementById(id);
const state = { stream: null, timer: null, busy: false, file: null, mode: 'camera', lastAnalysis: null, reports: new Map() };
const video = $('video'), preview = $('preview');

function status(message) { $('status').textContent = message; }
function tab(mode) {
  state.mode = mode;
  $('cameraPane').hidden = mode !== 'camera'; $('uploadPane').hidden = mode !== 'upload';
  $('cameraTab').classList.toggle('selected', mode === 'camera');
  $('uploadTab').classList.toggle('selected', mode === 'upload');
  if (mode === 'upload') stopCamera();
  status(mode === 'camera' ? 'Mở camera để quan sát dụng cụ.' : 'Chọn ảnh để phân tích.');
}
function clearOverlay() { for (const id of ['cameraOverlay', 'imageOverlay']) { const c = $(id); c.getContext('2d').clearRect(0, 0, c.width, c.height); } }
function stopCamera() {
  if (state.timer) clearInterval(state.timer);
  state.timer = null;
  if (state.stream) state.stream.getTracks().forEach(track => track.stop());
  state.stream = null; video.srcObject = null; clearOverlay();
  $('cameraEmpty').hidden = false; $('startCamera').disabled = false;
  $('stopCamera').disabled = true; $('capture').disabled = true;
  $('cameraState').textContent = 'Sẵn sàng';
}
async function startCamera() {
  try {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('Trình duyệt không hỗ trợ camera hoặc trang chưa dùng localhost/HTTPS.');
    state.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false });
    video.srcObject = state.stream; await video.play();
    $('cameraEmpty').hidden = true; $('startCamera').disabled = true;
    $('stopCamera').disabled = false; $('capture').disabled = false;
    $('cameraState').textContent = 'Camera đang bật'; status('Camera đã sẵn sàng. Nhấn “Phân tích khung hình”.');
    updateAutoScan();
  } catch (error) { status(`Không mở được camera: ${error.message}`); stopCamera(); }
}
function updateAutoScan() {
  if (state.timer) clearInterval(state.timer);
  state.timer = null;
  if (state.stream && $('autoScan').checked) state.timer = setInterval(() => { if (!state.busy) capture(); }, 3000);
}
function confidenceRatio(value) { const confidence = Number(value); return confidence > 1 ? confidence / 100 : confidence; }
function confidenceLabel(value) { return `${(confidenceRatio(value) * 100).toFixed(1)}%`; }
function confidenceTone(value) {
  const confidence = confidenceRatio(value);
  return confidence < .6 ? 'red' : confidence < .8 ? 'yellow' : 'green';
}
function draw(canvas, media, result) {
  canvas.width = result.width; canvas.height = result.height;
  const ctx = canvas.getContext('2d'); ctx.clearRect(0, 0, canvas.width, canvas.height);
  // The media uses object-fit: contain; canvas has the same intrinsic aspect ratio.
  ctx.lineWidth = Math.max(3, canvas.width / 250); ctx.font = `bold ${Math.max(15, canvas.width / 45)}px Segoe UI, sans-serif`;
  result.detections.forEach(item => {
    const [x1, y1, x2, y2] = item.box, label = `${item.label} ${confidenceLabel(item.confidence)}`;
    const tone = confidenceTone(item.confidence);
    ctx.strokeStyle = { red: '#d94141', yellow: '#c78a08', green: '#23864b' }[tone]; ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
    const width = ctx.measureText(label).width + 16, height = Math.max(25, canvas.width / 32);
    const top = y1 > height ? y1 - height : y1;
    ctx.fillStyle = { red: '#b52d35', yellow: '#9b6800', green: '#176c3a' }[tone]; ctx.fillRect(x1, top, width, height);
    ctx.fillStyle = '#fff'; ctx.fillText(label, x1 + 8, top + height * .72);
  });
}
function el(tag, text, className) { const node = document.createElement(tag); node.textContent = text; if (className) node.className = className; return node; }
function list(parent, heading, values, ordered = false) {
  parent.append(el('h4', heading)); const element = document.createElement(ordered ? 'ol' : 'ul');
  values.forEach(value => element.append(el('li', value))); parent.append(element);
}
function renderSuggestion(root, suggestion) {
  root.replaceChildren();
  if (!suggestion.title) {
    root.append(el('p', suggestion.message || 'Chưa có gợi ý.', 'source'));
    return;
  }
  const article = el('article', '', 'lesson'); article.append(el('h3', suggestion.title));
  if (suggestion.ai_provider === 'DeepSeek') {
    article.append(el('p', 'Phần giải thích được tạo bởi DeepSeek dự phòng.', 'source'));
  }
  if (suggestion.purpose || suggestion.use) {
    article.append(el('h4', 'Công dụng'));
    article.append(el('p', suggestion.purpose || suggestion.use));
  }
  if (suggestion.characteristics) {
    article.append(el('h4', 'Đặc điểm'));
    article.append(el('p', suggestion.characteristics));
  }
  if (suggestion.basic_knowledge) {
    article.append(el('h4', 'Kiến thức cơ bản'));
    article.append(el('p', suggestion.basic_knowledge));
  }
  if (suggestion.objective) {
    article.append(el('h4', suggestion.status === 'draft_saved_pending_review' ? 'Mục tiêu đề xuất' : 'Mục tiêu bài học'));
    article.append(el('p', suggestion.objective));
  }
  if (suggestion.steps?.length) list(article, 'Các bước tham khảo', suggestion.steps, true);
  if (suggestion.explanation) {
    const explanation = el('section', '', 'ai-explanation');
    explanation.append(el('h4', 'Giải thích thêm từ AI'));
    explanation.append(el('p', suggestion.explanation));
    article.append(explanation);
  }
  if (suggestion.message && suggestion.status !== 'draft_saved_pending_review') {
    article.append(el('p', suggestion.message, 'source'));
  }
  if (suggestion.status === 'draft_saved_pending_review') {
    article.append(el('p', suggestion.message || 'Gợi ý đang chờ giáo viên KHTN duyệt; chưa dùng làm hướng dẫn thực hành.', 'source'));
  }
  root.append(article);
}
async function loadPracticeSuggestion(labels, analysis, root, detectionRoot) {
  const requestId = (analysis.suggestionRequest || 0) + 1;
  analysis.suggestionRequest = requestId;
  try {
    const response = await fetch('/api/suggestion', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ labels }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'AI chưa thể tìm gợi ý.');
    if (state.lastAnalysis !== analysis || analysis.suggestionRequest !== requestId || !root.isConnected) return;
    if (detectionRoot) {
      analysis.result.detections.forEach(item => {
        const label = analysis.confirmedLabels?.get(item.detection_id) || item.label;
        const safety = (data.safety || []).find(entry => entry.label === label);
        const slot = detectionRoot.querySelector(`[data-detection-id="${item.detection_id}"] .safety-guidance`);
        if (safety && slot) renderSafety(slot, safety);
      });
    }
    renderSuggestion(root, data.suggestion);
  } catch (error) {
    if (state.lastAnalysis !== analysis || analysis.suggestionRequest !== requestId || !root.isConnected) return;
    renderSuggestion(root, {
      status: 'unavailable',
      message: `${error.message || 'AI chưa thể tìm gợi ý.'} Thông tin nhận diện vẫn được giữ nguyên.`,
    });
  }
}
function renderSafety(parent, safety) {
  parent.replaceChildren();
  const approved = safety?.status === 'approved';
  parent.className = `safety-guidance ${approved ? 'safety-approved' : 'safety-unapproved'}`;
  parent.append(el('h4', safety?.heading || `An toàn: ${safety?.name || 'Dụng cụ'}`));
  if (!approved) {
    parent.append(el('strong', 'CHƯA CÓ THÔNG TIN AN TOÀN ĐƯỢC DUYỆT', 'safety-state'));
    parent.append(el('p', 'Hãy hỏi giáo viên.'));
    return;
  }
  parent.append(el('strong', `ĐÃ ĐƯỢC GIÁO VIÊN DUYỆT · Mức độ: ${safety.hazard_level}`, 'safety-state'));
  if (safety.hazards?.length) list(parent, 'Nguy cơ', safety.hazards);
  list(parent, 'Cần tránh', safety.avoid);
  list(parent, 'Để an toàn', safety.student_action);
}
function show(result, source, analysis) {
  $('resultEmpty').hidden = true; $('resultContent').hidden = false;
  const detectionRoot = $('detections'); detectionRoot.replaceChildren();
  if (!result.detections.length) detectionRoot.append(el('p', 'Chưa nhận diện được dụng cụ.'));
  result.detections.forEach(item => {
    const uncertain = confidenceRatio(item.confidence) < .6;
    const card = el('article', '', `detection-item ${uncertain ? 'confidence-red' : `confidence-${confidenceTone(item.confidence)}`}`);
    card.dataset.detectionId = String(item.detection_id);
    card.append(el('span', `${item.label} · ${confidenceLabel(item.confidence)}`, 'chip'));
    if (uncertain) {
      card.append(el('p', 'AI chưa chắc chắn, em hãy hỏi thầy cô.', 'low-confidence-warning'));
      const correctionLabel = el('label', 'Chọn lại tên dụng cụ trước khi xem gợi ý', 'correction-label');
      const select = document.createElement('select'); select.setAttribute('aria-label', `Chọn tên đúng cho ${item.label}`);
      select.append(new Option('Chọn tên dụng cụ chính xác', ''));
      (result.supported_classes || []).forEach(label => select.append(new Option(label, label)));
      correctionLabel.append(select); card.append(correctionLabel);
      const confirmButton = el('button', 'Xác nhận', 'primary confirm-button'); confirmButton.type = 'button';
      const confirmStatus = el('p', '', 'feedback-status');
      confirmButton.disabled = true;
      confirmButton.onclick = () => {
        if (!select.value) {
          status('Hãy chọn tên dụng cụ chính xác trước khi xác nhận.');
          return;
        }
        analysis.confirmedLabels.set(item.detection_id, select.value);
        confirmButton.textContent = 'Đã xác nhận';
        confirmStatus.textContent = `Đã xác nhận tên dụng cụ: ${select.value}.`;
      };
      select.onchange = () => {
        analysis.confirmedLabels.delete(item.detection_id);
        confirmButton.disabled = !select.value;
        confirmButton.textContent = 'Xác nhận';
        confirmStatus.textContent = '';
      };
      const reportButton = el('button', 'Báo nhận diện sai', 'report-button'); reportButton.type = 'button';
      const reportStatus = el('p', '', 'feedback-status');
      reportButton.onclick = () => sendFeedback(item, select.value, reportButton, reportStatus);
      card.append(confirmButton, confirmStatus, reportButton, reportStatus);
    }
    const safetySlot = el('section', '', 'safety-guidance');
    renderSafety(safetySlot, item.safety);
    card.append(safetySlot);
    detectionRoot.append(card);
  });
  const lowConfidence = result.detections.filter(item => confidenceRatio(item.confidence) < .6);
  const eligibleLabels = [...new Set(result.detections
    .filter(item => confidenceRatio(item.confidence) >= .6)
    .map(item => item.label))];
  const root = $('suggestion');
  const actions = $('suggestionActions');
  analysis.confirmedLabels = new Map();
  actions.replaceChildren();
  renderSuggestion(root, result.suggestion);
  if (lowConfidence.length) {
    if (eligibleLabels.length) loadPracticeSuggestion(eligibleLabels, analysis, root, detectionRoot);
    else renderSuggestion(root, {
      status: 'needs_confirmation',
      message: 'Hãy chọn lại tên dụng cụ chưa chắc chắn trước khi AI tìm gợi ý bài thực hành.',
    });
    const continueButton = el('button', 'Tìm gợi ý sau khi xác nhận', 'primary confirm-button'); continueButton.type = 'button';
    continueButton.onclick = async () => {
      if (lowConfidence.some(item => !analysis.confirmedLabels.has(item.detection_id))) {
        status('Hãy chọn tên chính xác và bấm “Xác nhận” cho từng dụng cụ màu đỏ trước.');
        return;
      }
      const selected = analysis.confirmedLabels;
      const labels = [...new Set(result.detections.map(item => selected.get(item.detection_id) || item.label))];
      analysis.confirmedLabels = selected;
      continueButton.disabled = true; continueButton.textContent = 'AI đang tìm gợi ý…';
      renderSuggestion(root, { status: 'awaiting_ai', message: 'AI đang tìm gợi ý bài thực hành...' });
      await loadPracticeSuggestion(labels, analysis, root, detectionRoot);
      if (state.lastAnalysis === analysis) {
        continueButton.disabled = false;
        continueButton.textContent = 'Tìm gợi ý lại';
      }
    };
    actions.append(continueButton);
  } else if (result.labels.length) {
    loadPracticeSuggestion(result.labels, analysis, root, detectionRoot);
  }
  draw(source === 'camera' ? $('cameraOverlay') : $('imageOverlay'), source === 'camera' ? video : preview, result);
  status(result.detections.length ? `Đã nhận diện ${result.detections.length} vùng dụng cụ.` : 'Chưa thấy dụng cụ. Hãy thử ảnh rõ và đủ sáng hơn.');
}
async function analyze(blob, filename, source) {
  if (state.busy) return;
  state.busy = true; status('Đang nhận diện và tìm bài học…'); $('cameraState').textContent = 'Đang xử lý';
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 45000);
  try {
    const data = new FormData(); data.append('file', blob, filename);
    const response = await fetch('/api/analyze', { method: 'POST', body: data, signal: controller.signal });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Máy chủ chưa thể xử lý ảnh.');
    state.lastAnalysis = { blob, filename, source, result };
    state.reports = new Map();
    show(result, source, state.lastAnalysis);
  } catch (error) { status(error.name === 'AbortError' ? 'Quá thời gian xử lý. Hãy thử lại.' : `Có lỗi: ${error.message}`); }
  finally { clearTimeout(timer); state.busy = false; $('cameraState').textContent = state.stream ? 'Camera đang bật' : 'Sẵn sàng'; }
}
async function sendFeedback(item, selectedLabel, button, output) {
  const analysis = state.lastAnalysis;
  if (!analysis) { output.textContent = 'Không còn ảnh để gửi. Hãy phân tích ảnh lại.'; return; }
  let report = state.reports.get(item.detection_id);
  if (!report) { report = { reportId: crypto.randomUUID(), sending: false, sent: false }; state.reports.set(item.detection_id, report); }
  if (report.sending || report.sent) return;
  report.sending = true; button.disabled = true; button.textContent = 'Đang gửi ảnh…';
  output.textContent = 'Xin lỗi em! AI có thể đã nhận diện nhầm dụng cụ. Cảm ơn em đã giúp AI cải thiện độ chính xác!';
  try {
    const body = new FormData(); body.append('file', analysis.blob, analysis.filename);
    body.append('metadata', JSON.stringify({
      report_id: report.reportId, request_id: analysis.result.request_id,
      detection_id: item.detection_id, predicted_label: item.label,
      confidence: confidenceRatio(item.confidence), box: item.box,
      student_selected_label: selectedLabel || null,
    }));
    const response = await fetch('/api/feedback', { method: 'POST', body });
    const data = await response.json(); if (!response.ok || data.status !== 'saved') throw new Error(data.detail || 'Máy chủ chưa xác nhận đã lưu ảnh.');
    report.sent = true; button.textContent = 'Đã gửi';
    output.textContent = 'Đã gửi ảnh thành công! Cảm ơn em đã giúp AI học tốt hơn.';
  } catch (error) {
    button.disabled = false; button.textContent = 'Thử gửi lại';
    output.textContent = 'Chưa gửi được ảnh. Em hãy thử lại sau nhé.';
  } finally { report.sending = false; }
}
function capture() {
  if (!state.stream || !video.videoWidth || state.busy) return;
  const canvas = document.createElement('canvas'); canvas.width = video.videoWidth; canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  canvas.toBlob(blob => { if (blob) analyze(blob, 'camera.jpg', 'camera'); }, 'image/jpeg', .85);
}
$('cameraTab').onclick = () => tab('camera'); $('uploadTab').onclick = () => tab('upload');
$('startCamera').onclick = startCamera; $('stopCamera').onclick = stopCamera; $('capture').onclick = capture;
$('autoScan').onchange = updateAutoScan;
$('fileInput').onchange = event => {
  const file = event.target.files?.[0]; if (!file) return;
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024) { status('Chọn ảnh JPG, PNG hoặc WebP dưới 10 MB.'); return; }
  state.file = file; const url = URL.createObjectURL(file);
  preview.onload = () => { URL.revokeObjectURL(url); clearOverlay(); };
  preview.src = url; preview.hidden = false; $('dropzone').hidden = true;
  $('analyzeUpload').disabled = false; status(`Đã chọn ${file.name}. Nhấn “Phân tích ảnh”.`);
};
$('analyzeUpload').onclick = () => { if (state.file) analyze(state.file, state.file.name, 'upload'); };
window.addEventListener('pagehide', stopCamera);
