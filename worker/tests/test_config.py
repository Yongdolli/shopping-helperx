"""Actions 처럼 secret 이 빈 문자열로 들어와도 설정이 크래시하지 않는다."""
import importlib


def test_empty_env_falls_back_to_default(monkeypatch):
    for k in ("SMTP_PORT", "THRESHOLD_PCT", "WINDOW_DAYS", "SUPABASE_URL", "DIGEST"):
        monkeypatch.setenv(k, "")
    import worker.config as cfg
    importlib.reload(cfg)
    s = cfg.Settings()
    assert s.smtp_port == 587 and s.threshold_pct == 10 and s.window_days == 90 and not s.use_supabase and s.digest is True
