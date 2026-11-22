from app.config import Settings


def test_defaults_load_without_env():
    s = Settings(_env_file=None)
    assert s.daily_limit == 200
    assert s.rate_limit == "10/minute"
