from app.database import normalise_url


def test_render_style_urls_use_psycopg3():
    assert normalise_url("postgres://u:p@host:5432/db") == "postgresql+psycopg://u:p@host:5432/db"
    assert normalise_url("postgresql://u:p@host/db") == "postgresql+psycopg://u:p@host/db"


def test_explicit_and_sqlite_urls_are_left_alone():
    assert normalise_url("postgresql+psycopg://u:p@host/db") == "postgresql+psycopg://u:p@host/db"
    assert normalise_url("sqlite:///data/kundali.db") == "sqlite:///data/kundali.db"
