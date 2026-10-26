import pytest

from lupa_publica import main


def test_main_runs(capsys: pytest.CaptureFixture[str]) -> None:
    main()
    assert "lupa-publica" in capsys.readouterr().out
