import sys

with open('frontend/app.js', 'r') as f:
    content = f.read()

# 1. Add fetch wrapper with headers
fetch_wrapper = '''
    const originalFetch = window.fetch;
    window.fetch = async function() {
        let [resource, config] = arguments;
        if(config === undefined) {
            config = {};
        }
        if(config.headers === undefined) {
            config.headers = {};
        }
        
        const hrEmail = localStorage.getItem('hr_email');
        if(hrEmail) {
            config.headers['X-HR-Email'] = hrEmail;
        }
        return await originalFetch(resource, config);
    };
'''
content = fetch_wrapper + '\n' + content

# 2. Add Login logic
login_logic = '''
    // Auth & Login
    const loginScreen = document.getElementById('login-screen');
    const loginForm = document.getElementById('login-form');
    const hrEmailInput = document.getElementById('hr-email-input');
    const userProfile = document.getElementById('user-profile');
    const loggedInEmail = document.getElementById('logged-in-email');
    const logoutBtn = document.getElementById('logout-btn');

    function checkAuth() {
        const email = localStorage.getItem('hr_email');
        if (email) {
            if(loginScreen) loginScreen.style.display = 'none';
            if(userProfile) userProfile.style.display = 'flex';
            if(loggedInEmail) loggedInEmail.textContent = email;
            // Trigger fetches now that we are authenticated
            fetchCandidates();
            fetchReviewQueue();
            if(typeof fetchAuditLog === 'function') fetchAuditLog();
        } else {
            if(loginScreen) loginScreen.style.display = 'flex';
            if(userProfile) userProfile.style.display = 'none';
        }
    }

    if(loginForm) {
        loginForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const email = hrEmailInput.value.trim();
            if (email) {
                localStorage.setItem('hr_email', email);
                checkAuth();
            }
        });
    }

    if(logoutBtn) {
        logoutBtn.addEventListener('click', () => {
            localStorage.removeItem('hr_email');
            checkAuth();
        });
    }

    // Check auth on load
    checkAuth();
'''
content = content.replace("document.addEventListener('DOMContentLoaded', () => {", "document.addEventListener('DOMContentLoaded', () => {\n" + login_logic)

# 3. Prevent fetching candidates if not auth'd
content = content.replace("fetchCandidates();", "if(localStorage.getItem('hr_email')) fetchCandidates();")

# 4. Add submitEmailDecision, Outreach Draft, and Audit Log logic
extra_logic = '''
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
    if(outreachForm) {
        outreachForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = document.getElementById('draft-outreach-btn');
            const status = document.getElementById('outreach-status');
            btn.querySelector('.btn-spinner').classList.remove('hidden');
            
            try {
                const res = await fetch('/pipeline/emails/draft', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        candidate_id: document.getElementById('outreach-cand-id').value,
                        intent: document.getElementById('outreach-intent').value
                    })
                });
                const data = await res.json();
                status.className = 'upload-progress success';
                status.textContent = `Drafted ${data.emails_drafted} email(s) successfully!`;
                status.classList.remove('hidden');
            } catch(err) {
                status.className = 'upload-progress error';
                status.textContent = err.message;
                status.classList.remove('hidden');
            } finally {
                btn.querySelector('.btn-spinner').classList.add('hidden');
            }
        });
    }

    // Audit Log
    async function fetchAuditLog() {
        const container = document.getElementById('audit-container');
        if(!container) return;
        
        try {
            const res = await fetch('/audit/');
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
'''
content = content + '\n' + extra_logic

with open('frontend/app.js', 'w') as f:
    f.write(content)
