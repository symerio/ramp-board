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

from ramp_database.tools.user import add_user
from ramp_database.tools.event import add_event
from ramp_database.tools.event import delete_event
from ramp_database.tools.team import sign_up_team

from ramp_frontend import create_app
from ramp_frontend.testing import login_scope


@pytest.fixture(scope='module')
def client_session(database_connection):
    database_config = read_config(database_config_template())
    ramp_config = ramp_config_template()
    try:
        deployment_dir = create_toy_db(database_config, ramp_config)
        flask_config = generate_flask_config(database_config)
        app = create_app(flask_config)
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        with session_scope(database_config['sqlalchemy']) as session:
            yield app.test_client(), session
    finally:
        shutil.rmtree(deployment_dir, ignore_errors=True)
        try:
            # In case of failure we should close the global flask engine
            from ramp_frontend import db as db_flask
            db_flask.session.close()
        except RuntimeError:
            pass
        db, _ = setup_db(database_config['sqlalchemy'])
        Model.metadata.drop_all(db)


@pytest.fixture(scope='function')
def makedrop_event(client_session):
    _, session = client_session
    add_event(session, 'iris', 'iris_test_4event', 'iris_test_4event',
              'starting_kit', '/tmp/databoard_test/submissions',
              is_public=True)
    yield
    delete_event(session, 'iris_test_4event')


def test_team_get(client_session):
    client, session = client_session

    add_user(session, 'new_user', 'new_user', 'new_user',
             'new_user', 'new_user', access_level='user')
    add_event(session, 'iris', 'iris_new_event', 'new_event', 'starting_kit',
              '/tmp/databoard_test/submissions', is_public=True)

    # user signed up and approved for the event
    sign_up_team(session, 'iris_new_event', 'new_user')
    with login_scope(client, 'new_user', 'new_user') as client:
        rv = client.get('/events/iris_new_event/team')
        assert rv.status_code == 200
        assert b'My teams' in rv.data
