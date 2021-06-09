import logging
import os

from ..model import EventTeam, Team, UserTeam, Event, User

from .submission import add_submission

from ._query import select_event_by_name
from ._query import select_event_team_by_name
from ._query import select_team_by_name
from ._query import select_user_by_name

logger = logging.getLogger('RAMP-DATABASE')


def add_team(session, team_name: str, user_name: str) -> Team:
    """Create a new team

    Note that the behavior will change depending on whether it's
    an individual team (i.e. team_name == user_name) or not.

    Parameters
    ----------
    session : :class:`sqlalchemy.orm.Session`
        The session to directly perform the operation on the database.
    event_name : str
        The RAMP event name.
    user_name : str
        The name of admin user

    Returns
    -------
    team : :class:`ramp_database.model.Team`
        The created team.
    """
    user = select_user_by_name(session, user_name)
    team = Team(name=team_name, admin=user)
    session.add(team)
    session.commit()

    is_individual_team = (team_name == user.name)
    if not is_individual_team:
        user_team = UserTeam(team_id=team.id, user_id=user.id, status='accepted')
        session.add(user_team)

    session.commit()

    return team


def leave_all_teams(session, event_name: str, user_name: str):
    """Leave all teams for a given user and event (except for invididual teams)

    Note that the behavior will change depending on whether it's
    an individual team (i.e. team_name == user_name) or not.

    Parameters
    ----------
    session : :class:`sqlalchemy.orm.Session`
        The session to directly perform the operation on the database.
    event_name : str
        The RAMP event name.
    user_name : str
        The name of admin user
    """
    (session.query(UserTeam)
     .filter(UserTeam.status == 'accepted')
     .filter(UserTeam.user_id == User.id)
     .filter(User.name == user_name)
     .filter(UserTeam.team_id == Team.id)
     .filter(EventTeam.team_id == Team.id)
     .filter(EventTeam.event_id == Event.id)
     .filter(Event.name == event_name)
     .delete(synchronize_session='fetch'))
    session.commit()


def ask_sign_up_team(session, event_name, team_name):
    """Register a team to a RAMP event without approving.

    :class:`ramp_database.model.EventTeam` as an attribute ``approved`` set to
    ``False`` by default. Executing this function only create the relationship
    in the database.

    Parameters
    ----------
    session : :class:`sqlalchemy.orm.Session`
        The session to directly perform the operation on the database.
    event_name : str
        The RAMP event name.
    team_name : str
        The name of the team.

    Returns
    -------
    event : :class:`ramp_database.model.Event`
        The queried Event.
    team : :class:`ramp_database.model.Team`
        The queried team.
    event_team : :class:`ramp_database.model.EventTeam`
        The relationship event-team table.
    """
    event = select_event_by_name(session, event_name)
    team = select_team_by_name(session, team_name)
    event_team = select_event_team_by_name(session, event_name, team_name)
    if event_team is None:
        event_team = EventTeam(event=event, team=team)
        session.add(event_team)
        session.commit()
    return event, team, event_team


def sign_up_team(session, event_name, team_name):
    """Register a team to a RAMP event and submit the starting kit.

    Parameters
    ----------
    session : :class:`sqlalchemy.orm.Session`
        The session to directly perform the operation on the database.
    event_name : str
        The RAMP event name.
    team_name : str
        The name of the team.
    """
    event, team, event_team = ask_sign_up_team(session, event_name, team_name)
    # setup the sandbox
    path_sandbox_submission = os.path.join(event.problem.path_ramp_kit,
                                           'submissions',
                                           event.ramp_sandbox_name)
    submission_name = event.ramp_sandbox_name
    submission = add_submission(session, event_name, team_name,
                                submission_name, path_sandbox_submission)
    logger.info('Copying the submission files into the deployment folder')
    logger.info('Adding {}'.format(submission))
    event_team.approved = True
    session.commit()


def delete_event_team(session, event_name, team_name):
    """Delete a team from an RAMP event.

    Parameters
    ----------
    session : :class:`sqlalchemy.orm.Session`
        The session to directly perform the operation on the database.
    event_name : str
        The RAMP event name.
    team_name : str
        The name of the team.
    """
    event, team, event_team = ask_sign_up_team(session, event_name, team_name)
    session.delete(event_team)
    session.commit()


def get_event_team_by_name(session, event_name, user_name):
    """Get the event/team given an event and a user.

    Parameters
    ----------
    session : :class:`sqlalchemy.orm.Session`
        The session to directly perform the operation on the database.
    event_name : str
        The RAMP event name.
    team_name : str
        The name of the team.

    Returns
    -------
    event_team : :class:`ramp_database.model.EventTeam`
        The event/team instance queried.
    """
    return select_event_team_by_name(session, event_name, user_name)
