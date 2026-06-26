/**
 * NL2SQL — Frontend Application Logic
 *
 * Handles: database selection, query submission, result rendering,
 * feedback submission, database management, and query history.
 */

// ══════════════════════════════════════════════════════════════════
// State
// ══════════════════════════════════════════════════════════════════

const state = {
    selectedDb: null,
    databases: [],
    queryHistory: [],
    lastResult: null,
    isLoading: false,
};

// ══════════════════════════════════════════════════════════════════
// DOM References
// ══════════════════════════════════════════════════════════════════

const $  = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const dom = {
    statusBadge:       $('#statusBadge'),
    dbList:            $('#dbList'),
    historyList:       $('#historyList'),
    selectedDbName:    $('#selectedDbName'),
    selectedDbBadge:   $('#selectedDbBadge'),
    queryInput:        $('#queryInput'),
    btnQuery:          $('#btnQuery'),
    resultsSection:    $('#resultsSection'),
    loadingState:      $('#loadingState'),
    sqlOutput:         $('#sqlOutput'),
    sqlCode:           $('#sqlCode'),
    nlOutput:          $('#nlOutput'),
    nlContent:         $('#nlContent'),
    intentBadge:       $('#intentBadge'),
    timeBadge:         $('#timeBadge'),
    retryBadge:        $('#retryBadge'),
    errorOutput:       $('#errorOutput'),
    errorMessage:      $('#errorMessage'),
    dataOutput:        $('#dataOutput'),
    dataTableHead:     $('#dataTableHead'),
    dataTableBody:     $('#dataTableBody'),
    rowCount:          $('#rowCount'),
    feedbackSection:   $('#feedbackSection'),
    btnCopySQL:        $('#btnCopySQL'),
    btnCorrect:        $('#btnCorrect'),
    btnIncorrect:      $('#btnIncorrect'),
    correctionInput:   $('#correctionInput'),
    correctSqlInput:   $('#correctSqlInput'),
    btnSubmitCorrection: $('#btnSubmitCorrection'),
    dbModal:           $('#dbModal'),
    btnManageDB:       $('#btnManageDB'),
    btnCloseModal:     $('#btnCloseModal'),
    addDbForm:         $('#addDbForm'),
    registeredDbList:  $('#registeredDbList'),
    toastContainer:    $('#toastContainer'),
};

// ══════════════════════════════════════════════════════════════════
// API Layer
// ══════════════════════════════════════════════════════════════════

const api = {
    async get(url) {
        const res = await fetch(url);
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || res.statusText);
        }
        return res.json();
    },

    async post(url, data) {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || res.statusText);
        }
        return res.json();
    },

    async del(url) {
        const res = await fetch(url, { method: 'DELETE' });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: res.statusText }));
            throw new Error(err.detail || res.statusText);
        }
        return res.json();
    },

    getDatabases: ()      => api.get('/api/databases'),
    getHealth:    ()      => api.get('/api/health'),
    query:        (data)  => api.post('/api/query', data),
    addDatabase:  (data)  => api.post('/api/databases', data),
    removeDatabase: (id)  => api.del(`/api/databases/${id}`),
    reindexDatabase: (id) => api.post(`/api/databases/${id}/reindex`),
    submitFeedback: (data) => api.post('/api/feedback', data),
};

// ══════════════════════════════════════════════════════════════════
// Toast Notifications
// ══════════════════════════════════════════════════════════════════

function showToast(message, type = 'info', duration = 4000) {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    dom.toastContainer.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('removing');
        setTimeout(() => toast.remove(), 200);
    }, duration);
}

// ══════════════════════════════════════════════════════════════════
// Database List
// ══════════════════════════════════════════════════════════════════

async function loadDatabases() {
    try {
        state.databases = await api.getDatabases();
        renderDbList();
        updateStatus(true);

        // Auto-select first database if none selected
        if (!state.selectedDb && state.databases.length > 0) {
            selectDatabase(state.databases[0]);
        }
    } catch (e) {
        updateStatus(false);
        dom.dbList.innerHTML = `<div class="history-empty">Failed to load databases</div>`;
    }
}

function renderDbList() {
    if (state.databases.length === 0) {
        dom.dbList.innerHTML = `<div class="history-empty">No databases registered</div>`;
        return;
    }

    dom.dbList.innerHTML = state.databases.map(db => `
        <div class="db-item ${state.selectedDb?.db_id === db.db_id ? 'active' : ''}"
             data-db-id="${db.db_id}" onclick="selectDatabaseById('${db.db_id}')">
            <div class="db-item-icon">🗄️</div>
            <div class="db-item-info">
                <div class="db-item-name">${escapeHtml(db.name)}</div>
                <div class="db-item-meta">${db.table_count} tables</div>
            </div>
            <div class="db-item-status ${db.is_connected ? 'online' : 'offline'}"></div>
        </div>
    `).join('');
}

function selectDatabaseById(dbId) {
    const db = state.databases.find(d => d.db_id === dbId);
    if (db) selectDatabase(db);
}

function selectDatabase(db) {
    state.selectedDb = db;
    dom.selectedDbName.textContent = db.name;
    dom.btnQuery.disabled = false;
    renderDbList();
}

function updateStatus(connected) {
    if (connected) {
        dom.statusBadge.classList.add('connected');
        dom.statusBadge.querySelector('span:last-child').textContent = 'Connected';
    } else {
        dom.statusBadge.classList.remove('connected');
        dom.statusBadge.querySelector('span:last-child').textContent = 'Disconnected';
    }
}

// ══════════════════════════════════════════════════════════════════
// Query Execution
// ══════════════════════════════════════════════════════════════════

async function executeQuery() {
    const question = dom.queryInput.value.trim();
    if (!question || !state.selectedDb || state.isLoading) return;

    state.isLoading = true;
    dom.btnQuery.disabled = true;

    // Show loading state
    showSection('loading');
    animateLoadingSteps();

    try {
        const result = await api.query({
            question,
            database_id: state.selectedDb.db_id,
        });

        state.lastResult = result;
        renderResult(result);

        // Add to history
        addToHistory(question, result);

    } catch (e) {
        showError(`Request failed: ${e.message}`);
    } finally {
        state.isLoading = false;
        dom.btnQuery.disabled = false;
    }
}

function renderResult(result) {
    // Hide loading
    dom.loadingState.style.display = 'none';

    if (result.success) {
        // Show NL summary
        if (result.natural_language_response) {
            dom.nlOutput.style.display = 'block';
            let safeHtml = escapeHtml(result.natural_language_response);
            // Support simple markdown bolding (**text**) with random colors
            safeHtml = safeHtml.replace(/\*\*(.*?)\*\*/g, (match, p1) => {
                const colors = ['#ff5252', '#ff4081', '#e040fb', '#7c4dff', '#536dfe', '#448aff', '#40c4ff', '#18ffff', '#64ffda', '#69f0ae', '#b2ff59'];
                const color = colors[Math.floor(Math.random() * colors.length)];
                return `<strong style="color: ${color}; text-shadow: 0 0 8px ${color}40;">${p1}</strong>`;
            });
            dom.nlContent.innerHTML = safeHtml;
        }

        // Show SQL
        showSqlOutput(result);

        // Show data table
        if (result.results && result.results.rows) {
            showDataTable(result.results);
        }

        // Show feedback section
        dom.feedbackSection.style.display = 'block';
        dom.correctionInput.style.display = 'none';
    } else {
        // Show error
        showError(result.error || 'Unknown error occurred.');

        // Show SQL if it was generated (even if it failed)
        if (result.generated_sql) {
            showSqlOutput(result);
        }
    }
}

function showSqlOutput(result) {
    dom.sqlOutput.style.display = 'block';
    dom.sqlCode.innerHTML = highlightSQL(result.generated_sql || '');

    // Meta badges
    if (result.intent) {
        dom.intentBadge.textContent = result.intent.replace('_', ' ');
        dom.intentBadge.style.display = 'inline';
    }

    if (result.execution_time_ms) {
        dom.timeBadge.textContent = `${Math.round(result.execution_time_ms)}ms`;
    }

    if (result.correction_attempts > 0) {
        dom.retryBadge.textContent = `${result.correction_attempts} retries`;
        dom.retryBadge.style.display = 'inline';
    } else {
        dom.retryBadge.style.display = 'none';
    }
}

function showDataTable(data) {
    dom.dataOutput.style.display = 'block';

    const truncatedLabel = data.truncated ? ' (truncated)' : '';
    dom.rowCount.textContent = `${data.row_count} rows${truncatedLabel}`;

    // Header
    dom.dataTableHead.innerHTML = `<tr>${
        data.columns.map(col => `<th>${escapeHtml(col)}</th>`).join('')
    }</tr>`;

    // Body
    dom.dataTableBody.innerHTML = data.rows.map(row => `<tr>${
        data.columns.map(col => {
            const val = row[col];
            const display = val === null ? '<span style="color: var(--text-muted)">NULL</span>' : escapeHtml(String(val));
            return `<td>${display}</td>`;
        }).join('')
    }</tr>`).join('');
}

function showError(message) {
    dom.errorOutput.style.display = 'flex';
    dom.errorMessage.textContent = message;
}

function showSection(which) {
    dom.resultsSection.style.display = 'block';
    dom.loadingState.style.display = which === 'loading' ? 'block' : 'none';
    dom.nlOutput.style.display = 'none';
    dom.sqlOutput.style.display = 'none';
    dom.errorOutput.style.display = 'none';
    dom.dataOutput.style.display = 'none';
    dom.feedbackSection.style.display = 'none';
}

// ══════════════════════════════════════════════════════════════════
// Loading Animation
// ══════════════════════════════════════════════════════════════════

function animateLoadingSteps() {
    const steps = ['stepRouter', 'stepRetrieval', 'stepGenerate', 'stepValidate', 'stepExecute'];
    let current = 0;

    // Reset all steps
    steps.forEach(id => {
        const el = $(`#${id}`);
        el.classList.remove('active', 'done');
    });

    $(`#${steps[0]}`).classList.add('active');

    const interval = setInterval(() => {
        if (!state.isLoading || current >= steps.length - 1) {
            clearInterval(interval);
            return;
        }

        $(`#${steps[current]}`).classList.remove('active');
        $(`#${steps[current]}`).classList.add('done');
        current++;
        $(`#${steps[current]}`).classList.add('active');
    }, 500);
}

// ══════════════════════════════════════════════════════════════════
// SQL Syntax Highlighting (lightweight, no external deps)
// ══════════════════════════════════════════════════════════════════

function highlightSQL(sql) {
    if (!sql) return '';

    let escaped = escapeHtml(sql);

    // Keywords
    const keywords = [
        'SELECT', 'FROM', 'WHERE', 'JOIN', 'INNER JOIN', 'LEFT JOIN', 'RIGHT JOIN',
        'OUTER JOIN', 'CROSS JOIN', 'ON', 'AND', 'OR', 'NOT', 'IN', 'EXISTS',
        'BETWEEN', 'LIKE', 'IS', 'NULL', 'AS', 'ORDER BY', 'GROUP BY', 'HAVING',
        'LIMIT', 'OFFSET', 'UNION', 'ALL', 'DISTINCT', 'CASE', 'WHEN', 'THEN',
        'ELSE', 'END', 'ASC', 'DESC', 'WITH', 'OVER', 'PARTITION BY',
        'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER', 'TABLE',
        'INTO', 'VALUES', 'SET', 'COUNT', 'SUM', 'AVG', 'MIN', 'MAX',
    ];

    // Sort by length (longest first) to avoid partial matches
    keywords.sort((a, b) => b.length - a.length);

    // Replace keywords
    keywords.forEach(kw => {
        const regex = new RegExp(`\\b(${kw})\\b`, 'gi');
        escaped = escaped.replace(regex, '<span class="sql-keyword">$1</span>');
    });

    // Strings (single quotes)
    escaped = escaped.replace(/'([^']*?)'/g, "'<span class=\"sql-string\">$1</span>'");

    // Numbers
    escaped = escaped.replace(/\b(\d+\.?\d*)\b/g, '<span class="sql-number">$1</span>');

    return escaped;
}

// ══════════════════════════════════════════════════════════════════
// Query History
// ══════════════════════════════════════════════════════════════════

function addToHistory(question, result) {
    state.queryHistory.unshift({
        question,
        success: result.success,
        timestamp: new Date(),
        sql: result.generated_sql,
        time_ms: result.execution_time_ms,
    });

    // Keep last 20
    if (state.queryHistory.length > 20) state.queryHistory.pop();

    renderHistory();
}

function renderHistory() {
    if (state.queryHistory.length === 0) {
        dom.historyList.innerHTML = `<div class="history-empty">No queries yet. Try asking a question!</div>`;
        return;
    }

    dom.historyList.innerHTML = state.queryHistory.map((h, i) => `
        <div class="history-item" onclick="replayHistory(${i})">
            <div class="history-item-query">${h.success ? '✅' : '❌'} ${escapeHtml(h.question)}</div>
            <div class="history-item-meta">
                ${h.time_ms ? Math.round(h.time_ms) + 'ms' : ''} •
                ${formatTimeAgo(h.timestamp)}
            </div>
        </div>
    `).join('');
}

function replayHistory(index) {
    const h = state.queryHistory[index];
    if (h) {
        dom.queryInput.value = h.question;
    }
}

// ══════════════════════════════════════════════════════════════════
// Feedback System
// ══════════════════════════════════════════════════════════════════

function handleFeedbackCorrect() {
    showToast('Thanks! Glad the result was correct.', 'success');
    dom.feedbackSection.style.display = 'none';
}

function handleFeedbackIncorrect() {
    dom.correctionInput.style.display = 'flex';
    if (state.lastResult?.generated_sql) {
        dom.correctSqlInput.value = state.lastResult.generated_sql;
    }
}

async function submitCorrection() {
    const correctSql = dom.correctSqlInput.value.trim();
    if (!correctSql || !state.lastResult || !state.selectedDb) return;

    try {
        await api.submitFeedback({
            question: dom.queryInput.value.trim(),
            correct_sql: correctSql,
            database_id: state.selectedDb.db_id,
        });
        showToast('Correction submitted! The system will learn from this.', 'success');
        dom.feedbackSection.style.display = 'none';
    } catch (e) {
        showToast(`Failed to submit: ${e.message}`, 'error');
    }
}

// ══════════════════════════════════════════════════════════════════
// Database Management Modal
// ══════════════════════════════════════════════════════════════════

function openDbModal() {
    dom.dbModal.style.display = 'flex';
    renderRegisteredDatabases();
}

function closeDbModal() {
    dom.dbModal.style.display = 'none';
}

function renderRegisteredDatabases() {
    if (state.databases.length === 0) {
        dom.registeredDbList.innerHTML = `<div class="history-empty">No databases registered</div>`;
        return;
    }

    dom.registeredDbList.innerHTML = state.databases.map(db => `
        <div class="registered-db-item">
            <div class="registered-db-info">
                <strong>${escapeHtml(db.name)}</strong>
                <span>${db.table_count} tables • ${db.is_connected ? '🟢 Connected' : '🔴 Offline'}</span>
            </div>
            <div class="registered-db-actions">
                <button class="btn btn-ghost btn-sm" onclick="reindexDb('${db.db_id}')" title="Re-index schema">
                    🔄 Reindex
                </button>
                ${db.db_id !== 'demo_ecommerce' ? `
                    <button class="btn btn-danger btn-sm" onclick="removeDb('${db.db_id}')" title="Remove database">
                        ✕
                    </button>
                ` : ''}
            </div>
        </div>
    `).join('');
}

async function handleAddDb(e) {
    e.preventDefault();

    const data = {
        db_id: $('#newDbId').value.trim(),
        connection_string: $('#newDbConn').value.trim(),
        name: $('#newDbName').value.trim() || $('#newDbId').value.trim(),
        description: $('#newDbDesc').value.trim(),
    };

    try {
        await api.addDatabase(data);
        showToast(`Database '${data.name}' added successfully!`, 'success');
        dom.addDbForm.reset();
        await loadDatabases();
        renderRegisteredDatabases();
    } catch (e) {
        showToast(`Failed: ${e.message}`, 'error');
    }
}

async function removeDb(dbId) {
    if (!confirm(`Remove database '${dbId}'?`)) return;
    try {
        await api.removeDatabase(dbId);
        showToast('Database removed.', 'info');
        await loadDatabases();
        renderRegisteredDatabases();
    } catch (e) {
        showToast(`Failed: ${e.message}`, 'error');
    }
}

async function reindexDb(dbId) {
    try {
        showToast('Re-indexing schema...', 'info');
        await api.reindexDatabase(dbId);
        showToast('Schema re-indexed successfully!', 'success');
        await loadDatabases();
        renderRegisteredDatabases();
    } catch (e) {
        showToast(`Failed: ${e.message}`, 'error');
    }
}

// ══════════════════════════════════════════════════════════════════
// Utilities
// ══════════════════════════════════════════════════════════════════

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function formatTimeAgo(date) {
    const seconds = Math.floor((new Date() - date) / 1000);
    if (seconds < 60) return 'just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
}

// ══════════════════════════════════════════════════════════════════
// Event Listeners
// ══════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    // Load databases on startup
    loadDatabases();

    // Query button
    dom.btnQuery.addEventListener('click', executeQuery);

    // Enter key in textarea (Ctrl+Enter or Cmd+Enter)
    dom.queryInput.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            executeQuery();
        }
    });

    // Suggestion chips
    $$('.suggestion-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            dom.queryInput.value = chip.dataset.query;
            dom.queryInput.focus();
        });
    });

    // Copy SQL
    dom.btnCopySQL.addEventListener('click', () => {
        if (state.lastResult?.generated_sql) {
            navigator.clipboard.writeText(state.lastResult.generated_sql)
                .then(() => showToast('SQL copied to clipboard!', 'success', 2000))
                .catch(() => showToast('Failed to copy', 'error'));
        }
    });

    // Feedback
    dom.btnCorrect.addEventListener('click', handleFeedbackCorrect);
    dom.btnIncorrect.addEventListener('click', handleFeedbackIncorrect);
    dom.btnSubmitCorrection.addEventListener('click', submitCorrection);

    // Database modal
    dom.btnManageDB.addEventListener('click', openDbModal);
    dom.btnCloseModal.addEventListener('click', closeDbModal);
    dom.dbModal.addEventListener('click', (e) => {
        if (e.target === dom.dbModal) closeDbModal();
    });

    // Add database form
    dom.addDbForm.addEventListener('submit', handleAddDb);

    // Keyboard shortcut: Escape closes modal
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && dom.dbModal.style.display !== 'none') {
            closeDbModal();
        }
    });
});
