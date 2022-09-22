from itertools import product
from packaging import version

import numpy as np
import pandas as pd

from ..model.event import Event
from ..model.event import EventTeam
from ..model.submission import Submission
from ..model.team import Team

from .team import get_event_team_by_name

from .submission import get_bagged_scores
from .submission import get_scores
from .submission import get_submission_max_ram
from .submission import get_time


width = -1 if version.Version(pd.__version__) < version.Version("1.0.0") else None
pd.set_option("display.max_colwidth", width)


def _compute_leaderboard(
    session, submissions, leaderboard_type, event_name, with_links=True
):
    """Format the leaderboard.

    Parameters
    ----------
    session : :class:`sqlalchemy.orm.Session`
        The session to directly perform the operation on the database.
    submissions : list of :class:`ramp_database.model.Submission`
        The submission to report in the leaderboard.
    leaderboard_type : {'public', 'private'}
        The type of leaderboard to built.
    event_name : str
        The name of the event.
    with_links : bool
        Whether or not the submission name should be clickable.

    Returns
    -------
    leaderboard : dataframe
        The leaderboard in a dataframe format.
    """
    record_score = []
    event = session.query(Event).filter_by(name=event_name).one()
    for sub in submissions:
        # take only max n bag
        df = (
            get_bagged_scores(session, sub.id)
            .reset_index(drop=True)
            .max(axis=0)
            .to_frame()
            .T
        )

        if leaderboard_type == "private":
            df["submission ID"] = sub.basename.replace("submission_", "")
        df["team"] = sub.team.name
        df["submission"] = sub.name_with_link if with_links else sub.name
        df["submitted at (UTC)"] = pd.Timestamp(sub.submission_timestamp)
        record_score.append(df)

    # stack all the records
    df = pd.concat(record_score, axis=0, ignore_index=True, sort=False)

    # keep only second precision for the time stamp
    df["submitted at (UTC)"] = df["submitted at (UTC)"].astype("datetime64[s]")
    df.columns.name = None

    df = df.sort_values(by="submitted at (UTC)", ascending=False)
    return df


def _compute_competition_leaderboard(
    session, submissions, leaderboard_type, event_name
):
    """Format the competition leaderboard.

    Parameters
    ----------
    session : :class:`sqlalchemy.orm.Session`
        The session to directly perform the operation on the database.
    submissions : list of :class:`ramp_database.model.Submission`
        The submission to report in the leaderboard.
    leaderboard_type : {'public', 'private'}
        The type of leaderboard to built.
    event_name : str
        The name of the event.

    Returns
    -------
    competition_leaderboard : dataframe
        The competition leaderboard in a dataframe format.
    """
    event = session.query(Event).filter_by(name=event_name).one()
    score_type = event.get_official_score_type(session)
    score_name = event.official_score_name

    private_leaderboard = _compute_leaderboard(
        session, submissions, "private", event_name, with_links=False
    )

    # select best submission for each team
    best_df = private_leaderboard.groupby("team").min().reset_index()
    best_df = best_df.sort_values(by="Total cost")
    best_df.insert(0, 'rank', np.arange(1, best_df.shape[0]+1, dtype=np.int))

    return best_df


def get_leaderboard_all_info(session, event_name):
    """Get the info on the leaderboard for all the submissions.

    Result is returned as a pandas Dataframe

    If the submissions are in the state 'new' they will not be taken into
    account

    Parameters
    ----------
    session : :class:`sqlalchemy.orm.Session`
        The session to directly perform the operation on the database.
    event_name : str
        The event name.

    Returns
    -------
    leaderboard : DataFrame
        The dataframe of the current leaderboard with the information on the
        private and public score per each successfully finished submission.
    """
    update_all_user_leaderboards(session, event_name, new_only=False)

    submissions = (
        session.query(Submission)
        .filter(Event.name == event_name)
        .filter(Event.id == EventTeam.event_id)
        .filter(EventTeam.id == Submission.event_team_id)
        .filter(Submission.state == "scored")
    ).all()
    if not submissions:
        return pd.DataFrame()

    private_leaderboard = _compute_leaderboard(
        session, submissions, "private", event_name, with_links=False
    )
    private_leaderboard = private_leaderboard.set_index(["team", "submission"])
    public_leaderboard = _compute_leaderboard(
        session, submissions, "public", event_name, with_links=False
    )
    public_leaderboard = public_leaderboard.set_index(["team", "submission"])

    # join private and public data
    joined_leaderboard = private_leaderboard.join(
        public_leaderboard,
        on=["team", "submission"],
        lsuffix="-private",
        rsuffix="-public",
    )
    return joined_leaderboard


def get_leaderboard(
    session, leaderboard_type, event_name, user_name=None, with_links=True
):
    r"""Get a leaderboard.

    Parameters
    ----------
    session : :class:`sqlalchemy.orm.Session`
        The session to directly perform the operation on the database.
    leaderboard_type : {'public', 'private', 'failed', 'new', \
            'public competition', 'private competition'}
        The type of leaderboard to generate.
    event_name : str
        The event name.
    user_name : None or str, default is None
        The user name. If None, scores from all users will be queried. This
        parameter is discarded when requesting the competition leaderboard.
    with_links : bool, default is True
        Whether or not the submission name should be clickable.

    Returns
    -------
    leaderboard : str
        The leaderboard in HTML format.
    """
    q = (
        session.query(Submission)
        .filter(Event.id == EventTeam.event_id)
        .filter(Team.id == EventTeam.team_id)
        .filter(EventTeam.id == Submission.event_team_id)
        .filter(Event.name == event_name)
    )
    if user_name is not None:
        q = q.filter(Team.name == user_name)
    submissions = q.all()

    submission_filter = {
        "public": "is_public_leaderboard",
        "private": "is_private_leaderboard",
        "failed": "is_error",
        "new": "is_new",
        "public competition": "is_in_competition",
        "private competition": "is_in_competition",
    }

    submissions = [
        sub
        for sub in submissions
        if (getattr(sub, submission_filter[leaderboard_type]) and sub.is_not_sandbox)
    ]

    if not submissions:
        return None

    if leaderboard_type in ["public", "private"]:
        df = _compute_leaderboard(
            session,
            submissions,
            leaderboard_type,
            event_name,
            with_links=with_links,
        )
    elif leaderboard_type in ["new", "failed"]:
        if leaderboard_type == "new":
            columns = [
                "team",
                "submission",
                "submitted at (UTC)",
                "state",
                "waiting list",
            ]
        else:
            columns = ["team", "submission", "submitted at (UTC)", "error"]

        # we rely on the zip function ignore the submission state if the error
        # column was not appended
        data = [
            {
                column: value
                for column, value in zip(
                    columns,
                    [
                        sub.event_team.team.name,
                        sub.name_with_link,
                        pd.Timestamp(sub.submission_timestamp),
                        (
                            sub.state_with_link
                            if leaderboard_type == "failed"
                            else sub.state
                        ),
                        (
                            "#{}".format(sub.queue_position)
                            if sub.queue_position != -1
                            else ""
                        ),
                    ],
                )
            }
            for sub in submissions
        ]
        df = pd.DataFrame(data, columns=columns)
    else:
        # make some extra filtering
        submissions = [sub for sub in submissions if sub.is_public_leaderboard]
        if not submissions:
            return None
        competition_type = "public" if "public" in leaderboard_type else "private"
        df = _compute_competition_leaderboard(
            session, submissions, competition_type, event_name
        )

    df_html = df.to_html(
        escape=False, index=False, max_cols=None, max_rows=None, justify="left"
    )
    df_html = "<thead> {} </tbody>".format(
        df_html.split("<thead>")[1].split("</tbody>")[0]
    )
    return df_html


def update_leaderboards(session, event_name, new_only=False):
    """Update the leaderboards for a given event.

    Parameters
    ----------
    session : :class:`sqlalchemy.orm.Session`
        The session to directly perform the operation on the database.
    event_name : str
        The event name.
    new_only : bool, default is False
        Whether or not to update the whole leaderboards or only the new
        submissions. You can turn this option to True when adding a new
        submission in the database.
    """
    event = session.query(Event).filter_by(name=event_name).one()
    if not new_only:
        event.private_leaderboard_html = get_leaderboard(session, "private", event_name)
        event.public_leaderboard_html_with_links = get_leaderboard(
            session, "public", event_name
        )
        event.public_leaderboard_html_no_links = get_leaderboard(
            session, "public", event_name, with_links=False
        )
        event.failed_leaderboard_html = get_leaderboard(session, "failed", event_name)
        event.public_competition_leaderboard_html = get_leaderboard(
            session, "public competition", event_name
        )
        event.private_competition_leaderboard_html = get_leaderboard(
            session, "private competition", event_name
        )
    event.new_leaderboard_html = get_leaderboard(session, "new", event_name)
    session.commit()


def update_user_leaderboards(session, event_name, user_name, new_only=False):
    """Update the of a user leaderboards for a given event.

    Parameters
    ----------
    session : :class:`sqlalchemy.orm.Session`
        The session to directly perform the operation on the database.
    event_name : str
        The event name.
    user_name : str
        The user name. If None, scores from all users will be queried.
    new_only : bool, default is False
        Whether or not to update the whole leaderboards or only the new
        submissions. You can turn this option to True when adding a new
        submission in the database.
    """
    event_team = get_event_team_by_name(session, event_name, user_name)
    if not new_only:
        event_team.leaderboard_html = get_leaderboard(
            session, "public", event_name, user_name
        )
        event_team.failed_leaderboard_html = get_leaderboard(
            session, "failed", event_name, user_name
        )
    event_team.new_leaderboard_html = get_leaderboard(
        session, "new", event_name, user_name
    )
    session.commit()


def update_all_user_leaderboards(session, event_name, new_only=False):
    """Update the leaderboards for all users for a given event.

    Parameters
    ----------
    session : :class:`sqlalchemy.orm.Session`
        The session to directly perform the operation on the database.
    event_name : str
        The event name.
    new_only : bool, default is False
        Whether or not to update the whole leaderboards or only the new
        submissions. You can turn this option to True when adding a new
        submission in the database.
    """
    event = session.query(Event).filter_by(name=event_name).one()
    event_teams = session.query(EventTeam).filter_by(event=event).all()
    for event_team in event_teams:
        user_name = event_team.team.name
        if not new_only:
            event_team.leaderboard_html = get_leaderboard(
                session, "public", event_name, user_name
            )
            event_team.failed_leaderboard_html = get_leaderboard(
                session, "failed", event_name, user_name
            )
        event_team.new_leaderboard_html = get_leaderboard(
            session, "new", event_name, user_name
        )
    session.commit()
