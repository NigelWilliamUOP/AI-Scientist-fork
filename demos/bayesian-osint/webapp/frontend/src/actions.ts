function showModal(html: string): void { modal.innerHTML = `<button class="modal-close quiet" data-action="close-modal" aria-label="Close dialogue">${icon('close')}</button>${html}`; modal.showModal(); wire(modal); }
function modeModal(): void { showModal(`<div class="eyebrow">EVIDENCE TIME BOUNDARY</div><h2>Choose an investigation mode</h2><p>Each choice creates a separate session. Older sessions remain saved.</p><div class="mode-options">${action('current', 'Current investigation<br><small>Real retained evidence; allowlisted collection available.</small>')}${action('before', 'Historical: 5 Oct 2024, 15:22 UTC<br><small>Before the title correction; inspected later.</small>')}${action('after', 'Historical: 5 Oct 2024, 15:26 UTC<br><small>After the title correction; inspected later.</small>')}${action('frozen', 'Freeze retained evidence<br><small>No new network or model calls in this snapshot.</small>')}</div>`); }
function settingsModal(): void { showModal(`<div class="eyebrow">CONNECTION STATUS</div><h2>Server-side integrations</h2><div class="settings-grid"><section><h3>OpenRouter</h3>${statusTag(label(user!.ai_status), 'warn')}<p>Set <code>AI_PROVIDER=openrouter</code>, an exact <code>OPENROUTER_MODEL</code>, approved endpoint providers and the key in the host’s secret store. Paid calls require <code>ALLOW_PAID_AI=true</code>.</p><p>Session ceiling $${user!.limits.session_usd}; daily ceiling $${user!.limits.day_usd}; per-call ceiling $${user!.limits.call_usd}.</p><p class="small">No key is accepted through the browser or stored in this page.</p></section><section><h3>Google Drive</h3>${statusTag(label(user!.drive_status), 'warn')}<p>The app creates its own folder using narrow <code>drive.file</code> permission. Archive verification requires downloading the uploaded bytes and matching their hash.</p>${user!.role === 'owner' ? action('drive-connect', 'Connect owner’s Google Drive', '', 'primary') : ''}</section></div><div class="callout">Configuration is not verification. A real provider response and verified Drive readback remain separate release gates.</div><p class="small muted">Release ${esc(user!.release)}. Local plaintext HTTP is allowed only on loopback; deployed mode requires HTTPS.</p>`); }
function reviewModal(): void { showModal(`<div class="eyebrow">HUMAN REVIEW GATE</div><h2>Accept this assessment?</h2><p>Shared revision ${workspace!.assessment.revision} will become ${workspace!.assessment.revision + 1}. Removing a source later will not silently rewrite this record.</p><label for="review-note">Why does the cited evidence support the wording?</label><textarea id="review-note" rows="4" maxlength="2000" placeholder="Record your review rationale (at least 10 characters)."></textarea><label class="review-check"><input type="checkbox" id="support-checked"> I inspected the citations and reviewed whether the wording follows from them.</label>${action('accept-review', 'Record reviewed assessment', '', 'primary')}<p class="small muted">A successful exact-quote check is not sufficient by itself.</p>`); }
async function newMode(mode: Mode, cutoff?: string): Promise<void> { modal.close(); const r = await api<{
    id: string;
}>('/sessions', { mode, cutoff: cutoff || null, from_session_id: mode === 'RECORDED_REPLAY' ? sid : null }); sid = r.id; localStorage.setItem('osint.session', sid); draft = null; draftJob = null; currentExport = null; selectedSource = null; await load(); }
async function awaitJob(identity: string): Promise<void> { busy = true; render(); const startedSession = sid; try {
    for (let i = 0; i < 180; i++) {
        await new Promise(r => setTimeout(r, 700));
        if (sid !== startedSession)
            return;
        const job = await api<Job>('/jobs/' + identity);
        workspace = await api<Workspace>('/sessions/' + sid + '/workspace');
        if (job.state === 'completed') {
            if (job.result?.kind === 'answer') {
                draft = job.result;
                draftJob = identity;
            }
            else if (job.result?.kind === 'refresh') {
                const failed = job.result.sources?.filter(s => s.state === 'failed').length || 0;
                toast(failed ? `${failed} source refresh(es) failed. Retained evidence preserved.` : `${job.result.success_count} source(s) captured. Inspect the change status.`, failed > 0);
            }
            else if (job.result?.kind === 'archive') {
                toast('Drive upload and byte readback verified.');
            }
            await fetchDetail();
            return;
        }
        if (job.state === 'failed')
            throw new Error(messages[job.error || ''] || label(job.error || 'Job failed'));
        render();
    }
    toast('The task is still recorded on the server. Reload to inspect its status.');
}
finally {
    busy = false;
    render();
    if (draft)
        document.querySelector('#draft-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
} }
function wire(scope: ParentNode = root): void { scope.querySelectorAll<HTMLElement>('[data-action]').forEach(el => { el.onclick = () => { void handle(el).catch(e => toast((e as Error).message, true)); }; if (el instanceof SVGElement) {
    el.onkeydown = (event: KeyboardEvent) => { if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        void handle(el).catch(e => toast((e as Error).message, true));
    } };
} }); const filterBox = document.querySelector<HTMLInputElement>('#source-filter'); if (filterBox)
    filterBox.oninput = () => { filter = filterBox.value; document.querySelector('#source-list')!.innerHTML = sourceCards(); wire(document.querySelector('#source-list')!); }; const question = document.querySelector<HTMLTextAreaElement>('#research-question'); if (question)
    question.oninput = () => { query = question.value; }; }
async function handle(el: HTMLElement | SVGElement): Promise<void> { const a = el.dataset.action; if (a === 'select') {
    selectedSource = el.dataset.id || null;
    await fetchDetail();
    render();
    return;
} if (a === 'tab') {
    tab = el.dataset.tab || 'network';
    render();
    return;
} if (a === 'close-modal') {
    modal.close();
    return;
} if (a === 'settings') {
    settingsModal();
    return;
} if (a === 'mode') {
    modeModal();
    return;
} if (a === 'current') {
    await newMode('CURRENT_INVESTIGATION');
    return;
} if (a === 'before' || a === 'after') {
    tab = 'timeline';
    await newMode('HISTORICAL_RECONSTRUCTION', a === 'before' ? '2024-10-05T15:22:00Z' : '2024-10-05T15:26:00Z');
    return;
} if (a === 'frozen') {
    await newMode('RECORDED_REPLAY');
    return;
} if (a === 'preset') {
    query = el.dataset.q || query;
    document.querySelector<HTMLTextAreaElement>('#research-question')!.value = query;
    return;
} if (a === 'exclude') {
    const source = workspace!.sources.find(s => s.id === el.dataset.id)!;
    await api('/sessions/' + sid + '/exclusions', { source_id: source.id, excluded: !source.excluded });
    draft = null;
    draftJob = null;
    await load();
    toast(source.excluded ? 'Source reinstated.' : 'Source excluded in this scenario. Shared acceptance unchanged.');
    return;
} if (a === 'refresh') {
    const r = await api<{
        job_id: string;
    }>('/sessions/' + sid + '/refresh', { source_ids: ['CF-AWARD', 'FTS-PIN', 'FTS-TENDER', 'FTS-CORRECTION'] });
    await awaitJob(r.job_id);
    return;
} if (a === 'compile' || a === 'ask') {
    const second = document.querySelector<HTMLInputElement>('#challenge')?.checked || false;
    const r = await api<{
        job_id: string;
    }>('/sessions/' + sid + '/questions', { question: query, use_ai: a === 'ask', challenge: a === 'ask' && second });
    await awaitJob(r.job_id);
    return;
} if (a === 'citation') {
    const source = workspace!.sources.find(s => s.version_id === el.dataset.version);
    if (!source)
        return;
    selectedSource = source.id;
    await fetchDetail();
    render();
    const target = document.getElementById('segment-' + el.dataset.segment);
    target?.classList.add('highlight');
    target?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    return;
} if (a === 'export') {
    currentExport = await api<Export>('/sessions/' + sid + '/exports', {});
    await load();
    showExport();
    return;
} if (a === 'sync-export') {
    const r = await api<{
        job_id: string;
    }>('/exports/' + currentExport!.id + '/sync', {});
    modal.close();
    await awaitJob(r.job_id);
    currentExport = await api<Export>('/exports/' + currentExport!.id);
    showExport();
    return;
} if (a === 'review') {
    reviewModal();
    return;
} if (a === 'accept-review') {
    const rationale = document.querySelector<HTMLTextAreaElement>('#review-note')!.value;
    const checked = document.querySelector<HTMLInputElement>('#support-checked')!.checked;
    if (!checked || rationale.trim().length < 10) {
        toast('Add a review rationale and confirm the support check.', true);
        return;
    }
    await api('/sessions/' + sid + '/review', { job_id: draftJob, expected_revision: workspace!.assessment.revision, rationale, support_checked: true });
    modal.close();
    await load();
    toast('Human-reviewed assessment recorded.');
    return;
} if (a === 'drive-connect') {
    const r = await api<{
        authorization_url: string;
    }>('/owner/drive/connect', {});
    if (new URL(r.authorization_url).hostname !== 'accounts.google.com')
        throw new Error('Unexpected OAuth destination.');
    window.location.assign(r.authorization_url);
    return;
} if (a === 'map-tiles') {
    mapEnabled = true;
    render();
    return;
} if (a === 'zoom-in' || a === 'zoom-out') {
    zoom = Math.max(.8, Math.min(1.3, zoom + (a === 'zoom-in' ? .1 : -.1)));
    render();
    return;
} if (a === 'calculate') {
    const result = await api<{
        prior: number;
        initial: number;
        duplicate: number;
        replacement: number;
    }>('/training/sensitivity', { prior: Number(document.querySelector<HTMLInputElement>('#prior')!.value), initial_lr: Number(document.querySelector<HTMLInputElement>('#initial-lr')!.value), replacement_lr: Number(document.querySelector<HTMLInputElement>('#replacement-lr')!.value) });
    document.querySelector('#sensitivity-output')!.innerHTML = `<div class="sensitivity-cards">${[['Prior', result.prior], ['Initial evidence', result.initial], ['Duplicate report', result.duplicate], ['Corrected evidence', result.replacement]].map(([name, value]) => `<article><span>${name}</span><strong>${(Number(value) * 100).toFixed(1)}%</strong></article>`).join('')}</div><p class="small">Conditional arithmetic only. The corrected record replaces the initial likelihood factor.</p>`;
    return;
} if (a === 'tour') {
    if (workspace!.session.mode !== 'CURRENT_INVESTIGATION')
        await newMode('CURRENT_INVESTIGATION');
    tour = 0;
    tab = 'network';
    selectedSource = 'CF-AWARD';
    await fetchDetail();
    render();
    return;
} if (a === 'tour-next') {
    tour++;
    if (tour >= tourSteps.length)
        tour = -1;
    if (tour === 1)
        tab = 'timeline';
    if (tour === 2) {
        tab = 'network';
        selectedSource = workspace!.sources.some(s => s.id === 'FTS-CORRECTION') ? 'FTS-CORRECTION' : selectedSource;
        await fetchDetail();
    }
    if (tour === 3)
        tab = 'brief';
    render();
    return;
} if (a === 'tour-close') {
    tour = -1;
    render();
    return;
} if (a === 'logout') {
    await api('/auth/logout', {});
    user = null;
    sid = '';
    localStorage.removeItem('osint.session');
    loginView();
    return;
} }
function showExport(): void { const e = currentExport!; showModal(`<div class="eyebrow">IMMUTABLE AUDIT BUNDLE</div><h2>${e.state === 'verified' ? 'Drive archive verified' : 'Local archive created'}</h2><p>Your ZIP contains the template briefing, admitted source versions, review state, run records and a checksum manifest. It contains no credentials.</p><dl class="metadata"><div><dt>Archive</dt><dd class="mono">${esc(e.id)}</dd></div><div><dt>Size</dt><dd>${(e.size / 1024).toFixed(1)} KB</dd></div><div><dt>SHA-256</dt><dd class="mono">${esc(e.sha256)}</dd></div></dl><a class="button primary" href="/api/v1/exports/${encodeURIComponent(e.id)}/download" download>Download audit ZIP</a>${user!.role === 'owner' ? action('sync-export', 'Verify upload to Drive', user!.drive_status === 'DRIVE_NOT_CONNECTED' ? 'disabled' : '', '') : ''}<div class="callout ${e.state === 'verified' ? '' : 'warn'}">${e.state === 'verified' ? 'Uploaded object and manifest passed authenticated byte readback.' : 'Not saved to Drive. The local bundle is available regardless of connection status.'}</div>`); }
void boot();
