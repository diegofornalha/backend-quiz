"""Rate limiter stub"""

# Flag indicando se slowapi está disponível
SLOWAPI_AVAILABLE = False

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address
    SLOWAPI_AVAILABLE = True

    _limiter = None

    def get_limiter():
        global _limiter
        if _limiter is None:
            _limiter = Limiter(key_func=get_remote_address)
        return _limiter

    limiter = get_limiter()

except ImportError:
    # SlowAPI não disponível - criar stub
    class DummyLimiter:
        def limit(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

    limiter = DummyLimiter()

    def get_limiter():
        return limiter

# Rate limits padrão
RATE_LIMITS = {
    "default": "100/minute",
    "search": "30/minute",
    "chat": "20/minute"
}
