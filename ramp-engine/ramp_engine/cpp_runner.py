import logging
import sys
import os
import shutil
from datetime import datetime
import subprocess

from .base import _get_traceback
from .conda import _conda_info_envs, _get_conda_env_path
from .local import CondaEnvWorker

logger = logging.getLogger("RAMP-WORKER")


class CppCondaEnvWorker(CondaEnvWorker):
    """Local worker which uses conda environment to dispatch submission.

    Parameters
    ----------
    config : dict
        Configuration dictionary to set the worker. The following parameter
        should be set:

        * 'conda_env': the name of the conda environment to use. If not
          specified, the base environment will be used.
        * 'kit_dir': path to the directory of the RAMP kit;
        * 'data_dir': path to the directory of the data;
        * 'submissions_dir': path to the directory containing the
          submissions;
        * `logs_dir`: path to the directory where the log of the
          submission will be stored;
        * `predictions_dir`: path to the directory where the
          predictions of the submission will be stored.
        * 'timeout': timeout after a given number of seconds when
          running the worker. If not provided, a default of 7200
          is used.
    submission : str
        Name of the RAMP submission to be handle by the worker.

    Attributes
    ----------
    status : str
        The status of the worker. It should be one of the following state:

            * 'initialized': the worker has been instanciated.
            * 'setup': the worker has been set up.
            * 'error': setup failed / training couldn't be started
            * 'running': the worker is training the submission.
            * 'finished': the worker finished to train the submission.
            * 'collected': the results of the training have been collected.
    """

    def __init__(self, config, submission):
        super().__init__(config=config, submission=submission)

    def setup(self):
        """Set up the worker.

        The worker will find the path to the conda environment to use using
        the configuration passed when instantiating the worker.
        """
        # sanity check for the configuration variable
        for required_param in (
            "kit_dir",
            "data_dir",
            "submissions_dir",
            "logs_dir",
            "predictions_dir",
        ):
            self._check_config_name(self.config, required_param)
        # find the path to the conda environment
        env_name = self.config.get("conda_env", "base")
        conda_info = _conda_info_envs()

        self._python_bin_path = _get_conda_env_path(conda_info, env_name, self)

        super().setup()

    def teardown(self):
        """Remove the predictions stores within the submission."""
        if self.status not in ("collected", "retry"):
            raise ValueError("Collect the results before to kill the worker.")
        output_training_dir = os.path.join(
            self.config["kit_dir"],
            "submissions",
            self.submission,
            "training_output",
        )
        if os.path.exists(output_training_dir):
            shutil.rmtree(output_training_dir)
        super().teardown()

    def launch_submission(self):
        """Launch the submission.

        Basically, it comes to run ``ramp_test_submission`` using the conda
        environment given in the configuration. The submission is launched in
        a subprocess to free to not lock the Python main process.
        """
        if self.status == "running":
            raise ValueError(
                "Wait that the submission is processed before to " "launch a new one."
            )
        self._log_dir = os.path.join(self.config["logs_dir"], self.submission)
        os.makedirs(self._log_dir, exist_ok=True)
        self._log_file = open(os.path.join(self._log_dir, "log"), "wb+")
        submission_dir = os.path.join(
            self.config["submissions_dir"],
            self.submission,
        )
        output_dir = os.path.join(submission_dir, "training_output")
        os.makedirs(output_dir, exist_ok=True)
        bin_path = os.path.join(submission_dir, "main")
        INCLUDE_DIR = os.path.join(self.config["data_dir"], "include", "cpp")
        DATA_DIR = os.path.join(self.config["data_dir"], "data", "secret")

        subprocess.check_call(
            [
                "gcc",
                os.path.join(submission_dir, "main.cpp"),
                f"-I{INCLUDE_DIR}",
                "-lstdc++",
                "-O3",
                "-o",
                bin_path,
            ],
        )

        self._proc = subprocess.Popen(
            [
                bin_path,
            ],
            stdout=open(os.path.join(output_dir, "case0.ans"), "wb+"),
            stderr=self._log_file,
            stdin=open(os.path.join(DATA_DIR, "case0.in"), "rb"),
        )

        self._start_date = datetime.utcnow()
        self.status = "running"

    def collect_results(self):
        """Collect the results after that the submission is completed.

        Be aware that calling ``collect_results()`` before that the submission
        finished will lock the Python main process awaiting for the submission
        to be processed. Use ``worker.status`` to know the status of the worker
        beforehand.
        """
        if self.status == "initialized":
            raise ValueError(
                "The worker has not been setup and no submission "
                "was launched. Call the method setup() and "
                "launch_submission() before to collect the "
                "results."
            )
        elif self.status == "setup":
            raise ValueError(
                "No submission was launched. Call the method "
                "launch_submission() and then try again to "
                "collect the results."
            )
        if self.status in ["finished", "running", "timeout"]:
            # communicate() will wait for the process to be completed
            self._proc.communicate()
            self._log_file.close()
            with open(os.path.join(self._log_dir, "log"), "rb") as f:
                log_output = f.read()
            error_msg = _get_traceback(log_output.decode("utf-8"))
            if self.status == "timeout":
                error_msg += "\nWorker killed due to timeout after {}s.".format(
                    self.timeout
                )
            if self.status == "timeout":
                returncode = 124
            else:
                returncode = self._proc.returncode
            pred_dir = os.path.join(self.config["predictions_dir"], self.submission)
            output_training_dir = os.path.join(
                self.config["submissions_dir"],
                self.submission,
                "training_output",
            )
            if os.path.exists(pred_dir):
                shutil.rmtree(pred_dir)
            if returncode:
                if os.path.exists(output_training_dir):
                    shutil.rmtree(output_training_dir)
                self.status = "collected"
                return (returncode, error_msg)

            # scoring with the judger for now using a custom scoring function
            sys.path.append(
                os.path.join(self.config["data_dir"], "output_validators", "judger")
            )
            from data import OutputData

            output_data = OutputData.from_file(
                os.path.join(output_training_dir, "case0.ans")
            )
            # Just some fake score for now
            score = (
                output_data.deviceNum
                + sum(output_data.regionIndexs)
                + output_data.stepNum
            )
            with open(os.path.join(output_training_dir, "score.txt"), "w") as fh:
                fh.write(str(score))

            # copy the predictions into the disk
            # no need to create the directory, it will be handle by copytree
            shutil.copytree(output_training_dir, pred_dir)
            self.status = "collected"
            return (returncode, error_msg)
