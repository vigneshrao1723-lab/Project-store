"""Security audit A6: a maximum password length (input validation)."""

from app.extensions import db
from app.models import User


def test_a6_overlong_password_is_rejected(client):
    r = client.post("/register", data={"name": "A", "email": "long@example.com", "password": "p" * 5000})
    assert db.session.scalar(db.select(User).where(User.email == "long@example.com")) is None, \
        "a 5000 character password was accepted; each login would feed it to scrypt (cheap CPU denial of service)"
