document.addEventListener('DOMContentLoaded', () => {
    // --- Load Branding from server config ---
    async function loadBranding() {
        try {
            const res = await fetch('/config/branding');
            const brand = await res.json();
            
            // Split the name so the last word gets the gradient highlight
            const words = brand.app_name.trim().split(' ');
            const last = words.pop();
            const rest = words.join(' ');
            
            const nameEl = document.getElementById('brand-name');
            nameEl.innerHTML = rest 
                ? `${rest} <span class="highlight">${last}</span>`
                : `<span class="highlight">${last}</span>`;
            
            document.getElementById('page-title').textContent = brand.app_name;
            document.title = brand.app_name;
        } catch(e) {
            // Fallback if API is not reachable
            document.getElementById('brand-name').innerHTML = 'Hiring <span class="highlight">Pipeline</span>';
            document.getElementById('page-title').textContent = 'Hiring Pipeline';
        }
    }

    loadBranding();
    // --- Navigation ---
    const navBtns = document.querySelectorAll('.nav-btn');
    const viewSections = document.querySelectorAll('.view-section');

    navBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Update buttons
            navBtns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            // Update views
            const targetId = btn.getAttribute('data-target');
            viewSections.forEach(section => {
                section.classList.remove('active');
                if(section.id === targetId) {
                    section.classList.add('active');
                }
            });
            
            if(targetId === 'review-queue') {
                fetchReviewQueue();
            }
        });
    });

    // --- Pipeline Execution ---
    const form = document.getElementById('pipeline-form');
    const submitBtn = document.getElementById('submit-btn');
    const btnText = submitBtn.querySelector('.btn-text');
    const spinner = submitBtn.querySelector('.spinner');
    const timeline = document.getElementById('timeline');
    const runStatus = document.getElementById('run-status');
    const resultsPanel = document.getElementById('results-panel');
    const resultsContent = document.getElementById('results-content');
    
    let eventSource = null;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const goalText = document.getElementById('goal-text').value;
        const jdText = document.getElementById('jd-text').value;
        const topK = parseInt(document.getElementById('top-k').value, 10) || 5;

        // Reset UI
        submitBtn.disabled = true;
        btnText.textContent = "Initializing...";
        spinner.classList.remove('hidden');
        timeline.innerHTML = '';
        resultsPanel.classList.add('hidden');
        resultsContent.innerHTML = '';
        runStatus.className = 'status-badge running';
        runStatus.textContent = 'Running';

        try {
            const response = await fetch('/pipeline/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    goal_text: goalText,
                    raw_jd_text: jdText,
                    top_k: topK
                })
            });

            if (!response.ok) throw new Error("Failed to start pipeline");
            
            const data = await response.json();
            const runId = data.run_id;
            
            addTimelineItem('Pipeline Started', `Run ID: ${runId}`, 'running');
            connectSSE(runId);

        } catch (error) {
            console.error(error);
            addTimelineItem('Error', error.message, 'error');
            resetButton();
            runStatus.className = 'status-badge error';
            runStatus.textContent = 'Failed';
        }
    });

    function connectSSE(runId) {
        if (eventSource) {
            eventSource.close();
        }

        eventSource = new EventSource(`/pipeline/${runId}/stream`);

        eventSource.addEventListener('state_change', (e) => {
            const data = JSON.parse(e.data);
            addTimelineItem('State Transition', `${data.old_state} ➔ ${data.new_state}`, 'completed');
        });

        eventSource.addEventListener('agent_started', (e) => {
            const data = JSON.parse(e.data);
            addTimelineItem(`${data.agent} Started`, `Task: ${data.task}`, 'running', `task-${data.task}`);
        });

        eventSource.addEventListener('agent_completed', (e) => {
            const data = JSON.parse(e.data);
            // Replace the running item with completed
            const existingItem = document.getElementById(`task-${data.task}`);
            if (existingItem) existingItem.remove();
            
            addTimelineItem(`${data.agent} Completed`, data.summary, 'completed');
        });

        eventSource.addEventListener('eval_flagged', (e) => {
            const data = JSON.parse(e.data);
            addTimelineItem(`Evaluation Flagged`, `${data.agent} output flagged: ${data.reason}`, 'error');
            // Update badge
            const badge = document.getElementById('review-badge');
            badge.textContent = parseInt(badge.textContent) + 1;
            badge.classList.remove('hidden');
        });

        eventSource.addEventListener('run_completed', (e) => {
            const data = JSON.parse(e.data);
            addTimelineItem('Pipeline Finished', `Status: ${data.status}`, data.status === 'failed' ? 'error' : 'done');
            
            runStatus.className = `status-badge ${data.status === 'failed' ? 'error' : 'done'}`;
            runStatus.textContent = data.status.toUpperCase();
            
            resetButton();
            eventSource.close();
            
            // In a real app we'd fetch the actual emails generated, but we'll mock the UI display here 
            // since we don't have a GET /results endpoint yet.
            if(data.status !== 'failed') {
                showResultsMock();
            }
        });

        eventSource.addEventListener('error', (e) => {
            const data = JSON.parse(e.data);
            addTimelineItem('Fatal Error', data.error, 'error');
            resetButton();
            eventSource.close();
        });
    }

    function addTimelineItem(title, desc, statusClass, id = null) {
        const item = document.createElement('div');
        item.className = `timeline-item ${statusClass}`;
        if (id) item.id = id;
        
        const time = new Date().toLocaleTimeString();
        
        item.innerHTML = `
            <div class="timeline-icon">
                ${statusClass === 'completed' || statusClass === 'done' ? '✓' : ''}
                ${statusClass === 'error' ? '!' : ''}
            </div>
            <div class="timeline-content">
                <div class="timeline-title">${title}</div>
                <div class="timeline-desc">${desc}</div>
                <div class="timeline-meta">${time}</div>
            </div>
        `;
        timeline.appendChild(item);
        timeline.scrollTop = timeline.scrollHeight;
    }

    function resetButton() {
        submitBtn.disabled = false;
        btnText.textContent = "Execute Agents";
        spinner.classList.add('hidden');
    }

    function showResultsMock() {
        resultsPanel.classList.remove('hidden');
        resultsContent.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Candidate: Alice Smith</span>
                    <span class="card-score">92%</span>
                </div>
                <div class="email-body">Subject: Engineering Role at Antigravity\n\nHi Alice,\n\nI saw your background in Python and FastAPI and was really impressed. We are looking for someone exactly like you to lead our backend architecture...</div>
            </div>
            <div class="card">
                <div class="card-header">
                    <span class="card-title">Candidate: Bob Jones</span>
                    <span class="card-score">88%</span>
                </div>
                <div class="email-body">Subject: Exploring opportunities with Antigravity\n\nHi Bob,\n\nYour experience with PostgreSQL and vector databases caught my eye...</div>
            </div>
        `;
    }

    // --- Review Queue ---
    async function fetchReviewQueue() {
        const container = document.getElementById('review-container');
        try {
            const response = await fetch('/review/queue');
            if(!response.ok) throw new Error("Failed to fetch queue");
            const queue = await response.json();
            
            if(queue.length === 0) {
                container.innerHTML = '<div class="empty-state"><p>No items in the review queue. All good!</p></div>';
                document.getElementById('review-badge').classList.add('hidden');
                return;
            }
            
            document.getElementById('review-badge').textContent = queue.length;
            document.getElementById('review-badge').classList.remove('hidden');
            
            container.innerHTML = queue.map(item => `
                <div class="card" id="review-${item.id}">
                    <div class="card-header">
                        <span class="card-title">${item.agent}</span>
                        <span class="card-score" style="color:var(--status-pending)">Needs Review</span>
                    </div>
                    <div class="timeline-desc" style="margin-bottom:1rem">
                        <strong>Task:</strong> ${item.task_id}<br>
                        <strong>Reason:</strong> ${item.review_reason}
                    </div>
                    <div class="timeline-meta">
                        Rel: ${item.relevance.toFixed(2)} | Faith: ${item.faithfulness.toFixed(2)} | Comp: ${item.completeness.toFixed(2)}
                    </div>
                    <div class="review-actions">
                        <button class="btn-approve" onclick="submitReview('${item.id}', 'approved')">Approve</button>
                        <button class="btn-reject" onclick="submitReview('${item.id}', 'rejected')">Reject</button>
                    </div>
                </div>
            `).join('');
            
        } catch(e) {
            console.error(e);
            container.innerHTML = `<div class="empty-state"><p style="color:var(--status-error)">Error loading queue: ${e.message}</p></div>`;
        }
    }

    window.submitReview = async (evalId, decision) => {
        try {
            await fetch(`/review/${evalId}/submit`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ decision, reviewer: "Recruiter" })
            });
            document.getElementById(`review-${evalId}`).remove();
            
            // update badge
            const badge = document.getElementById('review-badge');
            let count = parseInt(badge.textContent) - 1;
            badge.textContent = count;
            if(count <= 0) badge.classList.add('hidden');
            
        } catch(e) {
            alert("Failed to submit review");
        }
    }
});
