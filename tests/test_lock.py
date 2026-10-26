from pathlib import Path

import pytest

from lupa_publica.lock import AlreadyRunningError, exclusive_lock


def test_second_run_is_refused_while_the_first_holds_the_lock(tmp_path: Path) -> None:
    lock = tmp_path / ".lupa.lock"

    with exclusive_lock(lock):
        with pytest.raises(AlreadyRunningError, match="already running"):
            with exclusive_lock(lock):
                pass


def test_lock_is_released_when_the_run_ends(tmp_path: Path) -> None:
    lock = tmp_path / ".lupa.lock"

    with exclusive_lock(lock):
        pass
    with exclusive_lock(lock):
        pass


def test_lock_is_released_even_if_the_run_fails(tmp_path: Path) -> None:
    lock = tmp_path / ".lupa.lock"

    with pytest.raises(ValueError), exclusive_lock(lock):
        raise ValueError("boom")
    with exclusive_lock(lock):
        pass


def test_lock_file_records_the_process_id(tmp_path: Path) -> None:
    lock = tmp_path / ".lupa.lock"

    with exclusive_lock(lock):
        assert lock.read_text().strip().isdigit()
