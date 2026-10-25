import pytest
from flask.testing import FlaskClient


@pytest.mark.parametrize(
    ("name", "ask", "status", "location"),
    [
        ("kris.branch.example", 200, 302, "https://drive.example/agenda"),
        ("Ralsei.Branch.Example", 200, 302, "http://tea.example/"),
        ("noelle.branch.example", 403, 404, None),
        ("berdly.branch.example", 403, 404, None),
        ("susie.branch.example", 403, 404, None),
        ("lancer.branch.example", 403, 404, None),
        ("bigshotbranch.example", 403, 404, None),
        ("queen.branch.example", 503, 503, None),
    ],
)
def test_serves_only_configured_names(
    client: FlaskClient, name: str, ask: int, status: int, location: str | None
) -> None:
    assert client.get("/ask", query_string={"domain": name}).status_code == ask

    response = client.get("/", headers={"Host": name})
    assert response.status_code == status
    assert response.headers.get("Location") == location


def test_ask_without_a_domain_is_a_bad_request(client: FlaskClient) -> None:
    assert client.get("/ask").status_code == 400
