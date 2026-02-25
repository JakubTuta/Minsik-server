import json
import logging
import typing

import redis

logger = logging.getLogger(__name__)

_REDIS_JOB_STATE_KEY = "dump_import_state"
_REDIS_JOB_STATE_TTL = 604800


def get_job_state(redis_client: redis.Redis) -> typing.Optional[dict]:
    try:
        data = redis_client.get(_REDIS_JOB_STATE_KEY)
        if data:
            decoded = data.decode("utf-8") if isinstance(data, bytes) else str(data)
            return json.loads(decoded)
    except Exception:
        pass
    return None


def save_job_state(redis_client: redis.Redis, state: dict) -> None:
    try:
        redis_client.set(
            _REDIS_JOB_STATE_KEY,
            json.dumps(state),
            ex=_REDIS_JOB_STATE_TTL,
        )
    except Exception:
        pass


def clear_job_state(redis_client: redis.Redis) -> None:
    try:
        redis_client.delete(_REDIS_JOB_STATE_KEY)
    except Exception:
        pass
