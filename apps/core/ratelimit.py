import time
from functools import wraps
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render


def get_client_ip(request):
    """
    Safely extract the client IP address from the request headers.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
    return ip


def check_rate_limit(key, limit, period):
    """
    Sliding window in-memory/cache rate limiter.
    Returns (is_limited: bool, retry_after_seconds: int).
    """
    now = time.time()
    cutoff = now - period

    cache_key = f"ratelimit:{key}"
    timestamps = cache.get(cache_key, [])

    # Filter timestamps within the active period
    valid_timestamps = [ts for ts in timestamps if ts > cutoff]

    if len(valid_timestamps) >= limit:
        oldest = min(valid_timestamps)
        retry_after = int(period - (now - oldest)) + 1
        return True, max(1, retry_after)

    # Append current timestamp and save back to cache
    valid_timestamps.append(now)
    cache.set(cache_key, valid_timestamps, timeout=period + 10)
    return False, 0


def ratelimit(key_prefix='rl', limit=10, period=60, block=True, methods=('POST', 'GET')):
    """
    Rate limiting decorator for Django view functions and CBVs.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            # Check if current method is subject to rate limiting
            if request.method in methods:
                ip = get_client_ip(request)
                rate_key = f"{key_prefix}:{ip}"
                is_limited, retry_after = check_rate_limit(rate_key, limit=limit, period=period)

                if is_limited and block:
                    # Check if request is AJAX or JSON
                    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', ''):
                        response = JsonResponse({
                            'error': 'Too many requests. Please try again later.',
                            'retry_after': retry_after
                        }, status=429)
                    else:
                        response = HttpResponse(
                            f"<h1>429 Too Many Requests</h1><p>Rate limit exceeded. Please try again in {retry_after} seconds.</p>",
                            status=429,
                            content_type="text/html; charset=utf-8"
                        )
                    response['Retry-After'] = str(retry_after)
                    return response

            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
