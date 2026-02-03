import * as apiClient from './api_client.js';

export async function renderSettingsView(container) {
    container.innerHTML = '<h2>Loading Settings...</h2>';

    const settings = await apiClient.fetchSettings();

    // Default values
    const scanInterval = settings.scan_interval ? parseInt(settings.scan_interval) / 60 : 5;
    const systemPrompt = settings.system_prompt_template || "You are a professional email assistant. Draft a reply based on the user's goal.";
    const licenseKey = settings.license_key || "";

    const isPaused = settings.scheduler_paused === 'true';
    const isManualMode = settings.manual_mode === 'true';
    const includeSig = settings.include_signature !== 'false';
    const aiProvider = settings.ai_provider || "ollama";
    const aiBaseUrl = settings.ai_base_url || "http://localhost:11434/v1";
    const aiApiKey = settings.ai_api_key || "ollama";

    let html = `
        <div class="settings-container" style="max-width: 800px; margin: 0 auto; padding: 20px;">
            <h1>Settings</h1>

            <div class="settings-section" style="margin-bottom: 30px; padding: 20px; background: #fff; border: 1px solid #ddd; border-radius: 8px;">
                <h3>⚡ Resource Management</h3>
                <p style="color:#666; font-size: 0.9em;">Control how much CPU/RAM Privemail uses.</p>
                
                <div style="margin-top: 15px; display: flex; align-items: center; justify-content: space-between;">
                    <div>
                        <label style="font-weight:bold; display:block;">Background Processing</label>
                        <span style="font-size:0.8em; color:#666;">Pause to stop analyzing new emails.</span>
                    </div>
                    <button id="btn-toggle-pause" style="padding: 8px 16px; border-radius: 4px; border: none; cursor: pointer; font-weight: bold; ${isPaused ? 'background:#fbbf24; color:#78350f;' : 'background:#e5e7eb; color:#374151;'}">
                        ${isPaused ? '⏸ PAUSED' : '▶ RUNNING'}
                    </button>
                </div>

                <div style="margin-top: 20px; border-top: 1px solid #eee; padding-top: 15px;">
                    <label style="font-weight:bold; display:block; margin-bottom:5px; color: #dc2626;">Emergency Stop</label>
                    <p style="font-size:0.8em; color:#666; margin-bottom: 10px;">If your computer is lagging, click this to immediately unload the AI model from memory.</p>
                    <button id="btn-unload" style="background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; padding: 8px 15px; border-radius: 4px; cursor: pointer;">
                        🛑 Unload AI Model
                    </button>
                </div>
            </div>

            <div class="settings-section" style="margin-bottom: 30px; padding: 20px; background: #fff; border: 1px solid #ddd; border-radius: 8px;">
                <h3>📧 Email Accounts</h3>
                <p style="color:#666; font-size: 0.9em;">Manage your connected email providers.</p>
                <div id="provider-list" style="margin-top: 15px;"></div>
                <button id="btn-add-provider" style="margin-top: 15px; background: #f3f4f6; color: #374151; border: 1px solid #d1d5db; padding: 8px 15px; border-radius: 4px; cursor: pointer;">
                    + Add Another Account
                </button>
            </div>

            <div class="settings-section" style="margin-bottom: 30px; padding: 20px; background: #fff; border: 1px solid #ddd; border-radius: 8px;">
                <h3>⚙️ Preferences</h3>
                
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px;">
                    <div>
                        <label style="font-weight:bold;">Manual Mode</label>
                        <p style="font-size:0.8em; color:#666; margin:0;">Fetch emails only. Generate drafts on click (Saves CPU).</p>
                    </div>
                    <input type="checkbox" id="chk-manual-mode" ${isManualMode ? 'checked' : ''} style="transform: scale(1.5);">
                </div>

                <div style="display: flex; align-items: center; justify-content: space-between;">
                    <div>
                        <label style="font-weight:bold;">Include Signature</label>
                        <p style="font-size:0.8em; color:#666; margin:0;">Append "(Drafted by Privemail AI)" to emails.</p>
                    </div>
                    <input type="checkbox" id="chk-signature" ${includeSig ? 'checked' : ''} style="transform: scale(1.5);">
                </div>
            </div>

            <div class="settings-section" style="margin-bottom: 30px; padding: 20px; background: #fff; border: 1px solid #ddd; border-radius: 8px;">
                <h3>📅 Scheduler</h3>
                <p style="color:#666; font-size: 0.9em;">How often should Privemail check Gmail for new messages?</p>
                <div style="margin-top: 10px;">
                    <label style="font-weight:bold;">Scan Interval (Minutes):</label>
                    <input type="number" id="set-interval" value="${scanInterval}" min="1" style="padding: 8px; width: 80px; margin-left: 10px;">
                </div>
            </div>

            <div class="settings-section" style="margin-bottom: 30px; padding: 20px; background: #fff; border: 1px solid #ddd; border-radius: 8px;">
                <h3>🧠 AI Persona (System Prompt)</h3>
                <p style="color:#666; font-size: 0.9em;">Define the base personality and rules for the AI model.</p>
                <textarea id="set-prompt" style="width: 100%; height: 150px; margin-top: 10px; padding: 10px; border: 1px solid #ccc; border-radius: 4px;">${systemPrompt}</textarea>
            </div>

            <div class="settings-section" style="margin-bottom: 30px; padding: 20px; background: #fff; border: 1px solid #ddd; border-radius: 8px;">
                <h3>🤖 AI Engine Configuration</h3>
                <p style="color:#666; font-size: 0.9em;">Connect to Ollama, LM Studio, or any OpenAI-compatible API.</p>
                
                <div style="margin-bottom: 15px;">
                    <label style="font-weight:bold; display:block; margin-bottom:5px;">Provider Type:</label>
                    <select id="set-ai-provider" style="width:100%; padding:8px; border: 1px solid #ddd; border-radius: 4px;">
                        <option value="ollama" ${aiProvider === 'ollama' ? 'selected' : ''}>Ollama (Local Native)</option>
                        <option value="openai_compatible" ${aiProvider === 'openai_compatible' ? 'selected' : ''}>OpenAI Compatible (Generic)</option>
                    </select>
                </div>

                <div style="margin-bottom: 15px;">
                    <label style="font-weight:bold; display:block; margin-bottom:5px;">Base URL:</label>
                    <input type="text" id="set-ai-base-url" value="${aiBaseUrl}" placeholder="http://localhost:11434/v1" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                    <p style="font-size:0.8em; color:#888; margin-top:4px;">For Ollama: <code>http://localhost:11434/v1</code><br>For LM Studio: <code>http://localhost:1234/v1</code></p>
                </div>

                <div style="margin-bottom: 20px;">
                    <label style="font-weight:bold; display:block; margin-bottom:5px;">API Key:</label>
                    <input type="password" id="set-ai-api-key" value="${aiApiKey}" placeholder="sk-..." style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                    <p style="font-size:0.8em; color:#888; margin-top:4px;">Leave as 'ollama' for local use. Required for OpenRouter/DeepSeek etc.</p>
                </div>
                
                <div style="border-top: 1px solid #eee; padding-top: 15px;">
                     <label style="font-weight:bold; display:block; margin-bottom:5px;">Google Connection:</label>
                     <button id="btn-reauth" style="background: #f3f4f6; color: #374151; border: 1px solid #d1d5db; padding: 8px 15px; border-radius: 4px; cursor: pointer;">
                        🔄 Re-Authenticate Google
                    </button>
                    <p style="font-size: 0.8em; color: #888; margin-top: 5px;">Click if syncing stops.</p>
                </div>
            </div>

            <div style="text-align: right;">
                <button id="btn-save-settings" style="background: #10b981; color: white; font-size: 1.1em; padding: 12px 24px; border: none; border-radius: 4px; cursor: pointer;">
                    Save All Settings
                </button>
            </div>
        </div>
    `;

    container.innerHTML = html;

    // --- LOAD PROVIDERS ---
    await loadProviders();

    // --- WIRE UP BUTTONS ---

    const btnPause = document.getElementById('btn-toggle-pause');
    btnPause.onclick = async () => {
        const currentlyPaused = btnPause.textContent.includes('PAUSED');
        const newState = !currentlyPaused;

        btnPause.textContent = "Saving...";

        try {
            await fetch(`/api/settings/pause?enabled=${newState}`, { method: 'POST' });

            if (newState) {
                btnPause.textContent = "⏸ PAUSED";
                btnPause.style.cssText = "padding: 8px 16px; border-radius: 4px; border: none; cursor: pointer; font-weight: bold; background:#fbbf24; color:#78350f;";
            } else {
                btnPause.textContent = "▶ RUNNING";
                btnPause.style.cssText = "padding: 8px 16px; border-radius: 4px; border: none; cursor: pointer; font-weight: bold; background:#e5e7eb; color:#374151;";
            }
        } catch (e) {
            alert("Failed to update pause state");
        }
    };

    const btnUnload = document.getElementById('btn-unload');
    btnUnload.onclick = async () => {
        const origText = btnUnload.textContent;
        btnUnload.textContent = "Stopping...";
        try {
            await fetch('/api/system/unload', { method: 'POST' });
            btnUnload.textContent = "Model Unloaded!";
        } catch (e) {
            btnUnload.textContent = "Failed";
        }
        setTimeout(() => btnUnload.textContent = origText, 3000);
    };

    document.getElementById('btn-save-settings').onclick = async () => {
        const btn = document.getElementById('btn-save-settings');
        const originalText = btn.textContent;
        btn.textContent = "Saving...";
        btn.disabled = true;

        const updates = [
            { key: "scan_interval", value: (parseInt(document.getElementById('set-interval').value) * 60).toString() },
            { key: "system_prompt_template", value: document.getElementById('set-prompt').value },
            { key: "manual_mode", value: document.getElementById('chk-manual-mode').checked.toString() },
            { key: "include_signature", value: document.getElementById('chk-signature').checked.toString() },

            // NEW: AI Settings
            { key: "ai_provider", value: document.getElementById('set-ai-provider').value },
            { key: "ai_base_url", value: document.getElementById('set-ai-base-url').value },
            { key: "ai_api_key", value: document.getElementById('set-ai-api-key').value }
        ];

        try {
            await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ settings: updates })
            });

            btn.textContent = "Saved!";
            btn.style.backgroundColor = "#059669";
            setTimeout(() => {
                btn.textContent = originalText;
                btn.style.backgroundColor = "#10b981";
                btn.disabled = false;
            }, 2000);
        } catch (e) {
            console.error(e);
            alert("Failed to save settings.");
            btn.textContent = originalText;
            btn.disabled = false;
        }
    };

    document.getElementById('btn-reauth').onclick = () => {
        if (confirm("This will disconnect your current session and ask you to login to Google again. Continue?")) {
            alert("Please restart the application to trigger the Google Login flow.");
        }
    };

    document.getElementById('btn-add-provider').onclick = () => {
        alert("To add a provider, go through the setup wizard again or use the API endpoints.");
    };
}

async function loadProviders() {
    try {
        const response = await fetch('/api/providers');
        const data = await response.json();

        const listEl = document.getElementById('provider-list');
        listEl.innerHTML = '';

        if (data.configured.length === 0) {
            listEl.innerHTML = '<p style="color: #888; font-style: italic;">No providers configured yet.</p>';
            return;
        }

        data.configured.forEach(provider => {
            const isActive = provider === data.active;
            const providerName = provider.charAt(0).toUpperCase() + provider.slice(1);

            const div = document.createElement('div');
            div.style.cssText = 'display: flex; align-items: center; justify-content: space-between; padding: 12px; margin-bottom: 10px; background: #f9fafb; border-radius: 6px; border: 1px solid #e5e7eb;';

            div.innerHTML = `
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span style="font-size: 20px;">${isActive ? '●' : '○'}</span>
                    <span style="font-weight: 500;">${providerName}</span>
                    ${isActive ? '<span style="background: #10b981; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.8em;">Active</span>' : ''}
                </div>
                <button
                    style="padding: 6px 12px; border-radius: 4px; border: 1px solid #d1d5db; background: white; cursor: pointer; ${isActive ? 'opacity: 0.5; cursor: not-allowed;' : ''}"
                    ${isActive ? 'disabled' : ''}
                    onclick="switchProvider('${provider}')"
                >
                    ${isActive ? 'Active' : 'Switch'}
                </button>
            `;

            listEl.appendChild(div);
        });
    } catch (error) {
        console.error('Failed to load providers:', error);
        document.getElementById('provider-list').innerHTML = '<p style="color: #dc2626;">Failed to load providers</p>';
    }
}

window.switchProvider = async function(provider) {
    if (!confirm(`Switch to ${provider}? You'll only see ${provider} emails until you switch back.`)) {
        return;
    }

    try {
        const response = await fetch('/api/provider', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider })
        });

        const data = await response.json();

        if (data.success) {
            await loadProviders();
            alert(`Switched to ${provider}. Refresh the inbox to see changes.`);
        } else {
            alert('Failed to switch: ' + (data.detail || 'Unknown error'));
        }
    } catch (error) {
        console.error('Switch provider error:', error);
        alert('Failed to switch provider: ' + error.message);
    }
}