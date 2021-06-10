import datetime

from sqlalchemy import Enum
from sqlalchemy import Column
from sqlalchemy import String
from sqlalchemy import Integer
from sqlalchemy import Boolean
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy.orm import backref
from sqlalchemy.orm import relationship

from sqlalchemy import sql

from .base import Model

__all__ = ['Team', 'UserTeam']


class Team(Model):
    """Team table.

    Parameters
    ----------
    name : str
        The name of the team.
    admin : :class:`ramp_database.model.User`
        The admin user of the team.

    Attributes
    ----------
    id : int
        The ID of the table row.
    name : str
        The name of the team.
    admin_id : int
        The ID of the admin user.
    admin : :class:`ramp_database.model.User`
        The admin user instance.
    initiator_id : int
        The ID of the team asking for merging.
    initiator : :class:`ramp_database.model.Team`
        The team instance asking for merging.
    acceptor_id : int
        The ID of the team accepting the merging.
    acceptor : :class:`ramp_database.model.Team`
        The team instance accepting the merging.
    team_events : :class:`ramp_database.model.EventTeam`
        A back-reference to the events to which the team is enroll.
    """
    __tablename__ = 'teams'

    id = Column(Integer, primary_key=True)
    name = Column(String(20), nullable=False, unique=True)

    admin_id = Column(Integer, ForeignKey('users.id'))
    admin = relationship('User',
                         backref=backref('admined_teams',
                                         cascade="all, delete"))

    creation_timestamp = Column(DateTime, nullable=False)

    def __init__(self, name, admin):
        self.name = name
        self.admin = admin
        self.creation_timestamp = datetime.datetime.utcnow()

    def __str__(self):
        return 'Team({})'.format(self.name)

    def __repr__(self):
        return ('Team(name={}, admin_name={})'
                .format(self.name, self.admin.name))

    def is_individual_team(self, user_name: str) -> bool:
        """Check whether it's an individual team name"""
        return self.name == user_name


class UserTeam(Model):
    """User to team many to many association table

    Parameters
    ----------
    user_id : int
        The ID of the user.
    team_id : int
        The ID of the team.
    status: str
        The relationship status. One of "asked", "accepted", "admin".

    Attributes
    ----------
    id : int
        The ID of the table row.
    update_timestamp : datetime
        Last updated timestamp.
    """
    __tablename__ = 'user_teams'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    user = relationship('User',
                        backref=backref('user_user_team',
                                        cascade="all, delete"))
    team_id = Column(Integer, ForeignKey('teams.id'))
    team = relationship('Team',
                        backref=backref('team_user_team',
                                        cascade="all, delete"))
    status = Column(
        Enum('asked', 'accepted', 'admin', name='status'),
        default='asked'
    )
    is_active = Column(Boolean, default=True, nullable=False)
    update_timestamp = Column(DateTime, onupdate=sql.func.now(),
                              server_default=sql.func.now())

    def __init__(self, user_id, team_id, status='asked', is_active=False):
        self.user_id = user_id
        self.team_id = team_id
        self.status = status
        self.is_active = is_active
