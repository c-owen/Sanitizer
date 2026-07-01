"""Host-side adapters: Buzz and Qt integration for Cloak.

Modules here may import PyQt6 and Buzz internals. Keep this layer thin — all
sanitization logic lives in the host-independent :mod:`cloak_core` package so it
can be tested without a running app.
"""
