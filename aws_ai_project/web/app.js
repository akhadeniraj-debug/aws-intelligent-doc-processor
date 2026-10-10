// AWS Intelligent Document Processor - Frontend Logic

let currentDocRecord = null;
let documentsList = [];

// Elements
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');
const systemStatusBadge = document.getElementById('systemStatusBadge');
const statusModeText = document.getElementById('statusModeText');

const statTotalDocs = document.getElementById('statTotalDocs');
const statAvgLatency = document.getElementById('statAvgLatency');
const statTotalEntities = document.getElementById('statTotalEntities');

const resCategory = document.getElementById('resCategory');
const resFilename = document.getElementById('resFilename');
const resDocId = document.getElementById('resDocId');
const resLatency = document.getElementById('resLatency');
const resWords = document.getElementById('resWords');

const kvTableBody = document.getElementById('kvTableBody');
const entitiesGrid = document.getElementById('entitiesGrid');
const phrasesCloud = document.getElementById('phrasesCloud');
const rawOcrText = document.getElementById('rawOcrText');
const rawJsonRecord = document.getElementById('rawJsonRecord');

const historyTableBody = document.getElementById('historyTableBody');
const searchDocsInput = document.getElementById('searchDocsInput');
const clearHistoryBtn = document.getElementById('clearHistoryBtn');
const copyJsonBtn = document.getElementById('copyJsonBtn');

// Pipeline Steppers
const stepS3 = document.getElementById('step-s3');
const stepLambda = document.getElementById('step-lambda');
const stepTextract = document.getElementById('step-textract');
const stepComprehend = document.getElementById('step-comprehend');
const stepDynamo = document.getElementById('step-dynamo');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  checkBackendHealth();
  loadDocuments();
  setupTabs();
  setupUpload();
  setupSamples();
  setupControls();
});

// Check API & AWS Connection
async function checkBackendHealth() {
  try {
    const res = await fetch('/api/health');
    const data = await res.json();
    if (data.aws_connected) {
      systemStatusBadge.className = 'mode-badge live';
      statusModeText.textContent = `AWS Live Mode (${data.region})`;
    } else {
      systemStatusBadge.className = 'mode-badge sandbox';
      statusModeText.textContent = 'Sandbox Simulator Mode';
    }
  } catch (err) {
    systemStatusBadge.className = 'mode-badge sandbox';
    statusModeText.textContent = 'Offline / Local Dev';
  }
}

// Tabs setup
function setupTabs() {
  const tabBtns = document.querySelectorAll('.tab-btn');
  tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      tabBtns.forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
      
      btn.classList.add('active');
      const targetPane = document.getElementById(btn.dataset.tab);
      if (targetPane) targetPane.classList.add('active');
    });
  });
}

// Upload & Drag-and-Drop
function setupUpload() {
  dropZone.addEventListener('click', () => fileInput.click());

  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
  });

  ['dragleave', 'dragend'].forEach(type => {
    dropZone.addEventListener(type, () => dropZone.classList.remove('dragover'));
  });

  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) {
      uploadFile(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      uploadFile(e.target.files[0]);
    }
  });
}

// Instant Demo Samples
function setupSamples() {
  document.querySelectorAll('.sample-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const sampleType = btn.dataset.sample;
      triggerStepperAnimation(async () => {
        const formData = new FormData();
        formData.append('sample_type', sampleType);
        const res = await fetch('/api/load-sample', {
          method: 'POST',
          body: formData
        });
        if (!res.ok) throw new Error('Failed to load sample');
        const data = await res.json();
        renderAnalysis(data);
        loadDocuments();
      }).catch(err => {
        alert('Error: ' + err.message);
        resetStepper();
      });
    });
  });
}

// General Controls
function setupControls() {
  searchDocsInput.addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase();
    const filtered = documentsList.filter(d => 
      (d.filename && d.filename.toLowerCase().includes(q)) ||
      (d.document_id && d.document_id.toLowerCase().includes(q)) ||
      (d.category && d.category.toLowerCase().includes(q))
    );
    renderHistoryTable(filtered);
  });

  clearHistoryBtn.addEventListener('click', async () => {
    if (confirm('Clear all document history?')) {
      await fetch('/api/documents', { method: 'DELETE' });
      currentDocRecord = null;
      loadDocuments();
      resetAnalysisView();
    }
  });

  copyJsonBtn.addEventListener('click', () => {
    if (!currentDocRecord) return;
    navigator.clipboard.writeText(JSON.stringify(currentDocRecord, null, 2));
    copyJsonBtn.innerHTML = `
      <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>
      Copied!
    `;
    setTimeout(() => {
      copyJsonBtn.innerHTML = `
        <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
        Copy JSON
      `;
    }, 2000);
  });
}

// Upload file to Backend Pipeline
async function uploadFile(file) {
  const formData = new FormData();
  formData.append('file', file);

  triggerStepperAnimation(async () => {
    const res = await fetch('/api/upload', {
      method: 'POST',
      body: formData
    });
    if (!res.ok) throw new Error('Upload and processing failed');
    const data = await res.json();
    renderAnalysis(data);
    loadDocuments();
  }).catch(err => {
    alert('Error during document processing: ' + err.message);
    resetStepper();
  });
}

// Pipeline Stepper Progress Animation
async function triggerStepperAnimation(workFn) {
  const steps = [
    { el: stepS3, statusText: 'Uploading' },
    { el: stepLambda, statusText: 'Triggered' },
    { el: stepTextract, statusText: 'Extracting OCR' },
    { el: stepComprehend, statusText: 'Analyzing NER' },
    { el: stepDynamo, statusText: 'Committing DB' }
  ];

  // Reset steps
  steps.forEach(s => {
    s.el.className = 'stepper-step';
    s.el.querySelector('.step-status').textContent = 'Waiting';
  });

  const runStep = (idx) => {
    if (idx > 0) {
      steps[idx - 1].el.className = 'stepper-step completed';
      steps[idx - 1].el.querySelector('.step-status').textContent = 'Done';
    }
    if (idx < steps.length) {
      steps[idx].el.className = 'stepper-step active';
      steps[idx].el.querySelector('.step-status').textContent = steps[idx].statusText;
    }
  };

  runStep(0);
  await new Promise(r => setTimeout(r, 220));
  runStep(1);
  await new Promise(r => setTimeout(r, 220));
  runStep(2);

  // Execute the real API call
  await workFn();

  runStep(3);
  await new Promise(r => setTimeout(r, 200));
  runStep(4);
  await new Promise(r => setTimeout(r, 180));

  steps.forEach(s => {
    s.el.className = 'stepper-step completed';
    s.el.querySelector('.step-status').textContent = 'Completed';
  });
}

function resetStepper() {
  [stepS3, stepLambda, stepTextract, stepComprehend, stepDynamo].forEach(el => {
    el.className = 'stepper-step';
    el.querySelector('.step-status').textContent = 'Idle';
  });
}

// Render Deep Extraction Details
function renderAnalysis(doc) {
  currentDocRecord = doc;

  resCategory.textContent = doc.category || 'Processed Document';
  resFilename.textContent = doc.filename || 'Untitled';
  resDocId.textContent = `ID: ${doc.document_id}`;
  resLatency.textContent = `Time: ${doc.processing_time_ms || 280} ms`;
  resWords.textContent = `Words: ${doc.word_count || 0}`;

  // 1. Key-Value Form Fields
  const fields = doc.form_fields || {};
  const fieldKeys = Object.keys(fields);
  if (fieldKeys.length === 0) {
    kvTableBody.innerHTML = `<tr><td colspan="3" class="empty-state">No structured form key-values detected. See OCR tab for full text.</td></tr>`;
  } else {
    kvTableBody.innerHTML = fieldKeys.map(k => `
      <tr>
        <td><strong>${escapeHtml(k)}</strong></td>
        <td><span class="field-value">${escapeHtml(fields[k])}</span></td>
        <td><span class="service-tag textract"><span class="dot"></span>Textract Forms</span></td>
      </tr>
    `).join('');
  }

  // 2. Comprehend Entities (NER)
  const entities = doc.entities || [];
  if (entities.length === 0) {
    entitiesGrid.innerHTML = `<div class="empty-state">No entities recognized.</div>`;
  } else {
    entitiesGrid.innerHTML = entities.map(ent => {
      const type = ent.Type || 'OTHER';
      const scorePct = Math.round((ent.Score || 0.95) * 100);
      return `
        <div class="entity-card ${type}">
          <div class="entity-header">
            <span>${escapeHtml(type)}</span>
            <span>${scorePct}% match</span>
          </div>
          <div class="entity-text">${escapeHtml(ent.Text)}</div>
          <div class="entity-score">
            <div class="score-bar">
              <div class="score-fill" style="width: ${scorePct}%;"></div>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  // 3. Key Phrases
  const phrases = doc.key_phrases || [];
  if (phrases.length === 0) {
    phrasesCloud.innerHTML = `<div class="empty-state">No key phrases found.</div>`;
  } else {
    phrasesCloud.innerHTML = phrases.map(p => `
      <div class="phrase-pill">
        <span>${escapeHtml(p.Text)}</span>
        <span class="phrase-score">${Math.round((p.Score || 0.9) * 100)}%</span>
      </div>
    `).join('');
  }

  // 4. Raw OCR Text
  rawOcrText.textContent = doc.extracted_text || '(No OCR text)';

  // 5. DynamoDB Record JSON
  rawJsonRecord.textContent = JSON.stringify(doc, null, 2);
}

function resetAnalysisView() {
  resCategory.textContent = 'Select or Upload a Document';
  resFilename.textContent = 'No Document Loaded';
  resDocId.textContent = 'ID: --';
  resLatency.textContent = 'Time: -- ms';
  resWords.textContent = 'Words: 0';
  kvTableBody.innerHTML = `<tr><td colspan="3" class="empty-state">Upload an invoice, resume, or ID form to view extracted key-value pairs.</td></tr>`;
  entitiesGrid.innerHTML = `<div class="empty-state">No entities to display yet.</div>`;
  phrasesCloud.innerHTML = `<div class="empty-state">AWS Comprehend key phrases will appear here.</div>`;
  rawOcrText.textContent = 'Raw OCR text extracted from Textract will appear here.';
  rawJsonRecord.textContent = '{ "message": "No document selected." }';
}

// Load Document History
async function loadDocuments() {
  try {
    const res = await fetch('/api/documents');
    const data = await res.json();
    documentsList = data.documents || [];

    // Calculate metrics
    statTotalDocs.textContent = documentsList.length;
    let totalLatency = 0;
    let totalEntitiesCount = 0;

    documentsList.forEach(d => {
      totalLatency += (d.processing_time_ms || 280);
      totalEntitiesCount += (d.entities ? d.entities.length : 0);
    });

    const avg = documentsList.length ? Math.round(totalLatency / documentsList.length) : 0;
    statAvgLatency.textContent = `${avg} ms`;
    statTotalEntities.textContent = totalEntitiesCount;

    renderHistoryTable(documentsList);

    // If no document is selected yet but we have docs, select the first one
    if (!currentDocRecord && documentsList.length > 0) {
      renderAnalysis(documentsList[0]);
    }
  } catch (err) {
    console.warn('Could not load documents:', err);
  }
}

function renderHistoryTable(list) {
  if (list.length === 0) {
    historyTableBody.innerHTML = `<tr><td colspan="8" class="empty-state">No documents processed yet. Click one of the instant samples above to begin!</td></tr>`;
    return;
  }

  historyTableBody.innerHTML = list.map(d => {
    const timeStr = d.processed_at ? new Date(d.processed_at).toLocaleTimeString() : 'Recent';
    const entCount = (d.entities || []).length;
    return `
      <tr>
        <td><code>${escapeHtml(d.document_id.slice(0, 16))}</code></td>
        <td><strong>${escapeHtml(d.filename)}</strong></td>
        <td><span class="category-badge">${escapeHtml(d.category || 'General')}</span></td>
        <td>${entCount} entities</td>
        <td>${d.processing_time_ms || 250} ms</td>
        <td><span class="badge-status ${d.status}">${d.status}</span></td>
        <td>${timeStr}</td>
        <td><button class="action-view-btn" onclick="selectDocument('${d.document_id}')">View</button></td>
      </tr>
    `;
  }).join('');
}

window.selectDocument = function(docId) {
  const doc = documentsList.find(d => d.document_id === docId);
  if (doc) {
    renderAnalysis(doc);
    window.scrollTo({ top: 120, behavior: 'smooth' });
  }
};

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
