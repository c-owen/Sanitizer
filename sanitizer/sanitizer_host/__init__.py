"""Host-side adapters: Buzz and Qt integration for Sanitizer.

Modules here may import PyQt6 and Buzz internals. Keep this layer thin — all
sanitization logic lives in the host-independent :mod:`sanitizer_core` package so it
can be tested without a running app.
"""
