"""
RAMP backend API

Methods for interacting with the database
"""
from __future__ import print_function, absolute_import

import os

import numpy as np

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine.url import URL

from .model import Base
from .query import select_submissions_by_state, select_submissions_by_id
from .config import STATES, UnknownStateError


__all__ = [
    'get_submissions',
    'get_submission_by_id',
    'set_submission_state',
    'get_submission_state',
    'set_predictions',
    'score_submission',
]


def get_submissions(config, event_name, state='new'):
    """
    Retrieve a list of submissions and their associated files
    depending on their current status

    Parameters
    ----------
    config : dict
        configuration
    event_name : str
        name of the RAMP event
    state : str, optional
        state of the requested submissions (default is 'new')

    Returns
    -------
    List of tuples (int, List[str]) :
        (submission_id, [path to submission files on the db])

    Raises
    ------
    ValueError :
        when mandatory connexion parameters are missing from config
    UnknownStateError :
        when the requested state does not exist in the database

    """
    if state not in STATES:
        raise UnknownStateError("Unrecognized state : '{}'".format(state))

    # Create database url
    db_url = URL(**config['sqlalchemy'])
    db = create_engine(db_url)

    # Create a configured "Session" class
    Session = sessionmaker(db)

    # Link the relational model to the database
    Base.metadata.create_all(db)

    # Connect to the dabase and perform action
    with db.connect() as conn:
        session = Session(bind=conn)

        submissions = select_submissions_by_state(session, event_name, state)

        if not submissions:
            return []

        subids = [submission.id for submission in submissions]
        subfiles = [submission.files for submission in submissions]
        filenames = [[f.path for f in files] for files in subfiles]

    return list(zip(subids, filenames))


def get_submission_by_id(config, submission_id):
    """
    Get a `Submission` instance given a submission id

    Parameters
    ----------

    config : dict
        configuration

    submission_id : int
        submission id

    Returns
    -------

    `Submission` instance
    """
    # Create database url
    db_url = URL(**config['sqlalchemy'])
    db = create_engine(db_url)

    # Create a configured "Session" class
    Session = sessionmaker(db)

    # Link the relational model to the database
    Base.metadata.create_all(db)

    # Connect to the dabase and perform action
    with db.connect() as conn:
        session = Session(bind=conn)
        submission = select_submissions_by_id(session, submission_id)
        # force event name and team name to be cached
        submission.event.name
        submission.team.name
    return submission


def set_submission_state(config, submission_id, state):
    """
    Modify the state of a submission in the RAMP database

    Parameters
    ----------
    config : dict
        configuration
    submission_id : int
        id of the requested submission
    state : str
        new state of the submission

    Raises
    ------
    ValueError :
        when mandatory connexion parameters are missing from config
    UnknownStateError :
        when the requested state does not exist in the database

    """
    if state not in STATES:
        raise UnknownStateError("Unrecognized state : '{}'".format(state))

    # Create database url
    db_url = URL(**config['sqlalchemy'])
    db = create_engine(db_url)

    # Create a configured "Session" class
    Session = sessionmaker(db)

    # Link the relational model to the database
    Base.metadata.create_all(db)

    # Connect to the dabase and perform action
    with db.connect() as conn:
        session = Session(bind=conn)

        submission = select_submissions_by_id(session, submission_id)
        submission.set_state(state)

        session.commit()


def get_submission_state(config, submission_id):
    """
    Modify the state of a submission in the RAMP database

    Parameters
    ----------
    config : dict
        configuration
    submission_id : int
        id of the requested submission

    Raises
    ------
    ValueError :
        when mandatory connexion parameters are missing from config
    UnknownStateError :
        when the requested state does not exist in the database

    """
    # Create database url
    db_url = URL(**config['sqlalchemy'])
    db = create_engine(db_url)

    # Create a configured "Session" class
    Session = sessionmaker(db)

    # Link the relational model to the database
    Base.metadata.create_all(db)

    # Connect to the dabase and perform action
    with db.connect() as conn:
        session = Session(bind=conn)
        submission = select_submissions_by_id(session, submission_id)
    return submission.state


def set_predictions(config, submission_id, prediction_path, ext='npy'):
    """
    Insert predictions in the database after training/testing

    Parameters
    ----------
    config : dict
        configuration
    submission_id : int
        id of the related submission
    prediction_path : str
        local path where predictions are saved.
        Should end with 'training_output'.
    ext : {'npy', 'npz', 'csv'}, optional
        extension of the saved prediction extension file (default is 'npy')

    Raises
    ------
    NotImplementedError :
        when the extension cannot be read properly

    """
    # Create database url
    db_url = URL(**config['sqlalchemy'])
    db = create_engine(db_url)

    # Create a configured "Session" class
    Session = sessionmaker(db)

    # Link the relational model to the database
    Base.metadata.create_all(db)

    # Connect to the dabase and perform action
    with db.connect() as conn:
        session = Session(bind=conn)

        submission = select_submissions_by_id(session, submission_id)

        for fold_id, cv_fold in enumerate(submission.on_cv_folds):
            cv_fold.full_train_y_pred = _load_submission(
                prediction_path, fold_id, 'train', ext)
            cv_fold.test_y_pred = _load_submission(
                prediction_path, fold_id, 'test', ext)
            cv_fold.valid_time = 0.0
            cv_fold.test_time = 0.0
            cv_fold.state = 'tested'
            session.commit()

        submission.state = 'tested'
        session.commit()


def _load_submission(path, fold_id, typ, ext):
    """
    Prediction loader method

    Parameters
    ----------
    path : str
        local path where predictions are saved
    fold_id : int
        id of the current CV fold
    type : {'train', 'test'}
        type of prediction
    ext : {'npy', 'npz', 'csv'}
        extension of the saved prediction extension file

    Raises
    ------
    ValueError :
        when typ is neither 'train' nor 'test'
    NotImplementedError :
        when the extension cannot be read properly

    """
    pred_file = os.path.join(path,
                             'fold_{}'.format(fold_id),
                             'y_pred_{}.{}'.format(typ, ext))

    if typ not in ['train', 'test']:
        raise ValueError("Only 'train' or 'test' are expected for arg 'typ'")

    if ext.lower() in ['npy', 'npz']:
        return np.load(pred_file)['y_pred']
    elif ext.lower() == 'csv':
        return np.loadfromtxt(pred_file)
    else:
        return NotImplementedError("No reader implemented for extension {ext}"
                                   .format(ext))


def score_submission(config, submission_id):
    # Create database url
    db_url = URL(**config['sqlalchemy'])
    db = create_engine(db_url)

    # Create a configured "Session" class
    Session = sessionmaker(db)

    # Link the relational model to the database
    Base.metadata.create_all(db)

    # Connect to the dabase and perform action
    with db.connect() as conn:
        session = Session(bind=conn)

        submission = select_submissions_by_id(session, submission_id)
        if submission.state != 'tested':
            raise ValueError('submission state must be "tested" to score')

        # We are conservative:
        # only score if all stages (train, test, validation)
        # were completed. submission_on_cv_fold compute scores can be called
        # manually if needed for submission in various error states.
        for submission_on_cv_fold in submission.on_cv_folds:
            submission_on_cv_fold.compute_train_scores()
            submission_on_cv_fold.compute_valid_scores()
            submission_on_cv_fold.compute_test_scores()
            submission_on_cv_fold.state = 'scored'
        session.commit()
        submission.compute_test_score_cv_bag()
        submission.compute_valid_score_cv_bag()
        # Means and stds were constructed on demand by fetching fold times.
        # It was slow because submission_on_folds contain also possibly large
        # predictions. If postgres solves this issue (which can be tested on
        # the mean and std scores on the private leaderbord), the
        # corresponding columns (which are now redundant) can be deleted in
        # Submission and this computation can also be deleted.
        submission.train_time_cv_mean = np.mean(
            [ts.train_time for ts in submission.on_cv_folds])
        submission.valid_time_cv_mean = np.mean(
            [ts.valid_time for ts in submission.on_cv_folds])
        submission.test_time_cv_mean = np.mean(
            [ts.test_time for ts in submission.on_cv_folds])
        submission.train_time_cv_std = np.std(
            [ts.train_time for ts in submission.on_cv_folds])
        submission.valid_time_cv_std = np.std(
            [ts.valid_time for ts in submission.on_cv_folds])
        submission.test_time_cv_std = np.std(
            [ts.test_time for ts in submission.on_cv_folds])
        session.commit()
        submission.state = 'scored'
        session.commit()
