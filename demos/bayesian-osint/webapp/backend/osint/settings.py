from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]

@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv('APP_DATA_DIR', str(ROOT / '.runtime'))))
    public_url: str = field(default_factory=lambda: os.getenv('APP_PUBLIC_URL', 'http://127.0.0.1:8000').rstrip('/'))
    production: bool = field(default_factory=lambda: os.getenv('APP_ENV', 'local') == 'production')
    owner_password: str = field(default_factory=lambda: os.getenv('APP_OWNER_PASSWORD', ''))
    reviewer_password: str = field(default_factory=lambda: os.getenv('APP_REVIEWER_PASSWORD', ''))
    release: str = field(default_factory=lambda: os.getenv('APP_RELEASE', '0.4.1-local'))
    ai_provider: str = field(default_factory=lambda: os.getenv('AI_PROVIDER', ''))
    ai_key: str = field(default_factory=lambda: os.getenv('OPENROUTER_API_KEY', ''))
    ai_model: str = field(default_factory=lambda: os.getenv('OPENROUTER_MODEL', ''))
    ai_providers: str = field(default_factory=lambda: os.getenv('OPENROUTER_PROVIDERS', ''))
    allow_paid: bool = field(default_factory=lambda: os.getenv('ALLOW_PAID_AI', 'false').lower() == 'true')
    session_budget: float = field(default_factory=lambda: float(os.getenv('AI_SESSION_BUDGET_USD', '5')))
    daily_budget: float = field(default_factory=lambda: float(os.getenv('AI_DAILY_BUDGET_USD', '20')))
    call_ceiling: float = field(default_factory=lambda: float(os.getenv('AI_CALL_CEILING_USD', '0.25')))
    google_client_id: str = field(default_factory=lambda: os.getenv('GOOGLE_CLIENT_ID', ''))
    google_client_secret: str = field(default_factory=lambda: os.getenv('GOOGLE_CLIENT_SECRET', ''))
    encryption_key: str = field(default_factory=lambda: os.getenv('TOKEN_ENCRYPTION_KEY', ''))
    start_worker: bool = True
    session_ttl: int = 8 * 3600

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir).resolve()
        p = urlparse(self.public_url)
        if p.scheme not in ('http', 'https') or not p.netloc or p.path not in ('', '/') or p.query or p.fragment or p.username or p.password:
            raise ValueError('APP_PUBLIC_URL must be an origin, without path/query')
        if self.production and (p.scheme != 'https' or len(self.owner_password) < 16):
            raise ValueError('Production requires HTTPS and an owner password of at least 16 characters')
        if not self.production and p.hostname not in ('localhost', '127.0.0.1', '::1'):
            raise ValueError('Non-production mode is restricted to loopback origins')
        if self.reviewer_password and (len(self.reviewer_password) < 16 or self.reviewer_password == self.owner_password):
            raise ValueError('Reviewer password must be distinct and at least 16 characters')
        for n in (self.session_budget, self.daily_budget, self.call_ceiling):
            if not 0 < n <= 1000:
                raise ValueError('Budget must be positive and bounded')

    @property
    def ai_status(self) -> str:
        if self.ai_provider != 'openrouter' or not self.ai_key:
            return 'AI_NOT_CONFIGURED'
        if not self.ai_model or '/' not in self.ai_model or 'latest' in self.ai_model.lower():
            return 'MODEL_NOT_CONFIGURED'
        if not self.allow_paid:
            return 'PAID_AI_NOT_AUTHORISED'
        if not self.ai_providers:
            return 'PROVIDER_NOT_CONFIGURED'
        return 'CONFIGURED_NOT_LIVE_VERIFIED'
