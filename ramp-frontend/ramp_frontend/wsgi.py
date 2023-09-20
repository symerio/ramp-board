from ramp_utils import generate_flask_config
from ramp_utils import read_config
import os

from ramp_frontend import create_app


def make_app(config_file):
    """Create the RAMP Flask app and register the views.

    Parameters
    ----------
    config : dict
        The Flask configuration generated with
        :func:`ramp_utils.generate_flask_config`.

    Returns
    -------
    app : Flask
        The Flask app created.
    """
    try:
        import sentry_sdk
        if "SENTRY_DSN" in os.environ:
            sentry_sdk.init(
                dsn=os.environ['SENTRY_DSN'],
                # Set traces_sample_rate to 1.0 to capture 100%
                # of transactions for performance monitoring.
                # We recommend adjusting this value in production.
                traces_sample_rate=0.5
            )
    except ImportError:
        pass
    config = read_config(config_file)
    flask_config = generate_flask_config(config)
    app = create_app(flask_config)

    return app
