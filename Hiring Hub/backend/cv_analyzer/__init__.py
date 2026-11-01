# Use the OS certificate store (needed behind corporate HTTPS-inspecting proxies).
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass