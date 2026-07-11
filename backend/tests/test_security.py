from app.core.security import hash_password, verify_password


def test_hash_password_produces_argon2_hash() -> None:
    password_hash = hash_password("correcthorsebattery")

    assert password_hash.startswith("$argon2id$")
    assert password_hash != "correcthorsebattery"


def test_verify_password_accepts_correct_password() -> None:
    password_hash = hash_password("correcthorsebattery")

    assert verify_password("correcthorsebattery", password_hash) is True


def test_verify_password_rejects_wrong_password() -> None:
    password_hash = hash_password("correcthorsebattery")

    assert verify_password("wrongpassword", password_hash) is False


def test_verify_password_rejects_malformed_hash() -> None:
    assert verify_password("anything", "not-a-real-hash") is False
