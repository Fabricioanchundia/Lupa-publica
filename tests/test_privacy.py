import pytest

from lupa_publica.privacy import KEY_ENV, MissingKeyError, load_key, pseudonymize

KEY = bytes.fromhex("ab" * 32)


def test_pseudonym_is_stable_for_the_same_input() -> None:
    assert pseudonymize("1712345678001", KEY) == pseudonymize("1712345678001", KEY)


def test_pseudonym_differs_between_people_and_keys() -> None:
    a = pseudonymize("1712345678001", KEY)

    assert a != pseudonymize("1712345679001", KEY)
    assert a != pseudonymize("1712345678001", bytes.fromhex("cd" * 32))


def test_pseudonym_does_not_contain_the_identifier() -> None:
    result = pseudonymize("1712345678001", KEY)

    assert "1712345678" not in result
    assert len(result) == 64


def test_load_key_reads_hex_from_environment() -> None:
    assert load_key({KEY_ENV: "ab" * 32}) == KEY


@pytest.mark.parametrize("value", ["", "   ", "not-hex", "ab" * 16])
def test_load_key_rejects_missing_or_weak_keys(value: str) -> None:
    with pytest.raises(MissingKeyError):
        load_key({KEY_ENV: value})
