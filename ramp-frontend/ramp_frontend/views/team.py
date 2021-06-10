"""Blueprint for all team functions for the RAMP frontend."""
import logging

import flask_login

from flask import (
    Blueprint,
    render_template,
    request,
    flash,
    redirect,
    url_for
)

from ramp_database.tools.frontend import is_accessible_code
from ramp_database.tools.frontend import is_accessible_event
from ramp_database.tools.user import get_team_by_name
from ramp_database.tools.team import (
        add_team, sign_up_team, leave_all_teams, get_event_team_by_user_name, add_team_member,
        get_team_members,
        respond_team_invite
)
from ramp_database.tools._query import (
    select_team_invites_by_user_name,
)
from ramp_database.model import User
from ramp_database.model import Team

from ramp_frontend import db

from .redirect import redirect_to_user

mod = Blueprint('team', __name__)
logger = logging.getLogger('RAMP-FRONTEND')

def _validate_team_request(session, event_name: str, user):
    if not is_accessible_event(session, event_name,
                               user.name):
        return redirect_to_user(
            f'{user.firstname}: no '
            f'event named "{event_name}"'
        )
    if not is_accessible_code(session, event_name, user.name):
        error_str = (f'No access to my submissions for event {event_name}. '
                     f'If you have already signed up, please wait for '
                     f'approval.')
        return redirect_to_user(error_str)

@mod.route("/events/<event_name>/team", methods=['GET', 'POST'])
@flask_login.login_required
def my_teams(event_name):
    """List the current team

    Parameters
    ----------
    event_name : str
        The name of the event.
    """
    current_user = flask_login.current_user
    res = _validate_team_request(db.session, event_name, current_user)
    if res is not None:
        return res

    if request.method == 'POST':
        team_name = request.form['new_team_name']

        team = get_team_by_name(db.session, team_name)
        if team is not None:
            flash(f"Team {team_name} already exists! Choose a different name.")
        else:
            leave_all_teams(db.session, event_name, current_user.name)
            team = add_team(db.session, team_name, current_user.name, is_individual=False)
            sign_up_team(db.session, event_name, team.name)

    event_team = get_event_team_by_user_name(
        db.session, event_name, current_user.name
    )

    team_members = get_team_members(db.session, event_team.team.name, status='accepted')
    asked_members = get_team_members(db.session, event_team.team.name, status='asked')
    # TODO: these should be only users that signed up to the event
    all_users = User.query.filter(User.id != current_user.id).all()
    team_invites = select_team_invites_by_user_name(
        db.session, event_name, current_user.name
    )

    return render_template('my_teams.html',
                           event_team=event_team,
                           team_members=team_members,
                           asked_members=asked_members,
                           team_invites=team_invites,
                           all_users=all_users,
                           msg="test")

@mod.route("/events/<event_name>/team/leave", methods=['POST'])
@flask_login.login_required
def leave_teams(event_name):
    """Leave all non individual teams

    Parameters
    ----------
    event_name : str
        The name of the event.
    """
    current_user = flask_login.current_user
    res = _validate_team_request(db.session, event_name, current_user)
    if res is not None:
        return res
    leave_all_teams(db.session, event_name, flask_login.current_user.name)
    return redirect(url_for("team.my_teams", event_name=event_name))


@mod.route("/events/<event_name>/team/add-user", methods=['POST'])
@flask_login.login_required
def add_team_members(event_name):
    """Leave all non individual teams

    Parameters
    ----------
    event_name : str
        The name of the event.
    """
    user_name_to_add = request.form['invite_user_name']

    current_user = flask_login.current_user
    res = _validate_team_request(db.session, event_name, current_user)
    if res is not None:
        return res
    event_team = get_event_team_by_user_name(
        db.session, event_name, current_user.name
    )

    user = db.session.query(User).filter_by(name=user_name_to_add).one_or_none()

    if event_team is None:
        return {'errors': [f'{user} is not signed up to {event_team.event}.']}
    errors = add_team_member(db.session, event_team.team.name, user.name)
    if errors:
        flash("\n".join(errors))
    return redirect(url_for("team.my_teams", event_name=event_name))



@mod.route("/events/<event_name>/team/invites", methods=['POST'])
@flask_login.login_required
def manage_team_invites(event_name):
    """Accept or reject team invites

    Parameters
    ----------
    event_name : str
        The name of the event.
    """
    team_id = request.form['team_id']

    current_user = flask_login.current_user
    res = _validate_team_request(db.session, event_name, current_user)
    if res is not None:
        return res
    team_id = int(team_id)

    team = db.session.query(Team).filter_by(id=team_id).one_or_none()
    respond_team_invite(db.session, current_user.name, team.name, action='accept')
    return redirect(url_for("team.my_teams", event_name=event_name))
