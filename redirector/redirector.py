"""Redirect a branch's subdomains to the links its DNS publishes.

A branch points `<name>.<target>` at `redirect.<host>` with a CNAME, and publishes the
link as a TXT record at `_redirect.<name>.<target>`. Caddy asks `/ask` before it issues
a certificate for a name, then proxies every request for that name here.
"""

import logging
import os
from urllib.parse import urlsplit

import dns.exception
import dns.name
import dns.rdata
import dns.resolver
from dns.rdtypes.ANY.CNAME import CNAME
from dns.rdtypes.ANY.TXT import TXT
from flask import Flask, abort, redirect, request
from werkzeug.wrappers import Response

log = logging.getLogger(__name__)

#: The branch's domain. Only names beneath it get a certificate or a redirect.
ZONE = os.environ["TARGET_DOMAIN"].lower()
#: The name every served name must CNAME to.
CNAME_TARGET = dns.name.from_text(f"redirect.{os.environ['HOST_DOMAIN']}")
#: Seconds one lookup may take, retries included. A first TLS handshake waits on it.
LOOKUP_LIFETIME = 3.0

app = Flask(__name__)


def _lookup(name: str, rdtype: str) -> list[dns.rdata.Rdata]:
    """The `rdtype` records at `name`, empty when it has none.

    A missing name or record is an ordinary answer. A lookup that cannot finish (a
    timeout, no reachable nameserver) raises, so an outage never reads as "unset".
    """
    try:
        return list(dns.resolver.resolve(name, rdtype, lifetime=LOOKUP_LIFETIME))
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return []


def _link(record: bytes) -> str | None:
    """The record's text, if it is a printable ASCII absolute http(s) URL."""
    if not record.isascii():
        return None
    url = record.decode("ascii")
    try:
        parts = urlsplit(url)
    except ValueError:
        return None
    if url.isprintable() and parts.scheme in ("http", "https") and parts.netloc:
        return url
    return None


def destination(name: str) -> str | None:
    """Where `name` redirects, or None when this service does not serve it.

    A served name sits beneath the branch's domain, CNAMEs to us, and publishes exactly
    one TXT record holding an absolute http(s) URL. The zone check comes first and is
    what keeps this from redirecting for anyone else's records: Caddy does not hold the
    Host header to the certificate's name.
    """
    name = name.lower()
    if not name.endswith(f".{ZONE}"):
        return None
    cnames = [r.target for r in _lookup(name, "CNAME") if isinstance(r, CNAME)]
    if CNAME_TARGET not in cnames:
        return None
    records = [
        b"".join(r.strings)
        for r in _lookup(f"_redirect.{name}", "TXT")
        if isinstance(r, TXT)
    ]
    match records:
        case [record]:
            url = _link(record)
            if url is None:
                log.warning("%s: redirect record is not an absolute http(s) URL", name)
            return url
        case []:
            return None
        case _:
            log.warning("%s: %d redirect records, expected one", name, len(records))
            return None


@app.get("/ask")
def ask() -> tuple[str, int]:
    """Caddy's on-demand TLS gate: a 2xx lets it issue a certificate for `domain`."""
    name = request.args.get("domain")
    if name is None:
        abort(400)
    return ("", 200) if destination(name) is not None else ("", 403)


@app.get("/")
def go() -> Response:
    """Redirect the requested name to its link.

    Caddy rewrites every public path to `/` (deploy/caddy/sites/redirector.caddy), so
    this one route serves them all and `/ask` stays out of public reach.
    """
    url = destination(request.host.split(":")[0])
    if url is None:
        abort(404)
    return redirect(url, code=302)


@app.errorhandler(dns.exception.DNSException)
def lookup_failed(e: dns.exception.DNSException) -> tuple[str, int]:
    """An unfinished lookup is an outage, not an unknown name. Any non-2xx on `/ask`
    refuses the certificate, so this answers both routes."""
    log.warning("%s: DNS lookup failed: %s", request.url, e)
    return "", 503
