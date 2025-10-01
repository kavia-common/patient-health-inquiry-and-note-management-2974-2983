(function () {
  // Simple config with localStorage
  const els = {
    apiBaseUrl: document.getElementById('apiBaseUrl'),
    patientId: document.getElementById('patientId'),
    startBtn: document.getElementById('startConversationBtn'),
    convoId: document.getElementById('conversationId'),
    msgCount: document.getElementById('messageCount'),
    updatedAt: document.getElementById('updatedAt'),
    messages: document.getElementById('messages'),
    messageInput: document.getElementById('messageInput'),
    sendMsgBtn: document.getElementById('sendMsgBtn'),
    askFollowBtn: document.getElementById('askFollowBtn'),
    genSummaryBtn: document.getElementById('genSummaryBtn'),
    genSaveSummaryBtn: document.getElementById('genSaveSummaryBtn'),
    noteTitle: document.getElementById('noteTitle'),
    saveFilename: document.getElementById('saveFilename'),
    summaryOutput: document.getElementById('summaryOutput'),
    saveResult: document.getElementById('saveResult'),
    statusBar: document.getElementById('statusBar'),
  };

  // Compute a sensible default API base when not provided by the user.
  function computeDefaultApiBase() {
    // If page is being served via a proxy path like /proxy/8000/,
    // ALWAYS route API through the same proxy as /proxy/3001/api
    try {
      const { origin, pathname } = window.location;
      const proxyMatch = pathname.match(/^\/proxy\/(\d+)\/?/);
      const backendPort = 3001;

      if (proxyMatch) {
        // Under proxy path; stick to same host + /proxy/3001/api.
        return `${origin}/proxy/${backendPort}/api`;
      }

      // Not under a proxy path: prefer same-origin relative proxy form in case a gateway maps it,
      // else fall back to same-origin /api (assuming backend co-served on same origin).
      // We intentionally avoid any direct internal DNS or explicit host:port defaults.
      return `${origin}/api`;
    } catch {
      // Last-resort safe relative path; never use internal DNS in browser.
      return '/proxy/3001/api';
    }
  }

  // Default values for quick start
  const storedApiBase = localStorage.getItem('ocean.apiBase');
  const isUnderProxy = /^\/proxy\/(\d+)\/?/.test(window.location.pathname);

  // When under proxy, we override any previously stored value to enforce proxied access.
  const effectiveDefaultApiBase = isUnderProxy
    ? `${window.location.origin}/proxy/3001/api`
    : (storedApiBase || computeDefaultApiBase());

  const defaults = {
    apiBase: effectiveDefaultApiBase,
    patientId: localStorage.getItem('ocean.patientId') || 'patient-123',
  };
  els.apiBaseUrl.value = defaults.apiBase;
  els.patientId.value = defaults.patientId;

  function setStatus(text, kind = 'info') {
    els.statusBar.textContent = text;
    els.statusBar.style.color = kind === 'error' ? 'var(--error)' : 'var(--muted)';
  }

  function saveConfig() {
    localStorage.setItem('ocean.apiBase', els.apiBaseUrl.value.trim());
    localStorage.setItem('ocean.patientId', els.patientId.value.trim());
  }

  function normalizeApiBase(raw) {
    let base = (raw || '').trim();

    // If browser is under a proxy path, enforce using the proxy path regardless of user-provided host.
    if (/^\/proxy\/(\d+)\/?/.test(window.location.pathname)) {
      // Accept relative '/proxy/3001' or absolute same-origin forms, but normalize to absolute same-origin proxy path.
      return `${window.location.origin}/proxy/3001/api`;
    }

    // If user pasted docs/redoc/openapi URL, normalize to host root
    try {
      const u = new URL(base, window.location.origin);
      if (
        u.pathname.startsWith('/docs') ||
        u.pathname.startsWith('/redoc') ||
        u.pathname.startsWith('/openapi')
      ) {
        u.pathname = '/';
        u.search = '';
        u.hash = '';
        base = u.toString();
      } else {
        base = u.toString();
      }
    } catch {
      // Non-URL input; allow relative paths like /proxy/3001/api
    }

    // Block using internal container DNS names in the browser for security and CORS stability.
    const disallowedHosts = [
      'vscode-internal', // generic guard against vscode-internal-*.cloud.kavia.ai direct container urls
      '.svc.cluster.local',
      '.internal',
      '.docker.internal',
    ];
    try {
      const parsed = new URL(base, window.location.origin);
      const hostLower = parsed.hostname.toLowerCase();
      if (disallowedHosts.some(h => hostLower.includes(h))) {
        // Replace with safer default under same origin
        base = `${window.location.origin}/proxy/3001/api`;
      } else {
        base = parsed.toString();
      }
    } catch {
      // If still not a full URL, keep as-is (may be a relative /proxy/3001/api)
    }

    // Remove trailing slashes
    base = base.replace(/\/*$/, '');

    // Ensure it ends with /api
    if (!/\/api$/.test(base)) {
      base = `${base}/api`;
    }
    return base;
  }

  function getApi(path) {
    const base = normalizeApiBase(els.apiBaseUrl.value);
    return `${base}${path}`;
  }

  let state = {
    conversationId: null,
    messages: [], // {sender:'patient'|'bot', text:string}
  };

  function renderMessages() {
    els.messages.innerHTML = '';
    state.messages.forEach(m => {
      const row = document.createElement('div');
      row.className = `message ${m.sender}`;
      const bubble = document.createElement('div');
      bubble.className = 'bubble';
      bubble.textContent = m.text;
      row.appendChild(bubble);
      els.messages.appendChild(row);
    });
    els.messages.scrollTop = els.messages.scrollHeight;
  }

  function updateConvoInfo({ message_count, updated_at }) {
    if (typeof message_count === 'number') {
      els.msgCount.textContent = String(message_count);
    }
    els.updatedAt.textContent = updated_at ? new Date(updated_at).toLocaleString() : '—';
  }

  async function pollStatus() {
    if (!state.conversationId) return;
    try {
      const url = getApi(`/conversations/status/?conversation_id=${encodeURIComponent(state.conversationId)}`);
      const res = await fetch(url);
      const data = await res.json();
      if (res.ok && data.status === 'success') {
        updateConvoInfo({
          message_count: data.data.message_count,
          updated_at: data.data.updated_at,
        });
      }
    } catch (e) {
      // no-op on polling errors
    }
  }

  setInterval(pollStatus, 5000);

  function setConversationId(id) {
    state.conversationId = id;
    els.convoId.textContent = id || '—';
  }

  async function startConversation() {
    saveConfig();
    const patient_id = els.patientId.value.trim();
    if (!patient_id) {
      setStatus('Please enter a Patient ID to start.', 'error');
      return;
    }
    setStatus('Starting conversation...');
    try {
      const res = await fetch(getApi('/conversations/start/'), {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ patient_id }),
      });
      const body = await res.json();
      if (!res.ok || body.status !== 'success') throw new Error(body?.error?.message || 'Failed to start conversation');
      const { conversation_id, created_at, updated_at } = body.data;
      setConversationId(conversation_id);
      updateConvoInfo({ message_count: 0, updated_at: updated_at || created_at });
      state.messages = [];
      renderMessages();
      setStatus('Conversation started.');
    } catch (e) {
      console.error(e);
      setStatus(`Error: ${e.message}`, 'error');
    }
  }

  async function sendMessage() {
    saveConfig();
    const text = els.messageInput.value.trim();
    if (!text) return;
    const patient_id = els.patientId.value.trim();
    if (!state.conversationId && !patient_id) {
      setStatus('Provide Patient ID or start a conversation first.', 'error');
      return;
    }
    setStatus('Sending...');
    try {
      const res = await fetch(getApi('/conversations/send/'), {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({
          conversation_id: state.conversationId || '00000000-0000-0000-0000-000000000000',
          sender: 'patient',
          text,
          patient_id: state.conversationId ? undefined : patient_id,
        }),
      });
      const body = await res.json();
      if (!res.ok || body.status !== 'success') throw new Error(body?.error?.message || 'Failed to send message');

      // If a new conversation was created, store its id
      if (body.data.created_new_conversation && body.data.conversation_id) {
        setConversationId(body.data.conversation_id);
      }

      // Append the patient message
      state.messages.push({ sender: 'patient', text });
      els.messageInput.value = '';

      // If backend generated a bot follow-up in the same response, render it now (even if empty string)
      if (body?.data?.ai_follow_up) {
        const q = (body.data.ai_follow_up.question ?? '');
        const qStr = String(q);
        // Surface actual LLM output; if empty show ellipsis bubble to indicate AI responded with nothing
        state.messages.push({ sender: 'bot', text: qStr.length ? qStr.trim() : '…' });
      } else {
        console.warn('AI follow-up payload missing or malformed.', body?.data);
      }

      // If backend reported AI error, surface it to the user
      if (body?.data?.ai_error) {
        const msg = body.data.ai_error.message || 'AI follow-up failed.';
        setStatus(`AI notice: ${msg}`, 'error');
        console.warn('AI follow-up error details:', body.data.ai_error);
      } else {
        setStatus('Sent.');
      }

      renderMessages();
      await pollStatus();
    } catch (e) {
      console.error(e);
      setStatus(`Error: ${e.message}`, 'error');
    }
  }

  async function askFollowUp() {
    if (!state.conversationId) {
      setStatus('Start or send a message to create a conversation first.', 'error');
      return;
    }
    setStatus('Requesting AI follow-up...');
    try {
      const res = await fetch(getApi('/ai/next-follow-up/'), {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ conversation_id: state.conversationId }),
      });
      const body = await res.json();
      if (!res.ok || body.status !== 'success') throw new Error(body?.error?.message || 'Failed to get follow-up');
      const question = body.data.question || '…';
      // Render the bot follow-up in the chat for context (note: backend stores messages; this UI only reflects bot prompt)
      state.messages.push({ sender: 'bot', text: question });
      renderMessages();
      await pollStatus();
      setStatus('Follow-up received.');
    } catch (e) {
      console.error(e);
      setStatus(`Error: ${e.message}`, 'error');
    }
  }

  async function generateSummary(viewOnly) {
    if (!state.conversationId) {
      setStatus('No conversation to summarize. Start a conversation first.', 'error');
      return;
    }
    const note_title = els.noteTitle.value.trim();
    setStatus(viewOnly ? 'Generating summary...' : 'Generating & saving summary...');
    els.summaryOutput.textContent = '';
    els.saveResult.textContent = '';
    try {
      if (viewOnly) {
        const res = await fetch(getApi('/notes/generate/'), {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ conversation_id: state.conversationId, note_title }),
        });
        const body = await res.json();
        if (!res.ok || body.status !== 'success') throw new Error(body?.error?.message || 'Failed to generate note');
        const { note_title: t, note_text } = body.data;
        els.summaryOutput.textContent = note_text || '(empty)';
        setStatus(`Summary generated${t ? `: ${t}` : ''}.`);
      } else {
        let filename = els.saveFilename.value.trim();
        if (!filename) {
          filename = `${els.patientId.value.trim() || 'patient'}-summary.txt`;
        }
        const res = await fetch(getApi('/ai/generate-and-save-summary/'), {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({ conversation_id: state.conversationId, filename, note_title }),
        });
        const body = await res.json();
        if (!res.ok || body.status !== 'success') throw new Error(body?.error?.message || 'Failed to generate & save summary');
        const { note_title: t, save_result } = body.data;
        els.summaryOutput.textContent = `Summary generated: ${t || '(untitled)'}\nSaved file: ${save_result?.filename}\nPath: ${save_result?.path}\nBytes: ${save_result?.bytes_written}`;
        els.saveResult.textContent = 'Save successful.';
        setStatus('Summary generated and saved.');
      }
    } catch (e) {
      console.error(e);
      setStatus(`Error: ${e.message}`, 'error');
      els.summaryOutput.textContent = '';
      els.saveResult.textContent = '';
    }
  }

  // Wire up events
  els.startBtn.addEventListener('click', startConversation);
  els.sendMsgBtn.addEventListener('click', sendMessage);
  els.messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  els.askFollowBtn.addEventListener('click', askFollowUp);
  els.genSummaryBtn.addEventListener('click', () => generateSummary(true));
  els.genSaveSummaryBtn.addEventListener('click', () => generateSummary(false));

  // Try quick backend health check to update status with better diagnostics
  (async function initHealth() {
    const url = getApi('/health/');
    try {
      const res = await fetch(url, { method: 'GET' });
      const text = await res.text().catch(() => '');
      let body = {};
      try { body = JSON.parse(text); } catch { /* not json */ }

      if (res.ok && body && body.status === 'success') {
        setStatus('Backend reachable.');
      } else {
        const detail = res.ok ? 'Unexpected response body' : `HTTP ${res.status}`;
        // Show a concise hint in UI and detailed info in console for debugging
        const hint = window.location.pathname.startsWith('/proxy/')
          ? 'Tip: when UI is under /proxy/8000/, keep API Base as /proxy/3001/api (default).'
          : 'Verify API Base ends with /api and prefer same-origin access.';
        setStatus(`Backend not reachable. ${detail}. ${hint}`, 'error');
        console.warn('Health check failed:', {
          url,
          status: res.status,
          ok: res.ok,
          textSnippet: (text || '').slice(0, 200),
          parsed: body,
        });
      }
    } catch (err) {
      // Likely network/CORS/TLS or mixed-content blocks
      const hint = window.location.pathname.startsWith('/proxy/')
        ? 'Ensure API Base is /proxy/3001/api for proxied setup.'
        : 'Ensure protocol/host/port and /api are correct.';
      setStatus(`Backend not reachable (network/CORS/TLS). ${hint}`, 'error');
      console.error('Health check network error:', { url, error: err });
    }
  })();
})();
