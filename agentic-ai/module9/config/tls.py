# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
"""
module9/config/tls.py
======================
TLS trust-store bootstrap for the Databricks connection.

Reuses the Module 7 helper, which points OpenSSL at certifi's CA bundle via
SSL_CERT_FILE and SSL_CERT_DIR. This is needed because some Python builds,
most commonly the python.org macOS framework build, ship without a
populated system CA store. Without it, the Databricks SQL connector fails
certificate verification against a perfectly valid DigiCert chain, and its
internal retries turn that failure into a long hang rather than a clear
error.

Confluent is unaffected because librdkafka resolves its own CA store.
"""
from __future__ import annotations

import os


def ensure_secure_ca() -> str | None:
    """Point OpenSSL at certifi's CA bundle. Returns the path in effect.

    Delegates to module7.config.tls when available so both modules share one
    implementation, with a local fallback for standalone module9 checkouts.
    Never weakens verification: an operator-set SSL_CERT_FILE always wins.
    """
    try:
        from module7.config.tls import ensure_secure_ca as _module7_ensure

        return _module7_ensure()
    except ImportError:
        pass

    try:
        import certifi
    except ImportError:
        return None

    ca_path = os.environ.get("SSL_CERT_FILE") or certifi.where()
    os.environ.setdefault("SSL_CERT_FILE", ca_path)
    os.environ.setdefault("SSL_CERT_DIR", os.path.dirname(ca_path))
    return ca_path
