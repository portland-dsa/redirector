import os

import dns.exception
import dns.rdata
import dns.resolver
import pytest
from flask.testing import FlaskClient

# The app reads its domains at import, so set them before any test module imports it.
os.environ["TARGET_DOMAIN"] = "branch.example"
os.environ["HOST_DOMAIN"] = "chapter.example"

#: The fake DNS every test resolves against, as (name, type) -> record texts.
ZONE: dict[tuple[str, str], list[str]] = {
    # Kris set everything up right, with the link split across two TXT strings.
    ("kris.branch.example", "CNAME"): ["redirect.chapter.example."],
    ("_redirect.kris.branch.example", "TXT"): ['"https://drive.example/" "agenda"'],
    # Ralsei's CNAME is in another case; DNS names compare case-insensitively.
    ("ralsei.branch.example", "CNAME"): ["REDIRECT.Chapter.Example."],
    ("_redirect.ralsei.branch.example", "TXT"): ['"http://tea.example/"'],
    # Noelle published a link but pointed the name at the branch's own server.
    ("noelle.branch.example", "CNAME"): ["www.branch.example."],
    ("_redirect.noelle.branch.example", "TXT"): ['"https://choir.example/"'],
    # Berdly pointed the name at us and never published a link.
    ("berdly.branch.example", "CNAME"): ["redirect.chapter.example."],
    # Susie added a second link instead of replacing the first.
    ("susie.branch.example", "CNAME"): ["redirect.chapter.example."],
    ("_redirect.susie.branch.example", "TXT"): [
        '"https://a.example/"',
        '"https://b.example/"',
    ],
    # Lancer's "link" is a script.
    ("lancer.branch.example", "CNAME"): ["redirect.chapter.example."],
    ("_redirect.lancer.branch.example", "TXT"): ['"javascript:alert(1)"'],
    # Spamton runs a lookalike domain and wants our certificates and redirects for it.
    ("bigshotbranch.example", "CNAME"): ["redirect.chapter.example."],
    ("_redirect.bigshotbranch.example", "TXT"): ['"https://kromer.example/"'],
}

#: Names whose lookups never finish.
UNREACHABLE = {"queen.branch.example"}


def _resolve(name: str, rdtype: str, lifetime: float) -> list[dns.rdata.Rdata]:
    if name in UNREACHABLE:
        raise dns.exception.Timeout()
    texts = ZONE.get((name, rdtype))
    if texts is None:
        raise dns.resolver.NXDOMAIN()
    return [dns.rdata.from_text("IN", rdtype, text) for text in texts]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> FlaskClient:
    from redirector.redirector import app

    monkeypatch.setattr(dns.resolver, "resolve", _resolve)
    return app.test_client()
