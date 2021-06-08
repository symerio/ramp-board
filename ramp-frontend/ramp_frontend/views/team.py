"""Blueprint for all team functions for the RAMP frontend."""
import logging

import flask_login

from flask import Blueprint
from flask import render_template

from ramp_database.tools.frontend import is_accessible_code
from ramp_database.tools.frontend import is_accessible_event
from ramp_database.tools.team import get_event_team_by_name
from ramp_database.model import User

from ramp_frontend import db

from .redirect import redirect_to_user

mod = Blueprint('team', __name__)
logger = logging.getLogger('RAMP-FRONTEND')


@mod.route("/events/<event_name>/team", methods=['GET'])
@flask_login.login_required
def my_teams(event_name):
    """List the current team

    Parameters
    ----------
    event_name : str
        The name of the event.
    """
    if not is_accessible_event(db.session, event_name,
                               flask_login.current_user.name):
        return redirect_to_user(
            f'{flask_login.current_user.firstname}: no '
            f'event named "{event_name}"'
        )
    if not is_accessible_code(db.session, event_name,
                              flask_login.current_user.name):
        error_str = (f'No access to my submissions for event {event_name}. '
                     f'If you have already signed up, please wait for '
                     f'approval.')
        return redirect_to_user(error_str)

    # Doesn't work if team mergers are allowed
    event_team = get_event_team_by_name(db.session, event_name,
                                        flask_login.current_user.name)
    team_users = [event_team.team.admin]
    # TODO: these should be only users that signed up to the event
    all_users = User.query.filter(User.id != flask_login.current_user.id).all()

    return render_template('my_teams.html',
                           event_team=event_team,
                           team_users=team_users,
                           all_users=all_users)
