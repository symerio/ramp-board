import shutil

import pytest

from ramp_utils import generate_flask_config
from ramp_utils import read_config
from ramp_utils.testing import database_config_template
from ramp_utils.testing import ramp_config_template

from ramp_database.model import Model
from ramp_database.testing import create_toy_db
from ramp_database.utils import setup_db
from ramp_database.utils import session_scope

from ramp_database.tools.user import add_user, delete_user
from ramp_database.tools.event import add_event
from ramp_database.tools.event import delete_event
from ramp_database.tools.team import sign_up_team
from ramp_database.tools._query import select_event_team_by_user_name

from ramp_frontend import create_app
from ramp_frontend.testing import login_scope


@pytest.fixture(scope="module")
def client_session(database_connection):
    database_config = read_config(database_config_template())
    ramp_config = ramp_config_template()
    try:
        deployment_dir = create_toy_db(database_config, ramp_config)
        flask_config = generate_flask_config(database_config)
        app = create_app(flask_config)
        app.config["TESTING"] = True
        app.config["WTF_CSRF_ENABLED"] = False
        with session_scope(database_config["sqlalchemy"]) as session:
            yield app.test_client(), session
    finally:
        shutil.rmtree(deployment_dir, ignore_errors=True)
        try:
            # In case of failure we should close the global flask engine
            from ramp_frontend import db as db_flask

            db_flask.session.close()
        except RuntimeError:
            pass
        db, _ = setup_db(database_config["sqlalchemy"])
        Model.metadata.drop_all(db)


@pytest.fixture(scope="function")
def makedrop_event(client_session):
    _, session = client_session
    add_event(
        session,
        "iris",
        "iris_new_event2",
        "iris_new_event2",
        "starting_kit",
        "/tmp/databoard_test/submissions",
        is_public=True,
    )
    yield "iris_new_event2"
    delete_event(session, "iris_new_event2")


@pytest.fixture(scope="function")
def makedrop_user(client_session):
    _, session = client_session
    add_user(
        session,
        "new_user",
        "new_user",
        "new_user",
        "new_user",
        "new_user",
        access_level="user",
    )
    yield "new_user"
    delete_user(session, "new_user")


@pytest.mark.parametrize(
    "url, mode",
    [
        ("/events/{event_name}/team", "GET"),
        ("/events/{event_name}/team", "POST"),
        ("/events/{event_name}/team/leave", "POST"),
        ("/events/{event_name}/team/add-user", "POST"),
        ("/events/{event_name}/team/invites", "POST"),
    ],
)
def test_team_access(client_session, makedrop_event, makedrop_user, url, mode):
    client, session = client_session
    event_name = makedrop_event
    user_name = makedrop_user
    if mode == "GET":
        func = client.get
    else:
        func = client.post

    # Unauthenticated users are redirected to /login
    rv = func(url.format(event_name=event_name))
    assert rv.status_code == 302
    assert "/login" in rv.location

    # Logged in users, for non existing events get redirected to /problems with
    # a flash message
    with login_scope(client, user_name, user_name) as client:
        rv = func(url.format(event_name="non-existing-event"))
        assert "/problems" in rv.location
        assert rv.status_code == 302

    # Users not signed up to the request get redirected to /problems with a
    # flash message
    with login_scope(client, user_name, user_name) as client:
        rv = func(url.format(event_name="boston_housing"))
        assert "/problems" in rv.location
        assert rv.status_code == 302


def test_team_get(client_session, makedrop_event, makedrop_user):
    client, session = client_session
    event_name = makedrop_event
    user_name = makedrop_user

    # user signed up and approved for the event
    sign_up_team(session, event_name, user_name)
    with login_scope(client, user_name, user_name) as client:
        rv = client.get(f"/events/{event_name}/team")
        assert rv.status_code == 200
        assert b"My teams" in rv.data


def test_leave_teams(client_session, makedrop_event, makedrop_user):
    client, session = client_session
    event_name = makedrop_event
    user_name = makedrop_user

    # user signed up and approved for the event
    sign_up_team(session, event_name, user_name)
    with login_scope(client, user_name, user_name) as client:
        rv = client.post(f"/events/{event_name}/team/leave")
        assert rv.status_code == 302
        assert rv.location.endswith(f"/events/{event_name}/team")

    # The user is still associated to an individual team
    event_team = select_event_team_by_user_name(session, event_name, user_name)
    assert event_team.team.is_individual
