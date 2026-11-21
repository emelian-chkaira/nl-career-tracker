"""SSRF guard for user-supplied hosts/URLs (custom AI endpoints, mail servers). Private/loopback targets are refused unless CAREERS_ALLOW_PRIVATE_HOSTS=true."""
import ipaddress, socket
from urllib.parse import urlparse
from fastapi import HTTPException
from .config import settings


def check_host(host: str) -> None:
    host = (host or "").strip()
    if not host: raise HTTPException(400, "host is required")
    if settings.allow_private_hosts: return
    try: infos = socket.getaddrinfo(host, None)
    except OSError: raise HTTPException(400, f"cannot resolve {host}")
    for i in infos:
        ip = ipaddress.ip_address(i[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise HTTPException(400, "private or local addresses are not allowed on this server")


def check_url(url: str) -> str:
    u = urlparse(url or "")
    if u.scheme not in ("http", "https") or not u.hostname: raise HTTPException(400, "base URL must start with http:// or https://")
    check_host(u.hostname); return url.rstrip("/")
