from tests.conftest import auth_headers


def test_non_admin_cannot_create_centre(client, user_token):
    resp = client.post(
        "/centres/",
        json={"name": "Rogue Lab", "location": "Nowhere"},
        headers=auth_headers(user_token),
    )
    assert resp.status_code == 403


def test_admin_can_create_centre_and_test(client, centre_and_test):
    centre, test = centre_and_test
    assert test["centre_id"] == centre["id"]
    assert test["price"] == 499.0


def test_list_centres_is_public(client, centre_and_test):
    resp = client.get("/centres/")
    assert resp.status_code == 200
    centres = resp.json()
    assert len(centres) == 1
    assert len(centres[0]["tests"]) == 1


def test_get_unknown_centre_404s(client):
    resp = client.get("/centres/does-not-exist")
    assert resp.status_code == 404


def test_add_test_to_unknown_centre_404s(client, admin_token):
    resp = client.post(
        "/centres/does-not-exist/tests/",
        json={"name": "X-Ray", "price": 999.0},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 404


def test_new_centre_and_test_appear_immediately_after_creation(client, admin_token):
    """
    The default (unfiltered, first-page) GET /centres/ and GET /tests/ responses
    are cached (see app/cache.py). This proves the cache is correctly
    invalidated on writes — a client must never see stale data right after
    creating something, whether or not Redis happens to be running.
    """
    assert client.get("/centres/").json() == []
    assert client.get("/tests/").json() == []

    centre = client.post(
        "/centres/",
        json={"name": "New Centre", "location": "Mumbai"},
        headers=auth_headers(admin_token),
    ).json()

    centres_after = client.get("/centres/").json()
    assert len(centres_after) == 1
    assert centres_after[0]["id"] == centre["id"]

    test = client.post(
        f"/centres/{centre['id']}/tests/",
        json={"name": "Lipid Panel", "price": 699.0},
        headers=auth_headers(admin_token),
    ).json()

    tests_after = client.get("/tests/").json()
    assert len(tests_after) == 1
    assert tests_after[0]["id"] == test["id"]

    # And the centre's nested `tests` list picks it up too.
    centre_detail = client.get(f"/centres/{centre['id']}").json()
    assert len(centre_detail["tests"]) == 1
