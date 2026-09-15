"""URL validation to prevent SSRF attacks.

Validates URLs against an allowlist of permitted TikTok/Douyin hosts
and blocks requests to private/metadata IP ranges.
"""

import ipaddress
import socket
from typing import Set
from urllib.parse import urlparse

# Allowlisted hosts for TikTok and Douyin platforms
ALLOWED_HOSTS: Set[str] = {
    "tiktok.com",
    "www.tiktok.com",
    "m.tiktok.com",
    "vt.tiktok.com",
    "vm.tiktok.com",
    "douyin.com",
    "www.douyin.com",
    "m.douyin.com",
    "v.douyin.com",
    "iesdouyin.com",
    "www.iesdouyin.com",
    "aweme.snssdk.com",
    "snssdk.com",
}

# Private / link-local / metadata ranges (RFC 1918, RFC 3927, RFC 5737, link-local)
BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),       # loopback
    ipaddress.ip_network("10.0.0.0/8"),         # private
    ipaddress.ip_network("172.16.0.0/12"),      # private
    ipaddress.ip_network("192.168.0.0/16"),     # private
    ipaddress.ip_network("169.254.0.0/16"),     # link-local (AWS/cloud metadata)
    ipaddress.ip_network("100.64.0.0/10"),      # carrier-grade NAT / cloud metadata
    ipaddress.ip_network("0.0.0.0/8"),          # current host
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),           # IPv6 unique-local
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
]


class URLValidationError(ValueError):
    """Raised when a URL fails SSRF validation."""
    pass


def _resolve_and_block(hostname: str) -> None:
    """Resolve hostname to IPs and block any private/metadata addresses."""
    try:
        addrinfos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return
    for family, _, _, _, sockaddr in addrinfos:
        try:
            addr = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            continue
        for net in BLOCKED_NETWORKS:
            if addr in net:
                raise URLValidationError(
                    f"Hostname '{hostname}' resolves to blocked address {addr}"
                )


def validate_url(url: str, allowed_hosts: Set[str] = None) -> str:
    """Validate URL for SSRF safety (strict allowlist). Returns URL if valid."""
    if allowed_hosts is None:
        allowed_hosts = ALLOWED_HOSTS
    if not isinstance(url, str) or not url.strip():
        raise URLValidationError("URL must be a non-empty string")
    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise URLValidationError(f"Invalid URL: {e}")
    if parsed.scheme not in ("http", "https"):
        raise URLValidationError(
            f"URL scheme '{parsed.scheme}' not allowed; only http/https permitted"
        )
    hostname = parsed.hostname
    if not hostname:
        raise URLValidationError("URL has no hostname")
    hostname = hostname.lower().strip()
    host_allowed = (
        hostname in allowed_hosts
        or any(hostname == h or hostname.endswith("." + h) for h in allowed_hosts)
    )
    if not host_allowed:
        raise URLValidationError(
            f"Host '{hostname}' is not in the allowed hosts list"
        )
    _resolve_and_block(hostname)
    return url


def validate_stream_url(url: str) -> str:
    """Validate a CDN/media stream URL (relaxed — no host allowlist).

    CDN hosts (e.g. *.tiktokcdn.com, *.pstatp.com) change frequently, so
    this only enforces http/https scheme + private/metadata IP blocking.
    """
    if not isinstance(url, str) or not url.strip():
        raise URLValidationError("URL must be a non-empty string")
    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception as e:
        raise URLValidationError(f"Invalid URL: {e}")
    if parsed.scheme not in ("http", "https"):
        raise URLValidationError(
            f"URL scheme '{parsed.scheme}' not allowed; only http/https permitted"
        )
    hostname = parsed.hostname
    if not hostname:
        raise URLValidationError("URL has no hostname")
    _resolve_and_block(hostname)
    return url
