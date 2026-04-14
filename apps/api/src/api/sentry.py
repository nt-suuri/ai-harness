import os

import sentry_sdk


def init_sentry() -> bool:
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return False
    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=0.1,
        environment=os.environ.get("ENV", "local"),
        release=os.environ.get("FLY_RELEASE_VERSION", "dev"),
    )
    return True
