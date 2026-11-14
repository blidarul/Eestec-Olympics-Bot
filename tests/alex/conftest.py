import pytest


@pytest.fixture(autouse=True)
def _reset_chat_monitor():
    """chat/ keeps one process-wide monitor of the opponent chat (a shorter list = new match): reset it after each test
    so that tests of other folders do not see our chat lines."""
    yield
    try:
        import chat
        chat.wrap_untrusted([])
    except Exception:
        pass
