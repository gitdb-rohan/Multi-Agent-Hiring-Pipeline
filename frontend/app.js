
    
    const originalFetch = window.fetch;
    window.fetch = async function() {
        let [resource, config] = arguments;
        if(config === undefined) {
            config = {};
        }
        if(config.headers === undefined) {
            config.headers = {};
        }
        
        const hrToken = localStorage.getItem('hr_token');
        if(hrToken) {
            config.headers['Authorization'] = 'Bearer ' + hrToken;
        }
        
        const res = await originalFetch(resource, config);
        
        // Globally catch 401 Unauthorized errors (except on the login endpoint itself)
        if (res.status === 401 && typeof resource === 'string' && !resource.includes('/auth/login')) {
            const modal = document.getElementById('session-modal');
            if (modal) {
                modal.classList.remove('hidden');
            }
        }
        
        return res;
    };
    
    const modalLogoutBtn = document.getElementById('modal-logout-btn');
    if (modalLogoutBtn) {
        modalLogoutBtn.addEventListener('click', () => {
            localStorage.removeItem('hr_token');
            localStorage.removeItem('hr_email');
            window.location.href = '/login.html';
        });
    }

    // Proactively listen for token expiry without waiting for a network request
    setInterval(() => {
        const token = localStorage.getItem('hr_token');
        if (token && window.location.pathname !== '/login.html') {
            try {
                const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
                if (payload.exp && Date.now() >= payload.exp * 1000) {
                    const modal = document.getElementById('session-modal');
                    if (modal) modal.classList.remove('hidden');
                }
            } catch (e) {
                // Ignore parsing errors
            }
        }
    }, 10000); // Check every 10 seconds


document.addEventListener('DOMContentLoaded', () => {

    
    
    // Theme Toggle Logic
    const themeToggle = document.getElementById('theme-toggle');
    if(themeToggle) {
        const updateThemeIcon = (theme) => {
            const icon = themeToggle.querySelector('svg');
            if(theme === 'dark') {
                icon.innerHTML = '<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>';
            } else {
                icon.innerHTML = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>';
            }
        };

        const savedTheme = localStorage.getItem('theme') || 'light';
        document.documentElement.setAttribute('data-theme', savedTheme);
        updateThemeIcon(savedTheme);
        
        themeToggle.addEventListener('click', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
            updateThemeIcon(newTheme);
        });
    }

    // Auth & Login
    const loginScreen = document.getElementById('login-screen');
    const loginForm = document.getElementById('login-form');
    const hrEmailInput = document.getElementById('hr-email-input');
    const hrPasswordInput = document.getElementById('hr-password-input');
    const registerBtn = document.getElementById('register-btn');
    const authStatus = document.getElementById('auth-status');
    const userProfile = document.getElementById('user-profile');
    const loggedInEmail = document.getElementById('logged-in-email');
    const logoutBtn = document.getElementById('logout-btn');

    function checkAuth() {
        const token = localStorage.getItem('hr_token');
        const email = localStorage.getItem('hr_email');
        if (token && email) {
            if(loginScreen) loginScreen.style.display = 'none';
            if(userProfile) userProfile.style.display = 'flex';
            if(loggedInEmail) loggedInEmail.textContent = email;
            // Trigger fetches now that we are authenticated
            if(typeof fetchCandidates === 'function') fetchCandidates();
            if(typeof fetchReviewQueue === 'function') fetchReviewQueue();
            if(typeof fetchAuditLog === 'function') fetchAuditLog();
            if(typeof fetchPastRuns === 'function') fetchPastRuns();
        } else {
            if(loginScreen) loginScreen.style.display = 'flex';
            if(userProfile) userProfile.style.display = 'none';
        }
    }

    if(loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = hrEmailInput.value.trim();
            const password = hrPasswordInput.value.trim();
            if (email && password) {
                try {
                    const res = await fetch('/auth/login', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ email, password })
                    });
                    if(res.ok) {
                        const data = await res.json();
                        localStorage.setItem('hr_token', data.token);
                        localStorage.setItem('hr_email', data.email);
                        checkAuth();
                    } else {
                        authStatus.textContent = "Invalid email or password";
                    }
                } catch(err) {
                    authStatus.textContent = "Network error";
                }
            }
        });
    }

    if(registerBtn) {
        registerBtn.addEventListener('click', async () => {
            const email = hrEmailInput.value.trim();
            const password = hrPasswordInput.value.trim();
            if (email && password) {
                try {
                    const res = await fetch('/auth/register', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ email, password })
                    });
                    if(res.ok) {
                        const data = await res.json();
                        localStorage.setItem('hr_token', data.token);
                        localStorage.setItem('hr_email', data.email);
                        checkAuth();
                    } else {
                        const data = await res.json();
                        authStatus.textContent = data.detail || "Registration failed";
                    }
                } catch(err) {
                    authStatus.textContent = "Network error";
                }
            } else {
                authStatus.textContent = "Please enter email and password to register.";
            }
        });
    }

    if(logoutBtn) {
        logoutBtn.addEventListener('click', () => {
            localStorage.removeItem('hr_token');
            localStorage.removeItem('hr_email');
            checkAuth();
        });
    }

    // Check auth on load
    checkAuth();


    // ────────────────────────────────────────
    // Branding
    // ────────────────────────────────────────
    async function loadBranding() {
        try {
            const res = await fetch('/config/branding');
            const brand = await res.json();
            document.getElementById('brand-name').textContent = brand.app_name;
            document.getElementById('page-title').textContent = brand.app_name;
            document.title = brand.app_name;
        } catch {
            document.getElementById('brand-name').textContent = 'HireFlow';
        }
    }
    loadBranding();

    // ────────────────────────────────────────
    // History Sidebar
    // ────────────────────────────────────────
    const historyToggle = document.getElementById('history-toggle');
    const closeHistory = document.getElementById('close-history');
    const historySidebar = document.getElementById('history-sidebar');

    if(historyToggle && historySidebar) {
        historyToggle.addEventListener('click', () => {
            historySidebar.classList.toggle('collapsed');
            if(!historySidebar.classList.contains('collapsed')) {
                fetchPastRuns();
            }
        });
    }

    if(closeHistory && historySidebar) {
        closeHistory.addEventListener('click', () => {
            historySidebar.classList.add('collapsed');
        });
    }

    // ────────────────────────────────────────
    // Navigation
    // ────────────────────────────────────────
    const navPills = document.querySelectorAll('.nav-pill');
    const views = document.querySelectorAll('.view');

    navPills.forEach(pill => {
        if (pill.id === 'history-toggle') return; // Handled separately
        pill.addEventListener('click', () => {
            navPills.forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            const target = pill.dataset.target;
            if(!target) return;
            views.forEach(v => {
                v.classList.remove('active');
                if (v.id === target) v.classList.add('active');
            });
            if (target === 'review') fetchReviewQueue();
            if (target === 'candidates') if(localStorage.getItem('hr_email')) fetchCandidates();
        });
    });

    // ────────────────────────────────────────
    // Pipeline Execution
    // ────────────────────────────────────────
    const form = document.getElementById('pipeline-form');
    const submitBtn = document.getElementById('submit-btn');
    const btnLabel = submitBtn.querySelector('.btn-label');
    const btnSpinner = submitBtn.querySelector('.btn-spinner');
    const timeline = document.getElementById('timeline');
    const timelineEmpty = document.getElementById('timeline-empty');
    const runStatus = document.getElementById('run-status');
    const resultsPanel = document.getElementById('results-panel');
    const resultsContent = document.getElementById('results-content');
    let eventSource = null;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const goalText = document.getElementById('goal-text').value;
        const jdText = document.getElementById('jd-text').value;
        const topK = parseInt(document.getElementById('top-k').value, 10) || 5;
        const strictness = parseFloat(document.getElementById('strictness').value) || 0.8;
        const autoApprove = document.getElementById('auto-approve').checked;

        // Reset
        submitBtn.disabled = true;
        btnLabel.textContent = 'Running…';
        btnSpinner.classList.remove('hidden');
        clearTimeline();
        resultsPanel.classList.add('hidden');
        resultsContent.innerHTML = '';
        setStatus('running', 'Running');

        try {
            const res = await fetch('/pipeline/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    goal_text: goalText, 
                    raw_jd_text: jdText, 
                    top_k: topK,
                    strictness: strictness,
                    auto_approve: autoApprove
                })
            });
            if (!res.ok) throw new Error('Failed to start pipeline');
            const data = await res.json();
            addTimelineItem('Pipeline Started', `Run ID: ${data.run_id}`, 'running');
            connectSSE(data.run_id);
        } catch (err) {
            addTimelineItem('Error', err.message, 'error');
            resetPipelineBtn();
            setStatus('error', 'Failed');
        }
    });

    function connectSSE(runId) {
        if (eventSource) eventSource.close();
        const hrToken = localStorage.getItem('hr_token');
        eventSource = new EventSource(`/pipeline/${runId}/stream?token=${hrToken}`);

        eventSource.addEventListener('state_change', (e) => {
            const d = JSON.parse(e.data);
            addTimelineItem('State', `${d.data.old_state} → ${d.data.new_state}`, 'completed');
            if (d.data.new_state === 'paused_for_review') {
                fetchReviewQueue();
            }
        });

        eventSource.addEventListener('agent_started', (e) => {
            const d = JSON.parse(e.data);
            addTimelineItem(`${d.data.agent}`, `Started — ${d.data.task}`, 'running', `task-${d.data.task}`);
        });

        eventSource.addEventListener('agent_completed', (e) => {
            const d = JSON.parse(e.data);
            const existing = document.getElementById(`task-${d.data.task}`);
            if (existing) existing.remove();
            addTimelineItem(`${d.data.agent}`, `${d.data.summary} (${d.data.duration_s}s)`, 'completed');
        });

        eventSource.addEventListener('eval_flagged', (e) => {
            const d = JSON.parse(e.data);
            addTimelineItem('Eval Flagged', `${d.data.agent}: ${d.data.reason}`, 'flagged');
            const badge = document.getElementById('review-badge');
            badge.textContent = parseInt(badge.textContent || '0') + 1;
            badge.classList.remove('hidden');
            fetchReviewQueue();
        });

        eventSource.addEventListener('run_completed', (e) => {
            const d = JSON.parse(e.data);
            const status = d.data.status;
            addTimelineItem('Done', `Pipeline finished: ${status}`, status === 'failed' ? 'error' : 'done');
            setStatus(status === 'failed' ? 'error' : status, status.toUpperCase());
            resetPipelineBtn();
            eventSource.close();
            if (status !== 'failed') showResults();
        });

        eventSource.addEventListener('error', (e) => {
            try {
                const d = JSON.parse(e.data);
                addTimelineItem('Error', d.data.error, 'error');
            } catch {
                addTimelineItem('Error', 'Connection lost', 'error');
            }
            resetPipelineBtn();
            setStatus('error', 'Error');
            eventSource.close();
        });
    }

    function clearTimeline() {
        timeline.innerHTML = '';
        if (timelineEmpty) timelineEmpty.remove();
    }

    function addTimelineItem(title, desc, cls, id = null) {
        // Remove empty state if present
        const empty = timeline.querySelector('.empty-state');
        if (empty) empty.remove();

        const el = document.createElement('div');
        el.className = `tl-item ${cls}`;
        if (id) el.id = id;
        const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        el.innerHTML = `
            <div class="tl-dot"></div>
            <div class="tl-body">
                <div class="tl-title">${title}</div>
                <div class="tl-desc">${desc}</div>
                <div class="tl-time">${time}</div>
            </div>`;
        timeline.appendChild(el);
        timeline.scrollTop = timeline.scrollHeight;
    }

    function setStatus(cls, text) {
        runStatus.className = `status-chip ${cls}`;
        runStatus.textContent = text;
    }

    function resetPipelineBtn() {
        submitBtn.disabled = false;
        btnLabel.textContent = 'Run Pipeline';
        btnSpinner.classList.add('hidden');
    }

    function showResults() {
        resultsPanel.classList.remove('hidden');
        resultsContent.innerHTML = `
            <div class="result-card">
                <div class="result-header">
                    <span class="result-name">Pipeline Complete</span>
                    <span class="result-score">✓</span>
                </div>
                <div class="result-email-body">All agents executed successfully. Check the Review Queue for any flagged outputs, or switch to the Candidates tab to see your candidate pool.</div>
            </div>`;
    }

    async function fetchPastRuns() {
        const container = document.getElementById('past-runs-container');
        if (!container) return;
        try {
            const res = await fetch('/pipeline/runs', {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('hr_token')}` }
            });
            const runs = await res.json();
            if (runs.length === 0) {
                container.innerHTML = '<div class="empty-state"><p>No past pipeline runs found.</p></div>';
                return;
            }
            container.innerHTML = runs.map(r => `
                <div class="history-item" onclick="viewRun('${r.id}')">
                    <button class="delete-btn" onclick="deleteRun(event, '${r.id}')" title="Delete Run">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                    </button>
                    <h4>${r.goal_text || 'Pipeline Run'}</h4>
                    <div class="date">${new Date(r.created_at).toLocaleString()}</div>
                    <div class="date" style="margin-top: 4px; text-transform: capitalize; display: flex; justify-content: space-between; align-items: center;">
                        Status: ${r.status}
                        ${(r.status === 'completed' || r.status === 'done' || r.status === 'paused_for_review') ? `
                            <button class="btn-text" style="font-size: 0.75rem; color: var(--accent); padding: 0;" onclick="openContinueModal(event, '${r.id}')">Resume</button>
                        ` : ''}
                    </div>
                </div>
            `).join('');
        } catch (err) {
            container.innerHTML = '<div class="empty-state"><p>Error loading runs.</p></div>';
        }
    }
    window.fetchPastRuns = fetchPastRuns;

    window.deleteRun = async function(e, runId) {
        e.stopPropagation(); // prevent clicking the history item
        if(!confirm("Are you sure you want to delete this run and all its data?")) return;
        
        try {
            const res = await fetch(`/pipeline/run/${runId}`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${localStorage.getItem('hr_token')}` }
            });
            if (res.ok) {
                fetchPastRuns();
            } else {
                alert("Failed to delete run.");
            }
        } catch (err) {
            alert("Error deleting run.");
        }
    };

    window.viewRun = function(runId) {
        // Switch to pipeline view
        const navPills = document.querySelectorAll('.nav-pill');
        const views = document.querySelectorAll('.view');
        navPills.forEach(p => p.classList.remove('active'));
        const pipelineBtn = document.querySelector('.nav-pill[data-target="pipeline"]');
        if (pipelineBtn) pipelineBtn.classList.add('active');
        
        views.forEach(v => {
            v.classList.remove('active');
            if (v.id === 'pipeline') v.classList.add('active');
        });
        
        clearTimeline();
        addTimelineItem('Viewing Past Run', `Run ID: ${runId}`, 'done');
        setStatus('done', 'VIEWING PAST RUN');
        document.getElementById('results-content').innerHTML = '';
        fetchEmails(runId);
        showResults();
    };

    window.openContinueModal = function(e, runId) {
        e.stopPropagation();
        document.getElementById('continue-run-id').value = runId;
        document.getElementById('continue-modal').classList.remove('hidden');
    };

    window.closeContinueModal = function() {
        document.getElementById('continue-modal').classList.add('hidden');
    };

    window.submitContinuePipeline = async function() {
        const runId = document.getElementById('continue-run-id').value;
        const extraK = document.getElementById('continue-extra-k').value;
        if (!runId || !extraK) return;
        
        closeContinueModal();
        viewRun(runId); // Switch to the pipeline tab to see what's happening
        
        try {
            const res = await fetch(`/pipeline/${runId}/continue`, {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('hr_token')}`
                },
                body: JSON.stringify({ extra_k: parseInt(extraK, 10) })
            });
            if (res.ok) {
                addTimelineItem('Pipeline Resumed', `Run ID: ${runId}, Extra K: ${extraK}`, 'running');
                connectSSE(runId);
            } else {
                alert('Failed to resume pipeline.');
            }
        } catch (err) {
            alert('Failed to resume pipeline.');
        }
    };


    // ────────────────────────────────────────
    // Candidate Management
    // ────────────────────────────────────────
    const uploadZone = document.getElementById('upload-zone');
    const fileInput = document.getElementById('file-input');
    const uploadProgress = document.getElementById('upload-progress');

    // Drag & drop
    fileInput.value = ''; // Force clear on page load to fix stuck browse button
    uploadZone.addEventListener('click', () => fileInput.click());
    uploadZone.addEventListener('dragover', (e) => { e.preventDefault(); uploadZone.classList.add('dragover'); });
    uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('dragover'));
    uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadZone.classList.remove('dragover');
        const files = Array.from(e.dataTransfer.files).filter(f => f.name.match(/\.(pdf|docx)$/i));
        if (files.length) {
            uploadFiles(files);
        } else {
            showUploadStatus('error', 'Invalid file type. Please upload a PDF or DOCX file.');
        }
    });

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length) uploadFiles(Array.from(fileInput.files));
    });

    async function uploadFiles(files) {
        showUploadStatus('loading', `Uploading ${files.length} file(s)…`);

        try {
            if (files.length === 1) {
                const fd = new FormData();
                fd.append('file', files[0]);
                const res = await fetch('/candidates/ingest', { method: 'POST', body: fd });
                const data = await res.json();
                
                if (!res.ok) {
                    showUploadStatus('error', `Error: ${data.detail || 'Upload failed. Please try logging in again.'}`);
                } else if (data.errors > 0) {
                    showUploadStatus('error', `Error: ${data.results[0].message}`);
                } else {
                    showUploadStatus('success', `✓ Ingested: ${data.results[0].name} (${data.results[0].email})`);
                    if(localStorage.getItem('hr_email')) fetchCandidates();
                }
            } else {
                const fd = new FormData();
                files.forEach(f => fd.append('files', f));
                const res = await fetch('/candidates/ingest/batch', { method: 'POST', body: fd });
                const data = await res.json();
                showUploadStatus(
                    data.errors > 0 ? 'error' : 'success',
                    `${data.ingested} ingested, ${data.errors} errors out of ${data.total} files`
                );
                if(localStorage.getItem('hr_email')) fetchCandidates();
            }
        } catch (err) {
            showUploadStatus('error', `Upload failed: ${err.message}`);
        }
        fileInput.value = '';
    }

    let uploadStatusTimer;
    function showUploadStatus(type, msg) {
        uploadProgress.className = `upload-progress ${type}`;
        uploadProgress.textContent = msg;
        uploadProgress.classList.remove('hidden');
        
        if (uploadStatusTimer) clearTimeout(uploadStatusTimer);
        
        if (type !== 'loading') {
            uploadStatusTimer = setTimeout(() => {
                uploadProgress.classList.add('hidden');
            }, 15000);
        }
    }

    // Folder import
    const folderBtn = document.getElementById('folder-ingest-btn');
    const folderStatus = document.getElementById('folder-status');

    folderBtn.addEventListener('click', async () => {
        const path = document.getElementById('folder-path').value.trim();
        if (!path) return;

        folderStatus.className = 'upload-progress loading';
        folderStatus.textContent = 'Importing…';
        folderStatus.classList.remove('hidden');

        try {
            const res = await fetch('/candidates/ingest/folder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ folder_path: path })
            });
            const data = await res.json();
            if (res.ok) {
                folderStatus.className = `upload-progress ${data.errors > 0 ? 'error' : 'success'}`;
                folderStatus.textContent = `${data.ingested} ingested, ${data.errors} errors out of ${data.total} files`;
                if(localStorage.getItem('hr_email')) fetchCandidates();
            } else {
                folderStatus.className = 'upload-progress error';
                folderStatus.textContent = data.detail || 'Import failed';
            }
        } catch (err) {
            folderStatus.className = 'upload-progress error';
            folderStatus.textContent = `Error: ${err.message}`;
        }
    });

    // Manual form
    const manualForm = document.getElementById('manual-form');
    const manualStatus = document.getElementById('manual-status');

    manualForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        manualStatus.className = 'upload-progress loading';
        manualStatus.textContent = 'Adding candidate…';
        manualStatus.classList.remove('hidden');
        
        const candidate = {
            name: document.getElementById('m-name').value,
            email: document.getElementById('m-email').value,
            current_title: document.getElementById('m-title').value,
            skills: document.getElementById('m-skills').value,
            years_of_experience: parseInt(document.getElementById('m-exp').value, 10),
            previous_companies: "",
            projects: "",
            summary: "",
            position_applied: ""
        };

        try {
            const res = await fetch('/candidates/ingest/manual', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(candidate)
            });
            const data = await res.json();
            if (res.ok && data.status === 'ingested') {
                manualStatus.className = 'upload-progress success';
                manualStatus.textContent = `✓ Added ${data.name}`;
                manualForm.reset();
                if(localStorage.getItem('hr_email')) fetchCandidates();
            } else {
                manualStatus.className = 'upload-progress error';
                manualStatus.textContent = data.message || 'Failed to add';
            }
        } catch (err) {
            manualStatus.className = 'upload-progress error';
            manualStatus.textContent = `Error: ${err.message}`;
        }
    });

    // Fetch & render candidates
    const candidateList = document.getElementById('candidates-container');
    const candidateCount = document.getElementById('candidate-count');
    
    let currentPage = 1;
    const pageSize = 20;
    let currentSearch = "";

    window.handleCandidateSearch = function(e) {
        currentSearch = e.target.value;
        currentPage = 1;
        fetchCandidates();
    };

    window.changePage = function(delta) {
        currentPage += delta;
        if (currentPage < 1) currentPage = 1;
        fetchCandidates();
    };

    document.getElementById('refresh-candidates-btn').addEventListener('click', fetchCandidates);

    async function fetchCandidates() {
        if(!candidateList) return;
        try {
            const skip = (currentPage - 1) * pageSize;
            const res = await fetch(`/candidates/?limit=${pageSize}&skip=${skip}&search=${encodeURIComponent(currentSearch)}`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('hr_token')}` }
            });
            if (!res.ok) throw new Error('Failed to load');
            const data = await res.json();
            const candidates = data.candidates;
            candidateCount.textContent = `${data.total} candidate${data.total !== 1 ? 's' : ''}`;

            if (candidates.length === 0) {
                candidateList.innerHTML = '<div class="empty-state"><p>No candidates found.</p></div>';
                document.getElementById('prev-page-btn').disabled = true;
                document.getElementById('next-page-btn').disabled = true;
                document.getElementById('page-indicator').textContent = `Page ${currentPage}`;
                return;
            }

            candidateList.innerHTML = candidates.map(c => `
                <div class="cand-card" style="cursor: pointer; position: relative;" onclick="openCandidateModal('${c.id}')">
                    <button class="delete-btn" style="position: absolute; top: 10px; right: 10px; background: none; border: none; color: #ff4757; cursor: pointer; padding: 4px; border-radius: 4px; z-index: 2;" onclick="deleteCandidate(event, '${c.id}')" title="Delete Candidate">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>
                    </button>
                    <div class="cand-name">${c.name || 'Unknown'}</div>
                    <div class="cand-email">${c.email || 'No email'}</div>
                    <div class="cand-meta">
                        <span>${c.years_of_experience}y exp</span>
                        ${c.current_title ? `<span>${c.current_title}</span>` : ''}
                    </div>
                    ${c.summary ? `<div class="cand-summary">${c.summary}</div>` : ''}
                </div>
            `).join('');
            
            document.getElementById('prev-page-btn').disabled = currentPage === 1;
            document.getElementById('next-page-btn').disabled = skip + candidates.length >= data.total;
            document.getElementById('page-indicator').textContent = `Page ${currentPage}`;
        } catch (err) {
            candidateList.innerHTML = `<div class="empty-state"><p>Could not load candidates: ${err.message}</p></div>`;
        }
    }
    window.fetchCandidates = fetchCandidates;
    
    window.deleteCandidate = async function(e, candidateId) {
        e.stopPropagation(); // prevent opening the modal
        if(!confirm("Are you sure you want to delete this candidate?")) return;
        
        try {
            const res = await fetch(`/candidates/${candidateId}`, {
                method: 'DELETE',
                headers: { 'Authorization': `Bearer ${localStorage.getItem('hr_token')}` }
            });
            if (res.ok) {
                fetchCandidates();
            } else {
                alert("Failed to delete candidate.");
            }
        } catch (err) {
            alert("Error deleting candidate.");
        }
    };
    
    window.openCandidateModal = async function(id) {
        try {
            const res = await fetch(`/candidates/${id}`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('hr_token')}` }
            });
            const c = await res.json();
            document.getElementById('modal-cand-name').textContent = c.name || 'Unknown';
            document.getElementById('modal-cand-email').textContent = c.email || 'No email';
            document.getElementById('modal-cand-title').textContent = c.current_title || '';
            document.getElementById('modal-cand-skills').textContent = c.skills && c.skills.length ? c.skills.join(', ') : 'None extracted';
            document.getElementById('modal-cand-exp').textContent = c.years_of_experience;
            document.getElementById('modal-cand-companies').textContent = c.previous_companies && c.previous_companies.length ? c.previous_companies.join(', ') : 'None listed';
            document.getElementById('modal-cand-summary').textContent = c.summary || 'No summary available.';
            
            document.getElementById('candidate-modal').classList.remove('hidden');
        } catch (err) {
            alert('Failed to load candidate details.');
        }
    };

    window.closeCandidateModal = function() {
        document.getElementById('candidate-modal').classList.add('hidden');
    };

    // ────────────────────────────────────────
    // Review Queue
    // ────────────────────────────────────────
    async function fetchReviewQueue() {
        const container = document.getElementById('review-container');
        const inlineSection = document.getElementById('inline-review-section');
        try {
            const res = await fetch('/review/queue', {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('hr_token')}` }
            });
            if (!res.ok) throw new Error('Failed to fetch');
            const queue = await res.json();

            if (queue.length === 0) {
                if (inlineSection) inlineSection.classList.add('hidden');
                document.getElementById('review-badge').classList.add('hidden');
                return;
            }

            if (inlineSection) inlineSection.classList.remove('hidden');
            document.getElementById('review-badge').textContent = queue.length;
            document.getElementById('review-badge').classList.remove('hidden');
            
            window.currentReviewQueue = queue;

            container.innerHTML = queue.map(item => {
                let contextHtml = '';
                if (item.context_data && item.context_data.length > 0) {
                    if (item.agent === 'JDAnalyser') {
                        const jd = item.context_data[0];
                        contextHtml = '<div class="review-context"><h4>Parsed Job Description</h4>' + `
                            <div class="rationale-box">
                                <p><strong>Role:</strong> ${jd.role_title || 'N/A'}</p>
                                <p><strong>Required Skills:</strong> ${jd.required_skills?.join(', ') || 'None'}</p>
                                <p><strong>Nice-to-Have Skills:</strong> ${jd.nice_to_have_skills?.join(', ') || 'None'}</p>
                                <p><strong>Experience:</strong> ${jd.experience_band || 'N/A'} (min ${jd.min_years_experience || 0} years)</p>
                                <p><strong>Red Flags:</strong> ${jd.red_flags && jd.red_flags.length > 0 ? jd.red_flags.map(rf => `<br>• [${rf.severity.toUpperCase()}] ${rf.flag}`).join('') : 'None'}</p>
                                <p><strong>Confidence:</strong> ${jd.confidence?.toFixed(2) || 'N/A'}</p>
                            </div>
                            <button class="btn-secondary" style="margin-top: 10px;" onclick="window.openJDEditorModal('${item.id}')">Edit Parsed JD</button>
                        ` + '</div>';
                    } else if (item.agent === 'CandidateScorer') {
                        contextHtml = `<div class="review-context">
                            <button class="btn-secondary" style="margin-top: 10px;" onclick="openCandidateScoreModal('${item.id}')">View Candidate Matches</button>
                        </div>`;
                    } else if (item.agent === 'OutreachDrafter') {
                        contextHtml = `<div class="review-context">
                            <button class="btn-secondary" style="margin-top: 10px;" onclick="openEmailEditorModal('${item.id}')">Review & Edit Emails</button>
                        </div>`;
                    }
                }

                return `
                <div class="review-card" id="review-${item.id}">
                    <div class="review-card-header">
                        <span class="review-agent">${item.agent}</span>
                        <span class="review-flag">Needs Review</span>
                    </div>
                    <div class="review-scores">
                        <span>Relevance: ${item.relevance.toFixed(2)}</span>
                        <span>Faithfulness: ${item.faithfulness.toFixed(2)}</span>
                        <span>Completeness: ${item.completeness.toFixed(2)}</span>
                    </div>
                    <div class="review-reason">${item.review_reason || 'Below threshold'}</div>
                    ${contextHtml}
                    <div class="review-actions">
                        <button class="btn-approve" onclick="submitReview('${item.id}', 'approved')">Approve</button>
                        <button class="btn-reject" onclick="submitReview('${item.id}', 'rejected')">Reject</button>
                    </div>
                </div>
                `;
            }).join('');
        } catch (err) {
            if (inlineSection) inlineSection.classList.remove('hidden');
            container.innerHTML = `<div class="empty-state"><p style="color:var(--red)">Error: ${err.message}</p></div>`;
        }
    }

    window.currentReviewItem = null;

    window.openCandidateScoreModal = function(evalId) {
        const item = window.currentReviewQueue.find(i => i.id === evalId);
        if (!item || !item.context_data || item.context_data.length === 0) return;
        
        window.currentReviewItem = item;
        
        const select = document.getElementById('score-cand-select');
        select.innerHTML = item.context_data.map(c => 
            `<option value="${c.candidate_id}">${c.candidate_name} (Score: ${c.final_score.toFixed(2)})</option>`
        ).join('');
        
        document.getElementById('candidate-score-modal').classList.remove('hidden');
        window.renderScoreCandidate(item.context_data[0].candidate_id);
    };
    
    window.renderScoreCandidate = function(candidateId) {
        if (!window.currentReviewItem) return;
        const c = window.currentReviewItem.context_data.find(x => x.candidate_id === candidateId);
        if (!c) return;
        
        document.getElementById('score-cand-name').textContent = `${c.candidate_name} — Score: ${c.final_score.toFixed(2)}`;
        
        const matched = c.rationale?.matched_skills || [];
        const missing = c.rationale?.missing_skills || [];
        
        document.getElementById('score-matched-skills').innerHTML = matched.map(s => `<span style="background: var(--green-bg); padding: 2px 6px; border-radius: 4px; font-size: 13px;">✓ ${s}</span>`).join('');
        document.getElementById('score-missing-skills').innerHTML = missing.map(s => `<span style="background: var(--red-bg); padding: 2px 6px; border-radius: 4px; font-size: 13px;">✗ ${s}</span>`).join('');
        document.getElementById('score-reasoning').textContent = c.rationale?.reasoning || 'No reasoning provided.';
    };

    window.closeScoreModal = function() {
        document.getElementById('candidate-score-modal').classList.add('hidden');
    };

    window.rejectCandidate = async function() {
        if (!window.currentReviewItem) return;
        const select = document.getElementById('score-cand-select');
        const candidateId = select.value;
        const runId = window.currentReviewItem.run_id;
        
        try {
            const res = await fetch(`/pipeline/${runId}/candidate/${candidateId}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('hr_token')}`
                }
            });
            if (res.ok) {
                alert('Candidate rejected and removed from pipeline.');
                
                // Remove from local memory
                window.currentReviewItem.context_data = window.currentReviewItem.context_data.filter(c => c.candidate_id !== candidateId);
                
                // If there are no more candidates, close the modal
                if (window.currentReviewItem.context_data.length === 0) {
                    closeScoreModal();
                    fetchReviewQueue(); // Re-render queue
                } else {
                    // Update dropdown
                    select.innerHTML = window.currentReviewItem.context_data.map(c => 
                        `<option value="${c.candidate_id}">${c.candidate_name} (Score: ${c.final_score.toFixed(2)})</option>`
                    ).join('');
                    
                    // Render the first remaining one
                    window.renderScoreCandidate(window.currentReviewItem.context_data[0].candidate_id);
                }
            } else {
                alert('Failed to reject candidate.');
            }
        } catch (err) {
            alert('Error rejecting candidate.');
        }
    };

    window.openEmailEditorModal = function(evalId) {
        const item = window.currentReviewQueue.find(i => i.id === evalId);
        if (!item || !item.context_data || item.context_data.length === 0) return;
        
        window.currentReviewItem = item;
        
        const select = document.getElementById('edit-email-select');
        select.innerHTML = item.context_data.map(e => 
            `<option value="${e.id}">${e.candidate_name}</option>`
        ).join('');
        
        document.getElementById('email-editor-modal').classList.remove('hidden');
        window.renderEmailCandidate(item.context_data[0].id);
    };
    
    window.renderEmailCandidate = function(emailId) {
        if (!window.currentReviewItem) return;
        const e = window.currentReviewItem.context_data.find(x => x.id === emailId);
        if (!e) return;
        
        document.getElementById('edit-email-id').value = e.id;
        document.getElementById('edit-email-to').textContent = e.candidate_email || `${e.candidate_name} (Email unknown)`;
        document.getElementById('edit-email-subject').value = e.subject;
        document.getElementById('edit-email-body').value = e.body;
    };

    window.closeEmailEditor = function() {
        document.getElementById('email-editor-modal').classList.add('hidden');
    };

    window.saveEmailEdits = async function() {
        const emailId = document.getElementById('edit-email-id').value;
        const subject = document.getElementById('edit-email-subject').value;
        const body = document.getElementById('edit-email-body').value;
        
        try {
            const res = await fetch(`/review/email/${emailId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('hr_token')}`
                },
                body: JSON.stringify({ subject, body })
            });
            if (res.ok) {
                alert('Email updated successfully!');
                // Update local memory so if they switch dropdowns, it retains the change
                if (window.currentReviewItem) {
                    const e = window.currentReviewItem.context_data.find(x => x.id === emailId);
                    if (e) {
                        e.subject = subject;
                        e.body = body;
                    }
                }
            } else {
                alert('Failed to update email.');
            }
        } catch (err) {
            alert('Failed to update email.');
        }
    };

    window.rejectEmail = async function() {
        if (!window.currentReviewItem) return;
        const select = document.getElementById('edit-email-select');
        const emailId = select.value;
        
        try {
            const res = await fetch(`/review/email/${emailId}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${localStorage.getItem('hr_token')}`
                }
            });
            if (res.ok) {
                alert('Email rejected and removed.');
                
                // Remove from local memory
                window.currentReviewItem.context_data = window.currentReviewItem.context_data.filter(e => e.id !== emailId);
                
                // If there are no more emails, close the modal
                if (window.currentReviewItem.context_data.length === 0) {
                    closeEmailEditor();
                    fetchReviewQueue(); // Re-render queue
                } else {
                    // Update dropdown
                    select.innerHTML = window.currentReviewItem.context_data.map(e => 
                        `<option value="${e.id}">${e.candidate_name}</option>`
                    ).join('');
                    
                    // Render the first remaining one
                    window.renderEmailCandidate(window.currentReviewItem.context_data[0].id);
                }
            } else {
                alert('Failed to reject email.');
            }
        } catch (err) {
            alert('Error rejecting email.');
        }
    };

    window.openJDEditorModal = function(evalId) {
        const item = window.currentReviewQueue.find(i => i.id === evalId);
        if (!item || !item.context_data || item.context_data.length === 0) return;
        
        window.currentReviewItem = item;
        const jd = item.context_data[0];
        
        document.getElementById('edit-jd-run-id').value = item.run_id;
        document.getElementById('edit-jd-exp').value = jd.experience_band || '';
        document.getElementById('edit-jd-min-yrs').value = jd.min_years_experience || 0;
        document.getElementById('edit-jd-role').value = jd.role_title || '';
        document.getElementById('edit-jd-req-skills').value = (jd.required_skills || []).join(', ');
        
        document.getElementById('jd-editor-modal').classList.remove('hidden');
    };

    window.closeJDEditor = function() {
        document.getElementById('jd-editor-modal').classList.add('hidden');
    };

    window.saveJDEdits = async function() {
        if (!window.currentReviewItem) return;
        
        const runId = document.getElementById('edit-jd-run-id').value;
        const exp = document.getElementById('edit-jd-exp').value;
        const minYrs = parseInt(document.getElementById('edit-jd-min-yrs').value, 10);
        const role = document.getElementById('edit-jd-role').value;
        const reqSkills = document.getElementById('edit-jd-req-skills').value.split(',').map(s => s.trim()).filter(s => s);
        
        const jd = window.currentReviewItem.context_data[0];
        
        const updatedJD = {
            ...jd,
            experience_band: exp,
            min_years_experience: minYrs,
            role_title: role,
            required_skills: reqSkills
        };
        
        try {
            const res = await fetch(`/pipeline/${runId}/jd`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('hr_token')}`
                },
                body: JSON.stringify({ extracted_jd: updatedJD })
            });
            if (res.ok) {
                alert('JD updated successfully!');
                // Update local memory and re-render
                jd.experience_band = exp;
                jd.min_years_experience = minYrs;
                jd.role_title = role;
                jd.required_skills = reqSkills;
                closeJDEditor();
                fetchReviewQueue(); // Re-fetch to update the UI
            } else {
                alert('Failed to update JD.');
            }
        } catch (err) {
            alert('Failed to update JD.');
        }
    };

    window.submitReview = async (evalId, decision, runId) => {
        try {
            await fetch(`/review/${evalId}/submit`, {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${localStorage.getItem('hr_token')}`
                },
                body: JSON.stringify({ decision, reviewer: 'Recruiter' })
            });
            const card = document.getElementById(`review-${evalId}`);
            if (card) card.remove();
            const badge = document.getElementById('review-badge');
            let count = parseInt(badge.textContent) - 1;
            badge.textContent = count;
            if (count <= 0) {
                badge.classList.add('hidden');
                document.getElementById('inline-review-section').classList.add('hidden');
                setStatus('running', 'Running');
                
                // Reconnect SSE if not active so we can hear when it finishes
                if (runId && (!eventSource || eventSource.readyState === EventSource.CLOSED)) {
                    eventSource = new EventSource(`/pipeline/${runId}/stream`);
                    
                    eventSource.addEventListener('state_change', (e) => {
                        const d = JSON.parse(e.data);
                        addTimelineItem('State', `${d.data.old_state} → ${d.data.new_state}`, 'completed');
                        if (d.data.new_state === 'paused_for_review') {
                            fetchReviewQueue();
                        }
                    });

                    eventSource.addEventListener('agent_started', (e) => {
                        const d = JSON.parse(e.data);
                        addTimelineItem(d.data.agent, `Started task: ${d.data.task}`, 'running');
                    });

                    eventSource.addEventListener('agent_completed', (e) => {
                        const d = JSON.parse(e.data);
                        addTimelineItem(d.data.agent, `Completed: ${d.data.summary} (${d.data.duration_s}s)`, 'completed');
                    });

                    eventSource.addEventListener('run_completed', (e) => {
                        const d = JSON.parse(e.data);
                        const status = d.data.status;
                        addTimelineItem('Done', `Pipeline finished: ${status}`, status === 'failed' ? 'error' : 'done');
                        setStatus(status === 'failed' ? 'error' : status, status.toUpperCase());
                        fetchEmails(runId);
                        eventSource.close();
                    });

                    eventSource.addEventListener('error', (e) => {
                        try {
                            const d = JSON.parse(e.data);
                            addTimelineItem('Error', d.data.error, 'error');
                            setStatus('error', 'Error');
                        } catch {
                            console.log("SSE Connection dropped");
                        }
                        eventSource.close();
                    });
                }
            }
        } catch {
            alert('Failed to submit review');
        }
    };

    async function fetchEmails(runId) {
        try {
            const res = await fetch(`/pipeline/${runId}/emails`, {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('hr_token')}` }
            });
            if (!res.ok) return;
            const emails = await res.json();
            
            if(emails && emails.length > 0) {
                const resultsContent = document.getElementById('results-content');
                
                const emailHtml = emails.map(e => `
                    <div style="background: rgba(255,255,255,0.03); border: 1px solid var(--glass-border); border-radius: var(--radius-sm); padding: 1rem; margin-top: 1rem; flex-basis: 100%;">
                        <h4 style="margin-top: 0;">To Candidate: ${e.candidate_id}</h4>
                        <p style="margin-bottom: 5px;"><strong>Subject:</strong> ${e.subject}</p>
                        <pre style="white-space: pre-wrap; font-family: inherit; font-size: 0.9rem; color: var(--text-secondary); background: rgba(0,0,0,0.2); padding: 10px; border-radius: 4px;">${e.body}</pre>
                        <div style="margin-top: 10px; text-transform: capitalize; font-size: 0.8rem; color: ${e.status === 'approved' ? 'var(--success)' : 'var(--warning)'};">
                            Status: ${e.status}
                        </div>
                    </div>
                `).join('');
                
                resultsContent.innerHTML += `<div style="margin-top: 1.5rem; width: 100%;"><h3>Generated Emails</h3>${emailHtml}</div>`;
            }
        } catch (err) {
            console.error("Failed to fetch emails:", err);
        }
    }
});


    window.submitEmailDecision = async (emailId, decision) => {
        const bodyElem = document.getElementById(`email-body-${emailId}`);
        const editedBody = bodyElem ? bodyElem.value : null;
        
        try {
            await fetch(`/review/email/${emailId}/decision`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    decision, 
                    edited_body: editedBody,
                    reviewer_email: localStorage.getItem('hr_email')
                })
            });
            const card = document.getElementById(`email-${emailId}`);
            if (card) card.remove();
        } catch(err) {
            alert('Failed to submit email decision');
        }
    };

    
    // Outreach Manual Form
    const outreachForm = document.getElementById('outreach-form');
    const previewCard = document.getElementById('outreach-preview-card');
    const previewSubject = document.getElementById('outreach-preview-subject');
    const previewBody = document.getElementById('outreach-preview-body');
    const sendOutreachBtn = document.getElementById('outreach-send-btn');
    
    if(outreachForm) {
        outreachForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = document.getElementById('draft-outreach-btn');
            const status = document.getElementById('outreach-status');
            btn.querySelector('.btn-spinner').classList.remove('hidden');
            previewCard.style.display = 'none';
            
            try {
                const res = await fetch('/pipeline/emails/draft', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        candidate_email: document.getElementById('outreach-cand-email').value,
                        intent: document.getElementById('outreach-intent').value,
                        custom_instructions: document.getElementById('outreach-custom').value
                    })
                });
                const data = await res.json();
                if (data.status === 'success') {
                    status.className = 'upload-progress success';
                    status.textContent = 'Draft generated successfully! Review below.';
                    status.classList.remove('hidden');
                    
                    // Show Preview
                    previewSubject.value = data.subject;
                    previewBody.value = data.body;
                    previewCard.dataset.email = data.candidate_email;
                    previewCard.style.display = 'block';
                } else {
                    throw new Error(data.detail || 'Unknown error');
                }
            } catch(err) {
                status.className = 'upload-progress error';
                status.textContent = err.message;
                status.classList.remove('hidden');
            } finally {
                btn.querySelector('.btn-spinner').classList.add('hidden');
            }
        });
    }
    
    if(sendOutreachBtn) {
        sendOutreachBtn.addEventListener('click', async () => {
            const candEmail = previewCard.dataset.email;
            const subject = previewSubject.value;
            const body = previewBody.value;
            
            try {
                sendOutreachBtn.textContent = "Sending...";
                const res = await fetch('/pipeline/emails/send_manual', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        candidate_email: candEmail,
                        subject: subject,
                        body: body
                    })
                });
                
                if (res.ok) {
                    alert("Email sent successfully via MCP!");
                    previewCard.style.display = 'none';
                    outreachForm.reset();
                    document.getElementById('outreach-status').classList.add('hidden');
                } else {
                    alert("Failed to send email.");
                }
            } catch(err) {
                alert("Network error: " + err);
            } finally {
                sendOutreachBtn.textContent = "Confirm & Send";
            }
        });
    }

    // Audit Log
    async function fetchAuditLog() {
        const container = document.getElementById('audit-container');
        if(!container) return;
        
        try {
            const res = await fetch('/audit/', {
                headers: { 'Authorization': `Bearer ${localStorage.getItem('hr_token')}` }
            });
            const logs = await res.json();
            if(!logs.length) {
                container.innerHTML = '<div class="empty-state"><p>No audit logs found.</p></div>';
                return;
            }
            
            container.innerHTML = logs.map(l => `
                <div class="glass-card" style="margin-bottom:1rem; padding: 1.5rem;">
                    <div style="display:flex; justify-content:space-between; margin-bottom:1rem; border-bottom:1px solid rgba(0,0,0,0.1); padding-bottom:0.5rem;">
                        <strong>Run: ${l.run_id}</strong>
                        <span class="status-chip idle">HR: ${l.created_by || 'Unknown'}</span>
                    </div>
                    <div style="margin-bottom:1rem;">
                        <p><strong>Goal:</strong> ${l.goal_text}</p>
                        <p><strong>JD Summary:</strong> ${l.jd_summary || 'N/A'}</p>
                    </div>
                    ${l.decisions.length ? `
                    <div style="background:rgba(255,255,255,0.5); padding:1rem; border-radius:8px;">
                        <h4>Review Decisions</h4>
                        ${l.decisions.map(d => `
                            <p style="margin:0.25rem 0;">
                                <strong>${d.reviewer}:</strong> ${d.decision} (Agent: ${d.agent}) 
                            </p>
                        `).join('')}
                    </div>
                    ` : '<p style="color:#888; font-size:0.9rem;">No reviews yet.</p>'}
                </div>
            `).join('');
        } catch(err) {
            console.error(err);
        }
    }
    window.fetchAuditLog = fetchAuditLog;
    
    const refreshAuditBtn = document.getElementById('refresh-audit-btn');
    if(refreshAuditBtn) {
        refreshAuditBtn.addEventListener('click', fetchAuditLog);
    }
