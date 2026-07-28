import datetime

import app.config
import grpc
import jwt


def make_token(role: str = "admin", user_id: int = 1) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(minutes=15),
    }
    return jwt.encode(
        payload,
        app.config.settings.jwt_secret_key,
        algorithm=app.config.settings.jwt_algorithm,
    )


ADMIN_HEADERS = {"Authorization": f"Bearer {make_token(role='admin')}"}
USER_HEADERS = {"Authorization": f"Bearer {make_token(role='user')}"}


class MockRpcError(grpc.RpcError):
    def __init__(self, code, details):
        super().__init__()
        self._code = code
        self._details = details

    def code(self):
        return self._code

    def details(self):
        return self._details
