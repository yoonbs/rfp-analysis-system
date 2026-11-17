/* ==========================================================================
 * main.js
 * R&D 사업 제안요청서(RFP) 분석 시스템 - 프론트엔드 로직
 *  - 파일 드래그앤드롭 / PDF·HWPX·TXT 텍스트 추출 (클라이언트에서 수행)
 *  - 추출 텍스트를 Flask API(/api/analyze)로 전송하여 분석
 *  - 결과 대시보드 렌더링 / Chart.js 레이더 차트 / 인쇄
 * ========================================================================== */

pdfjsLib.GlobalWorkerOptions.workerSrc =
    'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/2.16.105/pdf.worker.min.js';

// --- 1. 전역 상태 ---------------------------------------------------------
let currentExtractedText = '';
let currentFileName = '';
let currentAnalysisResult = null;
let radarChartInstance = null;

document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    initDropzone();

    const textArea = document.getElementById('text-input');
    textArea.addEventListener('input', (e) => {
        document.getElementById('text-length').textContent =
            e.target.value.length.toLocaleString();
        currentExtractedText = e.target.value;
        if (!currentFileName) currentFileName = '직접 입력 문서';
    });
});

// --- 2. UI 제어 유틸리티 --------------------------------------------------
function escapeHtml(value) {
    return String(value === undefined || value === null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function showAlert(msg) {
    document.getElementById('alert-message').textContent = msg;
    document.getElementById('alert-modal').classList.remove('hidden');
}
function closeAlert() {
    document.getElementById('alert-modal').classList.add('hidden');
}

function showUploadView() {
    document.getElementById('view-result').classList.remove('active');
    document.getElementById('result-header').classList.add('hidden');
    document.getElementById('view-upload').classList.add('active');
    currentExtractedText = '';
    currentFileName = '';
    currentAnalysisResult = null;
    document.getElementById('text-input').value = '';
    document.getElementById('text-length').textContent = '0';
    document.getElementById('file-input').value = '';
}

function showResultView() {
    document.getElementById('view-upload').classList.remove('active');
    document.getElementById('result-header').classList.remove('hidden');
    document.getElementById('view-result').classList.add('active');
    document.querySelectorAll('.nav-item')[0].click();
}

function setStatus(loading, title = '', desc = '') {
    const panel = document.getElementById('status-panel');
    const btn = document.getElementById('btn-analyze');
    if (loading) {
        panel.classList.remove('hidden');
        document.getElementById('status-title').textContent = title;
        document.getElementById('status-desc').textContent = desc;
        btn.disabled = true;
        btn.classList.add('opacity-50');
    } else {
        panel.classList.add('hidden');
        btn.disabled = false;
        btn.classList.remove('opacity-50');
    }
}

function initTabs() {
    const navItems = document.querySelectorAll('.nav-item');
    const sections = document.querySelectorAll('.section-content');
    navItems.forEach((item) => {
        item.addEventListener('click', () => {
            if (window.matchMedia('print').matches) return;
            navItems.forEach((nav) => nav.classList.remove('active'));
            item.classList.add('active');
            const targetId = item.getAttribute('data-target');
            sections.forEach((sec) => {
                sec.classList.toggle('active', sec.id === targetId);
            });
        });
    });
}

// --- 3. 파일 처리 및 추출 로직 (클라이언트 사이드) -----------------------
function initDropzone() {
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-input');

    dropzone.addEventListener('click', () => fileInput.click());
    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });
    dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragover'));
    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length) handleFile(e.target.files[0]);
    });
}

async function handleFile(file) {
    currentFileName = file.name;
    const ext = file.name.split('.').pop().toLowerCase();

    if (ext === 'hwp') {
        showAlert(
            "HWP 파일은 텍스트 추출이 제한적입니다. 원활한 분석을 위해 한글 프로그램에서 'PDF' 또는 'HWPX'로 저장한 뒤 업로드해 주세요."
        );
        return;
    }

    setStatus(true, '파일 읽는 중...', '텍스트를 추출하고 있습니다.');
    try {
        let text = '';
        if (ext === 'pdf') {
            text = await extractFromPDF(file);
        } else if (ext === 'hwpx') {
            text = await extractFromHWPX(file);
        } else if (ext === 'txt') {
            text = await file.text();
        } else {
            showAlert('지원하지 않는 파일 형식입니다. (PDF, HWPX, TXT 지원)');
            setStatus(false);
            return;
        }

        if (text.trim().length < 50) {
            showAlert('추출된 텍스트가 너무 적습니다. 스캔된 이미지 형태의 문서일 수 있습니다.');
        }

        currentExtractedText = text;
        document.getElementById('text-input').value = text;
        document.getElementById('text-length').textContent = text.length.toLocaleString();
    } catch (err) {
        console.error(err);
        showAlert('파일 추출 중 오류가 발생했습니다: ' + err.message);
    } finally {
        setStatus(false);
    }
}

async function extractFromPDF(file) {
    const arrayBuffer = await file.arrayBuffer();
    const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    let fullText = '';
    for (let i = 1; i <= pdf.numPages; i++) {
        const page = await pdf.getPage(i);
        const textContent = await page.getTextContent();
        const pageText = textContent.items.map((item) => item.str).join(' ');
        fullText += `\n--- [${i}페이지] ---\n` + pageText;
    }
    return fullText;
}

async function extractFromHWPX(file) {
    const arrayBuffer = await file.arrayBuffer();
    const zip = await JSZip.loadAsync(arrayBuffer);
    let fullText = '';

    for (const filename of Object.keys(zip.files)) {
        if (filename.startsWith('Contents/section') && filename.endsWith('.xml')) {
            const xmlText = await zip.files[filename].async('text');
            const textNodeRegex = /<hp:t[^>]*>(.*?)<\/hp:t>/g;
            let match;
            while ((match = textNodeRegex.exec(xmlText)) !== null) {
                fullText +=
                    match[1]
                        .replace(/&lt;/g, '<')
                        .replace(/&gt;/g, '>')
                        .replace(/&amp;/g, '&') + ' ';
            }
            fullText += '\n';
        }
    }
    return fullText;
}

// --- 4. 백엔드 API 연동 ---------------------------------------------------
async function startAnalysis(isReanalysis = false) {
    if (!currentExtractedText || currentExtractedText.trim().length < 50) {
        showAlert('분석할 텍스트가 부족합니다. 문서를 업로드하거나 텍스트를 직접 입력해 주세요.');
        return;
    }

    if (isReanalysis) {
        showUploadViewForReanalysis();
    }

    setStatus(
        true,
        isReanalysis ? '역량 기반 재분석 중...' : 'AI 분석 중...',
        '서버에서 제안요청서를 심층 분석하고 있습니다. (약 10~60초 소요)'
    );

    try {
        const res = await fetch('/api/analyze', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: currentExtractedText,
                filename: currentFileName || '직접 입력 문서',
            }),
        });

        const payload = await res.json().catch(() => ({}));
        if (!res.ok || !payload.ok) {
            throw new Error(payload.error || `HTTP ${res.status}`);
        }

        if (isReanalysis && currentAnalysisResult) {
            currentAnalysisResult.ttaPerspective = payload.data.ttaPerspective;
            currentAnalysisResult.judgment = payload.data.judgment;
        } else {
            currentAnalysisResult = payload.data;
        }

        if (payload.history) renderHistory(payload.history);
        if (payload.truncated) {
            showAlert('문서가 매우 길어 앞부분 일부만 분석에 사용되었습니다.');
        }

        renderDashboard(currentAnalysisResult);
        showResultView();
    } catch (err) {
        console.error(err);
        showAlert('AI 분석 중 오류가 발생했습니다.\n(' + err.message + ')');
        if (isReanalysis && currentAnalysisResult) showResultView();
    } finally {
        setStatus(false);
    }
}

function showUploadViewForReanalysis() {
    // 재분석 중 로딩 패널이 보이도록 업로드 뷰로 잠시 전환
    document.getElementById('view-result').classList.remove('active');
    document.getElementById('view-upload').classList.add('active');
    document.getElementById('text-input').value = currentExtractedText;
    document.getElementById('text-length').textContent =
        currentExtractedText.length.toLocaleString();
}

async function reanalyzeSection45() {
    if (!currentExtractedText || !currentAnalysisResult) {
        showAlert('재분석할 원문 텍스트가 없습니다.');
        return;
    }
    await startAnalysis(true);
}

// --- 5. 히스토리 ----------------------------------------------------------
function renderHistory(history) {
    const listObj = document.getElementById('history-list');
    if (!history || history.length === 0) {
        listObj.innerHTML =
            '<p class="text-xs text-gray-500 text-center mt-4">분석 이력이 없습니다.</p>';
        return;
    }

    listObj.innerHTML = history
        .map(
            (h) => `
        <div class="p-3 border-b border-gray-200 cursor-pointer hover:bg-gray-100 transition" onclick="loadHistory(${h.id})">
            <p class="text-xs font-bold text-gray-800 truncate mb-1" title="${escapeHtml(h.title)}">${escapeHtml(h.title)}</p>
            <div class="flex justify-between items-center text-xs text-gray-500">
                <span class="truncate w-3/4">${escapeHtml(h.filename)}</span>
                <span>${escapeHtml(h.date)}</span>
            </div>
        </div>`
        )
        .join('');
}

async function loadHistory(id) {
    try {
        const res = await fetch(`/api/history/${id}`);
        const payload = await res.json();
        if (!res.ok || !payload.ok) throw new Error(payload.error || `HTTP ${res.status}`);

        currentFileName = payload.filename;
        currentExtractedText = payload.rawText || '';
        currentAnalysisResult = payload.data;
        renderDashboard(currentAnalysisResult);
        showResultView();
    } catch (err) {
        console.error(err);
        showAlert('분석 이력을 불러오지 못했습니다.\n(' + err.message + ')');
    }
}

function downloadJSON() {
    if (!currentAnalysisResult) return;
    const dataStr =
        'data:text/json;charset=utf-8,' +
        encodeURIComponent(JSON.stringify(currentAnalysisResult, null, 2));
    const a = document.createElement('a');
    a.setAttribute('href', dataStr);
    a.setAttribute('download', `RFP분석_${new Date().getTime()}.json`);
    a.click();
}

// --- 6. 설정(연구소 역량) -------------------------------------------------
function openSettingsModal() {
    document.getElementById('settings-modal').classList.remove('hidden');
}
function closeSettingsModal() {
    document.getElementById('settings-modal').classList.add('hidden');
}

async function saveSettings() {
    const val = document.getElementById('tta-capabilities').value;
    try {
        const res = await fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ capabilities: val }),
        });
        const payload = await res.json();
        if (!res.ok || !payload.ok) throw new Error(payload.error || `HTTP ${res.status}`);
        closeSettingsModal();
        showAlert('연구소 역량이 서버에 저장되었습니다. 이후 분석 시 적용됩니다.');
    } catch (err) {
        showAlert('설정 저장에 실패했습니다.\n(' + err.message + ')');
    }
}

// --- 7. 대시보드 렌더링 ---------------------------------------------------
function getMatchBadge(level) {
    if (level === '상')
        return '<span class="badge-high px-2 py-0.5 rounded-sm text-xs font-bold w-full inline-block text-center">상 (High)</span>';
    if (level === '중')
        return '<span class="badge-medium px-2 py-0.5 rounded-sm text-xs font-bold w-full inline-block text-center">중 (Medium)</span>';
    return '<span class="badge-low px-2 py-0.5 rounded-sm text-xs font-bold w-full inline-block text-center">하 (Low)</span>';
}
function getRiskBadge(level) {
    if (level === '상')
        return '<span class="px-2 py-0.5 bg-red-100 text-red-800 border border-red-300 rounded-sm text-xs font-bold">위험도: 상</span>';
    if (level === '중')
        return '<span class="px-2 py-0.5 bg-yellow-100 text-yellow-800 border border-yellow-300 rounded-sm text-xs font-bold">위험도: 중</span>';
    return '<span class="px-2 py-0.5 bg-gray-100 text-gray-800 border border-gray-300 rounded-sm text-xs font-bold">위험도: 하</span>';
}

function setText(id, value) {
    document.getElementById(id).textContent =
        value === undefined || value === null || value === '' ? '-' : value;
}

function renderDashboard(data) {
    const meta = data.projectMeta || {};
    const goals = data.goals || {};
    const execution = data.execution || {};
    const tta = data.ttaPerspective || {};
    const judgment = data.judgment || {};

    setText('header-title', meta.title);

    const rec = meta.recommendation || {};
    const recBadge = document.getElementById('badge-recommendation');
    recBadge.textContent = rec.status || '검토';
    recBadge.className = `px-2 py-0.5 text-xs font-bold rounded-sm border border-gray-800 ${
        rec.class || 'bg-gray-800 text-white'
    }`;

    // D-Day 계산
    try {
        const dDayDate = new Date(meta.dDay);
        if (meta.dDay && !isNaN(dDayDate)) {
            const today = new Date();
            const diffDays = Math.ceil((dDayDate - today) / (1000 * 60 * 60 * 24));
            document.getElementById('header-dday').textContent =
                'D' + (diffDays >= 0 ? '-' + diffDays : '+' + Math.abs(diffDays));
        } else {
            document.getElementById('header-dday').textContent = meta.dDay || '-';
        }
    } catch (e) {
        document.getElementById('header-dday').textContent = '-';
    }

    // Section 1
    setText('v-agency', meta.agency);
    setText('v-noticeNumber', meta.noticeNumber);
    setText('v-duration', meta.duration);
    setText('v-budget', meta.budget);
    setText('v-fundingRatio', meta.fundingRatio);
    setText('v-eligibility', meta.eligibility);
    setText('v-dates', meta.dates);

    // Section 2
    setText('v-finalGoal', goals.finalGoal);
    setText('v-policyBackground', goals.policyBackground);

    document.getElementById('v-annualGoals').innerHTML = (goals.annualGoals || [])
        .map(
            (ag) => `
        <div class="bg-white border border-gray-300 p-4">
            <span class="text-xs font-bold text-gray-800 bg-gray-200 px-2 py-1 rounded-sm mb-2 inline-block border border-gray-300">${escapeHtml(ag.year)}</span>
            <p class="text-sm text-gray-800 mt-1">${escapeHtml(ag.goal)}</p>
        </div>`
        )
        .join('');

    document.getElementById('v-kpis').innerHTML = (goals.kpis || [])
        .map(
            (kpi) => `
        <tr class="hover:bg-gray-50">
            <td class="px-4 py-2 border-r border-gray-200 font-medium text-gray-900">${escapeHtml(kpi.name)}</td>
            <td class="px-4 py-2 border-r border-gray-200 text-gray-900 font-bold">${escapeHtml(kpi.target)}</td>
            <td class="px-4 py-2 border-r border-gray-200">${escapeHtml(kpi.method)}</td>
            <td class="px-4 py-2 border-r border-gray-200 text-gray-600 text-sm">${escapeHtml(kpi.time)}</td>
            <td class="px-4 py-2 text-center text-xs text-gray-500">${escapeHtml(kpi.source)}</td>
        </tr>`
        )
        .join('');

    document.getElementById('v-keywords').innerHTML = (goals.keywords || [])
        .map(
            (kw) =>
                `<span class="bg-white border border-gray-400 text-gray-700 px-2 py-1 text-xs font-medium"># ${escapeHtml(kw)}</span>`
        )
        .join('');

    // Section 3
    document.getElementById('v-wbs').innerHTML = (execution.wbs || [])
        .map((w) => {
            const reqBadge =
                w.type === '필수' || w.type === 'Mandatory'
                    ? '<span class="text-red-700 px-1 py-0.5 text-xs font-bold border border-red-300 bg-red-50">필수</span>'
                    : '<span class="text-gray-600 px-1 py-0.5 text-xs font-bold border border-gray-300 bg-gray-100">선택</span>';
            return `
        <div class="flex items-start gap-4 p-4 bg-white">
            <div class="flex-1">
                <div class="flex items-center gap-2 mb-1"><h4 class="font-bold text-gray-900 text-sm">${escapeHtml(w.task)}</h4>${reqBadge}</div>
                <p class="text-sm text-gray-700">${escapeHtml(w.desc)}</p>
            </div>
            <div class="text-xs text-gray-500 whitespace-nowrap mt-1">${escapeHtml(w.source)}</div>
        </div>`;
        })
        .join('');

    setText('v-deliverables', execution.deliverables);

    const ganttContainer = document.getElementById('v-gantt');
    ganttContainer.innerHTML = `
        <div class="gantt-header border-r border-gray-300">세부 태스크</div>
        <div class="gantt-header border-r border-gray-300">1차년도</div>
        <div class="gantt-header border-r border-gray-300">2차년도</div>
        <div class="gantt-header">3차년도</div>
    `;
    (execution.schedule || []).forEach((item) => {
        const taskDiv = document.createElement('div');
        taskDiv.className = 'gantt-task border-r border-gray-300 text-gray-800 text-xs md:text-sm';
        taskDiv.textContent = item.task || '';
        ganttContainer.appendChild(taskDiv);

        [item.y1, item.y2, item.y3].forEach((pct, index) => {
            const barContainer = document.createElement('div');
            barContainer.className = `gantt-cell gantt-bar-container ${
                index < 2 ? 'border-r border-gray-300' : ''
            }`;
            const value = Number(pct) || 0;
            if (value > 0) {
                const bar = document.createElement('div');
                bar.className = 'gantt-bar';
                bar.style.width = `${Math.min(value, 100)}%`;
                if (value < 100) bar.style.opacity = '0.5';
                barContainer.appendChild(bar);
            }
            ganttContainer.appendChild(barContainer);
        });
    });

    // Section 4
    setText('v-role', tta.role);
    setText('v-roleReason', tta.roleReason);
    setText('v-tasksAndBudget', tta.tasksAndBudget);
    setText('v-gaps', tta.gaps);

    document.getElementById('v-mapping').innerHTML = (tta.mapping || [])
        .map(
            (m) => `
        <tr class="hover:bg-gray-50">
            <td class="px-4 py-3 border-r border-gray-200 text-sm text-gray-900 font-medium">${escapeHtml(m.req)}</td>
            <td class="px-4 py-3 border-r border-gray-200 text-sm text-gray-700">${escapeHtml(m.tta)}</td>
            <td class="px-4 py-3 border-r border-gray-200 align-middle">${getMatchBadge(m.match)}</td>
            <td class="px-4 py-3 text-xs text-gray-600">${escapeHtml(m.reason)}</td>
        </tr>`
        )
        .join('');

    document.getElementById('v-risks').innerHTML = (tta.risks || [])
        .map(
            (r) => `
        <div class="flex items-start gap-4 p-4 bg-white">
            <div class="mt-0.5 w-24 shrink-0">${getRiskBadge(r.level)}</div>
            <div>
                <h4 class="font-bold text-sm text-gray-900 mb-1">${escapeHtml(r.type)}</h4>
                <p class="text-sm text-gray-700">${escapeHtml(r.desc)}</p>
            </div>
        </div>`
        )
        .join('');

    // Section 5
    setText(
        'v-totalScore',
        judgment.totalScore === undefined ? '-' : `${judgment.totalScore} 점`
    );
    setText('v-recommendationDesc', judgment.recommendationDesc);

    document.getElementById('v-points').innerHTML = (judgment.points || [])
        .map((p) => `<li>${escapeHtml(p)}</li>`)
        .join('');

    document.getElementById('v-todo').innerHTML = (judgment.todo || [])
        .map(
            (t) => `
        <li class="flex items-center gap-3 text-sm bg-white p-3">
            <input type="checkbox" class="w-4 h-4 text-gray-800 border-gray-400 focus:ring-gray-800 rounded-sm">
            <span class="text-gray-800">${escapeHtml(t)}</span>
        </li>`
        )
        .join('');

    renderChart(judgment.scores || {});
}

function renderChart(scores) {
    const ctx = document.getElementById('radarChart').getContext('2d');
    if (radarChartInstance) radarChartInstance.destroy();

    radarChartInstance = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: ['역량 적합도', '전략적 부합성', '자원 가용성', '경쟁력', '리스크 관리'],
            datasets: [
                {
                    label: '평가 점수',
                    data: [
                        scores.competency || 0,
                        scores.strategy || 0,
                        scores.resources || 0,
                        scores.competitiveness || 0,
                        scores.riskMgt || 0,
                    ],
                    backgroundColor: 'rgba(31, 41, 55, 0.1)',
                    borderColor: 'rgba(31, 41, 55, 1)',
                    pointBackgroundColor: 'rgba(31, 41, 55, 1)',
                    pointBorderColor: '#fff',
                    borderWidth: 2,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            scales: {
                r: {
                    min: 0,
                    max: 100,
                    angleLines: { color: 'rgba(0, 0, 0, 0.2)' },
                    grid: { color: 'rgba(0, 0, 0, 0.2)' },
                    pointLabels: {
                        font: {
                            family: "'Inter', 'Noto Sans KR', sans-serif",
                            size: 11,
                            weight: 'bold',
                        },
                        color: '#111827',
                    },
                    ticks: { stepSize: 20, display: false },
                },
            },
            plugins: { legend: { display: false } },
        },
    });
}
