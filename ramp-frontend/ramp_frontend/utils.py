"""
The :mod:`ramp_frontend.utils` provides utilities to ease sending email.
"""

import logging

from flask_mail import Message

from ramp_frontend import mail

logger = logging.getLogger('RAMP-FRONTEND')


def body_formatter_user(user):
    """Create the body of an email using the user information.

    Parameters
    ----------
    user : :class:`ramp_database.model.User`
        The user profile.

    Returns
    -------
    body : str
        The email body.
    """
    body = f"""
    user = {user.name}
    name = {user.firstname} {user.lastname}
    email = {user.email}
    """
    if user.university is not None:
        body += (f"university = {user.university.name} "
                 f"({user.university.country})\n")
    body += f"graduation year = {user.graduation_year}"

    return body


def send_mail(to, subject, body):
    """Send email using Flask Mail.

    Parameters
    ----------
    to : str
        The email address of the recipient.
    subject : str
        The subject of the email.
    body : str
        The body of the email.
    """
    try:
        msg = Message(subject)
        msg.body = body
        msg.add_recipient(to)
        mail.send(msg)
    except Exception as e:
        logger.error('Mailing error: {}'.format(e))
