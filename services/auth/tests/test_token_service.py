import pytest
import jwt
import datetime
import hashlib
import app.services.token_service as token_service


class TestCreateAccessToken:
    def test_create_access_token_returns_string(self):
        token = token_service.create_access_token(1, "user")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_access_token_payload_sub(self):
        import app.config
        token = token_service.create_access_token(42, "user")
        payload = jwt.decode(
            token,
            app.config.settings.jwt_secret_key,
            algorithms=[app.config.settings.jwt_algorithm]
        )
        assert payload["sub"] == "42"

    def test_create_access_token_payload_role(self):
        import app.config
        token = token_service.create_access_token(1, "admin")
        payload = jwt.decode(
            token,
            app.config.settings.jwt_secret_key,
            algorithms=[app.config.settings.jwt_algorithm]
        )
        assert payload["role"] == "admin"

    def test_create_access_token_payload_type(self):
        import app.config
        token = token_service.create_access_token(1, "user")
        payload = jwt.decode(
            token,
            app.config.settings.jwt_secret_key,
            algorithms=[app.config.settings.jwt_algorithm]
        )
        assert payload["type"] == "access"

    def test_create_access_token_payload_expiry_present(self):
        import app.config
        token = token_service.create_access_token(1, "user")
        payload = jwt.decode(
            token,
            app.config.settings.jwt_secret_key,
            algorithms=[app.config.settings.jwt_algorithm]
        )
        assert "exp" in payload
        assert "iat" in payload

    def test_create_access_token_different_users_differ(self):
        token1 = token_service.create_access_token(1, "user")
        token2 = token_service.create_access_token(2, "user")
        assert token1 != token2


class TestCreateRefreshToken:
    def test_create_refresh_token_returns_tuple(self):
        result = token_service.create_refresh_token()
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_create_refresh_token_raw_is_string(self):
        raw, _ = token_service.create_refresh_token()
        assert isinstance(raw, str)

    def test_create_refresh_token_hash_is_sha256(self):
        raw, hash_val = token_service.create_refresh_token()
        assert isinstance(hash_val, str)
        assert len(hash_val) == 64

    def test_create_refresh_token_hash_matches_raw(self):
        raw, hash_val = token_service.create_refresh_token()
        expected_hash = hashlib.sha256(raw.encode()).hexdigest()
        assert hash_val == expected_hash

    def test_create_refresh_token_raw_and_hash_differ(self):
        raw, hash_val = token_service.create_refresh_token()
        assert raw != hash_val

    def test_create_refresh_token_unique_each_call(self):
        raw1, hash1 = token_service.create_refresh_token()
        raw2, hash2 = token_service.create_refresh_token()
        assert raw1 != raw2
        assert hash1 != hash2


class TestDecodeAccessToken:
    def test_decode_access_token_valid(self):
        token = token_service.create_access_token(5, "user")
        payload = token_service.decode_access_token(token)
        assert payload["sub"] == "5"
        assert payload["role"] == "user"

    def test_decode_access_token_expired_raises(self):
        import app.config
        payload = {
            "sub": "1",
            "role": "user",
            "exp": datetime.datetime.utcnow() - datetime.timedelta(seconds=1),
            "iat": datetime.datetime.utcnow() - datetime.timedelta(minutes=15),
            "type": "access"
        }
        expired_token = jwt.encode(
            payload,
            app.config.settings.jwt_secret_key,
            algorithm=app.config.settings.jwt_algorithm
        )
        with pytest.raises(jwt.ExpiredSignatureError):
            token_service.decode_access_token(expired_token)

    def test_decode_access_token_wrong_secret_raises(self):
        wrong_secret_token = jwt.encode({"sub": "1", "role": "user"}, "wrong-secret", algorithm="HS256")
        with pytest.raises(jwt.InvalidTokenError):
            token_service.decode_access_token(wrong_secret_token)

    def test_decode_access_token_malformed_raises(self):
        with pytest.raises(jwt.InvalidTokenError):
            token_service.decode_access_token("not.a.valid.token")


class TestHashToken:
    def test_hash_token_returns_string(self):
        result = token_service.hash_token("any-raw-token")
        assert isinstance(result, str)

    def test_hash_token_length_is_64(self):
        result = token_service.hash_token("any-raw-token")
        assert len(result) == 64

    def test_hash_token_deterministic(self):
        raw = "my-test-token"
        hash1 = token_service.hash_token(raw)
        hash2 = token_service.hash_token(raw)
        assert hash1 == hash2

    def test_hash_token_different_inputs_differ(self):
        hash1 = token_service.hash_token("token-a")
        hash2 = token_service.hash_token("token-b")
        assert hash1 != hash2

    def test_hash_token_matches_sha256(self):
        raw = "test-token-value"
        expected = hashlib.sha256(raw.encode()).hexdigest()
        assert token_service.hash_token(raw) == expected
