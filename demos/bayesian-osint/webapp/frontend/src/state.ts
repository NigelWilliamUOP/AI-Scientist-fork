type Mode = 'CURRENT_INVESTIGATION' | 'HISTORICAL_RECONSTRUCTION' | 'RECORDED_REPLAY';
type Source = {
    id: string;
    display_title: string;
    publisher: string;
    publisher_date: string | null;
    publisher_timestamp: string | null;
    date_precision: string;
    source_type: string;
    version_id: string;
    representation: string;
    origin_group: string;
    acquired_at: string | null;
    excluded: boolean;
    last_attempt: {
        state: string;
        at: string;
        error: string | null;
    } | null;
};
type Segment = {
    id: string;
    locator: string;
    text: string;
    sha256: string;
};
type Evidence = Source & {
    url: string;
    segments: Segment[];
    licence: string;
    coverage: string;
    reviewed_on: string;
    upstream_body_sha256: string | null;
    notice_id: string | null;
};
type Citation = {
    source_version_id: string;
    segment_id: string;
    quote: string;
};
type Statement = {
    text: string;
    kind: string;
    citations: Citation[];
};
type Answer = {
    statements: Statement[];
    uncertainties: string[];
    next_evidence: string[];
};
type Run = {
    id: string;
    phase: string;
    returned_model?: string;
    returned_provider?: string;
    cost: number | null;
    cost_status: string;
    started_at: string;
    state: string;
    answer?: Answer;
};
type Result = {
    kind: string;
    inference?: boolean;
    answer?: Answer;
    source_versions?: string[];
    label?: string;
    runs?: Run[];
    challenge?: Run;
    challenge_error?: string;
    sources?: {
        source_id: string;
        state: string;
        error?: string;
    }[];
    success_count?: number;
};
type Job = {
    id: string;
    state: string;
    result: Result | null;
    error: string | null;
};
type LedgerEvent = {
    id: number;
    kind: string;
    detail: string;
    at: string;
    job_id: string | null;
};
type Workspace = {
    session: {
        id: string;
        mode: Mode;
        cutoff: string | null;
        scope_revision: number;
    };
    case: {
        title: string;
        question: string;
        location: null | {
            name: string;
            lat: number;
            lon: number;
            source_url: string;
            source_quote: string;
            precision: string;
            reviewed_on: string;
        };
    };
    sources: Source[];
    graph: {
        nodes: {
            id: string;
            label: string;
            kind: string;
        }[];
        edges: {
            source: string;
            target: string;
            kind: string;
            source_version_id: string;
            locator: string;
        }[];
    };
    assessment: {
        revision: number;
        stale: boolean;
        body: {
            status: string;
            statements: Statement[];
            rationale?: string;
        };
    };
    baseline: Answer;
    events: LedgerEvent[];
    budget_committed_usd: number;
};
type User = {
    role: string;
    csrf: string;
    release: string;
    ai_status: string;
    drive_status: string;
    limits: {
        session_usd: number;
        day_usd: number;
        call_usd: number;
    };
};
type Export = {
    id: string;
    state: string;
    sha256: string;
    size: number;
    remote_id?: string | null;
};
const root = document.querySelector<HTMLDivElement>('#app')!;
const modal = document.querySelector<HTMLDialogElement>('#modal')!;
let user: User | null = null, workspace: Workspace | null = null, selectedSource: string | null = null, detail: Evidence | null = null;
let tab = 'network', filter = '', query = 'Which dates are targets rather than evidence of completed operation?', draft: Result | null = null, draftJob: string | null = null, busy = false, currentExport: Export | null = null, tour = -1, mapEnabled = false, zoom = 1;
let sid = localStorage.getItem('osint.session') || '';
const shortNames: Record<string, string> = { 'CF-AWARD': 'Equipment award', 'FTS-PIN': 'Prior information notice', 'FTS-TENDER': 'Operations tender', 'FTS-CORRECTION': 'Title correction', 'PORT-STATEMENT': 'Reported shore-power use' };
const messages: Record<string, string> = { AUTH_REQUIRED: 'Please sign in again.', AI_NOT_CONFIGURED: 'AI is not connected. Configure the server-side OpenRouter credentials before requesting a model call.', DRIVE_NOT_CONNECTED: 'The local archive is safe. Google Drive has not been connected to this app.', GOOGLE_OAUTH_APP_NOT_CONFIGURED: 'Set the Google OAuth client and token-encryption secret on the server first.', NO_ADMITTED_EVIDENCE: 'No admitted evidence remains. Reinstate a source before compiling a briefing.', STALE_REVIEW_CONFLICT: 'The evidence or accepted assessment has changed. Compile a fresh draft before review.', SOURCE_UNAVAILABLE: 'The source could not be fetched. The previous evidence is retained.', JOB_ALREADY_ACTIVE: 'Your current task is still running.', REPLAY_READ_ONLY: 'This frozen replay is read-only. Start a current investigation to make changes.', RESULT_OUTSIDE_CURRENT_SCOPE: 'This answer used evidence now excluded from your scenario. Compile a fresh brief.', MODEL_UNSUPPORTED_OR_PRICING_UNKNOWN: 'The selected endpoint has not passed the schema and pricing preflight.', LOGIN_FAILED: 'That access password was not recognised.', LOGIN_RATE_LIMITED: 'Too many login attempts. Try again after one minute.' };
function esc(v: unknown): string { return String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!)); }
function safeLink(v: string): string { try {
    const u = new URL(v);
    return u.protocol === 'https:' ? esc(u.href) : '#';
}
catch {
    return '#';
} }
function date(v: string | null): string { if (!v)
    return 'Publication date unknown'; if (/^\d{4}-\d{2}-\d{2}$/.test(v))
    return new Date(v + 'T12:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }); return new Date(v).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' }) + ' UTC'; }
function label(v: string): string { return v.toLowerCase().replaceAll('_', ' '); }
function toast(text: string, error = false): void { const el = document.querySelector<HTMLDivElement>('#toast')!; el.textContent = text; el.className = 'show' + (error ? ' error' : ''); window.setTimeout(() => { el.className = ''; }, 7000); }
async function api<T>(path: string, body?: unknown): Promise<T> { const r = await fetch('/api/v1' + path, { method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', headers: body === undefined ? {} : { 'Content-Type': 'application/json', 'X-CSRF-Token': user?.csrf || '' }, body: body === undefined ? undefined : JSON.stringify(body) }); if (!r.ok) {
    const problem = await r.json().catch(() => ({ error: 'REQUEST_FAILED' }));
    const code = typeof problem.error === 'string' ? problem.error : 'REQUEST_INVALID';
    throw new Error(messages[code] || label(code));
} return r.json() as Promise<T>; }
function icon(name: string): string { const paths: Record<string, string> = { network: 'M4 12h6m4 0h6M12 4v6m0 4v6M4 4h4v4H4zM16 4h4v4h-4zM4 16h4v4H4zM16 16h4v4h-4zM9 9h6v6H9z', map: 'm3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3zM9 3v15M15 6v15', timeline: 'M4 3v18M4 6h6m-6 6h12m-12 6h16', brief: 'M5 3h10l4 4v14H5zM14 3v5h5M8 12h8M8 16h6', refresh: 'M20 7v5h-5M4 17v-5h5M5 8a7 7 0 0 1 12-3l3 4M4 15l3 4a7 7 0 0 0 12-3', export: 'M12 3v12m-4-4 4 4 4-4M5 16v5h14v-5', close: 'm6 6 12 12M18 6 6 18', arrow: 'M5 12h14m-5-5 5 5-5 5', check: 'm5 12 4 4 10-10', settings: 'M12 3v3m0 12v3M3 12h3m12 0h3M6 6l2 2m8 8 2 2M6 18l2-2m8-8 2-2M8 12a4 4 0 1 0 8 0 4 4 0 1 0-8 0' }; return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="${paths[name] || paths.arrow}"/></svg>`; }
function action(name: string, text: string, extra = '', cls = ''): string { return `<button class="${cls}" data-action="${name}" ${extra}>${text}</button>`; }
function loginView(): void { root.innerHTML = `<main class="login-page" id="main"><section class="login-story"><div class="eyebrow">UNIVERSITY–PARTNER RESEARCH DEMONSTRATOR</div><div class="brand large"><span class="brand-mark">B</span>OSINT<span class="brand-accent">BAYES</span></div><h1>See the evidence.<br>Inspect the judgement.</h1><p>Follow a real Portsmouth investigation from public records to a briefing you can challenge.</p><div class="login-facts"><span>05 public-source records</span><span>Traceable citations</span><span>Human review gate</span></div><p class="small muted">Real source extracts are included. Live acquisition, model calls and Drive uploads each require their own verified connection.</p></section><section class="login-card"><div class="eyebrow">EVIDENCE OBSERVATORY / 0.4.1</div><h2>Open your workspace</h2><p>Sign in with the owner or reviewer password supplied by the host.</p><form id="login-form"><label for="password">Access password</label><input id="password" type="password" autocomplete="current-password" required maxlength="256"><button class="primary wide" type="submit">Enter investigation ${icon('arrow')}</button><p id="login-error" class="error-text" role="alert"></p></form><div class="rule"></div><p class="small muted">Local installation? Run <code>python scripts/run.py</code>. The launcher tells the owner where to find the generated access password.</p></section></main>`; document.querySelector<HTMLFormElement>('#login-form')!.onsubmit = async (e) => { e.preventDefault(); const field = document.querySelector<HTMLInputElement>('#password')!; try {
    await api('/auth/login', { password: field.value });
    field.value = '';
    await boot();
}
catch (err) {
    document.querySelector('#login-error')!.textContent = (err as Error).message;
} }; }
async function boot(): Promise<void> { try {
    user = await api<User>('/me');
    const sessions = await api<{
        id: string;
    }[]>('/sessions');
    if (!sessions.some(x => x.id === sid))
        sid = sessions[0]?.id || '';
    if (!sid) {
        const created = await api<{
            id: string;
        }>('/sessions', {});
        sid = created.id;
    }
    localStorage.setItem('osint.session', sid);
    await load();
    const jobs = await api<{
        id: string;
        kind: string;
        state: string;
    }[]>('/sessions/' + sid + '/jobs');
    const active = jobs.find(j => j.state === 'running' || j.state === 'queued');
    if (active) {
        void awaitJob(active.id).catch(e => toast((e as Error).message, true));
    }
    else {
        const latest = jobs.find(j => j.kind === 'question' && j.state === 'completed');
        if (latest) {
            try {
                const j = await api<Job>('/jobs/' + latest.id);
                draft = j.result;
                draftJob = j.id;
                render();
            }
            catch { /* A source withdrawal can make an old answer inadmissible. */ }
        }
    }
}
catch {
    user = null;
    loginView();
} }
async function load(): Promise<void> { workspace = await api<Workspace>('/sessions/' + sid + '/workspace'); if (!selectedSource || !workspace.sources.some(s => s.id === selectedSource && !s.excluded))
    selectedSource = workspace.sources.find(s => !s.excluded)?.id || null; await fetchDetail(); render(); }
async function fetchDetail(): Promise<void> { const source = workspace?.sources.find(s => s.id === selectedSource && !s.excluded); detail = source ? await api<Evidence>('/sessions/' + sid + '/versions/' + source.version_id) : null; }
function statusTag(text: string, tone = 'muted'): string { return `<span class="tag ${tone}">${esc(text)}</span>`; }
function sourceCards(): string { return workspace!.sources.filter(s => !filter || `${s.display_title} ${s.id} ${s.publisher}`.toLowerCase().includes(filter.toLowerCase())).map(s => `<article class="source-card ${selectedSource === s.id ? 'selected' : ''} ${s.excluded ? 'excluded' : ''}"><div class="source-heading"><span class="source-code">${esc(s.id)}</span>${statusTag(s.excluded ? 'Excluded' : s.last_attempt?.state === 'failed' ? 'Refresh failed' : s.representation === 'original_http_capture' ? 'HTTP capture' : 'Curated extract', s.excluded ? 'muted' : s.last_attempt?.state === 'failed' ? 'warn' : s.representation === 'original_http_capture' ? 'good' : 'muted')}</div><button class="source-select" data-action="select" data-id="${esc(s.id)}" ${s.excluded ? 'disabled' : ''}>${esc(shortNames[s.id] || s.display_title)}</button><div class="source-date">${esc(date(s.publisher_timestamp || s.publisher_date))}</div><div class="source-bottom"><span>${s.origin_group.includes('OPERATIONS') ? 'Shared origin: operations' : s.origin_group.includes('EQUIPMENT') ? 'Equipment contract' : 'Publisher statement'}</span><button class="exclude-toggle" data-action="exclude" data-id="${esc(s.id)}" aria-label="${s.excluded ? 'Reinstate' : 'Exclude'} ${esc(s.id)}" ${workspace!.session.mode === 'RECORDED_REPLAY' ? 'disabled' : ''}>${s.excluded ? '+' : '−'}</button></div></article>`).join('') || '<p class="muted">No matching sources.</p>'; }
