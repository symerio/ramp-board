import logging
import sys
import os
import shutil
from datetime import datetime
import time
import subprocess
from pathlib import Path

from .base import _get_traceback
from .conda import _conda_info_envs, _get_conda_env_path
from .local import CondaEnvWorker

logger = logging.getLogger("RAMP-WORKER")


COMPILATION_ERROR = 1220
RUNTIME_ERROR = 1221
SCORING_ERROR = 1222


def get_conda_cmd(cmd: list[str], options: list[str] = None, memory="10m") -> list[str]:

    if options is None:
        options = []
    cmd_full = (
        [
            "docker",
            "run",
            "-i",
            "--rm",
            "--network",
            "none",
            "-v",
            "/home/ubuntu/miniforge3/:/home/ubuntu/miniforge3/:ro",
            "-v",
            "/etc/passwd:/etc/passwd:ro",
            "-v",
            "/etc/group:/etc/group:ro",
        ]
        + options
        + ["-m", memory, "ubuntu:kinetic-20220830"]
        + cmd
    )
    return cmd_full


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

    def is_cpp_submission(self) -> bool:
        """Return True if submission is C++, False if it's a Python one"""

        submission_dir = Path(self.config["submissions_dir"]) / self.submission

        if (submission_dir / "main.cpp").exists() and (
            len((submission_dir / "main.cpp").read_text().strip()) > 10
        ):
            return True
        else:
            return False

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
        INCLUDE_DIR = Path(
            self.config["data_dir"], "..", "..", "smartfactoryinstruments-starting-kit"
        )
        DATA_DIR = os.path.join(self.config["data_dir"], "data", "secret")

        self.status = "finished"

        is_cpp = self.is_cpp_submission()
        if is_cpp:
            bin_path = os.path.join(submission_dir, "main")

            try:
                subprocess.check_call(
                    [
                        "gcc",
                        os.path.join(submission_dir, "main.cpp"),
                        f"-I{INCLUDE_DIR / 'CPP'}",
                        "-lstdc++",
                        "-O3",
                        "-w",
                        "-o",
                        bin_path,
                    ],
                    stderr=self._log_file,
                    stdout=self._log_file,
                )
            except subprocess.CalledProcessError as err:

                self._return_code = COMPILATION_ERROR
                return

            # Compilation passed, clean up the log
            shutil.copy(
                os.path.join(self._log_dir, "log"),
                os.path.join(self._log_dir, "compilation-log"),
            )
            self._log_file.truncate(0)
        else:
            bin_path = os.path.join(submission_dir, "solution.py")
            shutil.copy(INCLUDE_DIR / "python/data.py", submission_dir)

        # Run solution in batches
        batch_size = 4
        for n_batch in range(3):
            t0 = time.perf_counter()
            procs = []
            for sub_idx in range(batch_size):
                idx = batch_size * n_batch + sub_idx
                # We have 9 test cases in total
                if idx > 9:
                    continue
                if is_cpp:
                    p = subprocess.Popen(
                        get_conda_cmd(
                            [str(bin_path)],
                            options=["-v", f"{submission_dir}:{submission_dir}:ro"],
                        ),
                        stdout=open(os.path.join(output_dir, f"case{idx}.ans"), "wb+"),
                        stderr=self._log_file,
                        stdin=open(os.path.join(DATA_DIR, f"case{idx}.in"), "rb"),
                    )
                else:
                    python_runner = (
                        Path(self.config["data_dir"])
                        / "../scripts/ramp_python_runner.py"
                    ).resolve()
                    p = subprocess.Popen(
                        get_conda_cmd(
                            [
                                os.path.join(self._python_bin_path, "python"),
                                str(python_runner),
                                str(bin_path),
                                os.path.join(DATA_DIR, f"case{idx}.in"),
                                os.path.join(output_dir, f"case{idx}.ans"),
                            ],
                            options=[
                                "-v",
                                f"{submission_dir}:{submission_dir}:ro",
                                "-v",
                                f"{python_runner.parent}:{python_runner.parent}:ro",
                                "-v",
                                f"{DATA_DIR}:{DATA_DIR}:ro",
                                "-v",
                                f"{output_dir}:{output_dir}",
                            ],
                        ),
                        stderr=self._log_file,
                    )

                procs.append(p)
            for p in procs:
                # Time remaining for this batch (evaluated in parallel)
                dt = max(t0 + self.timeout - time.perf_counter(), 0)
                if dt == 0:
                    self.status = "timeout"
                    self._return_code = 124
                    return
                try:
                    p.communicate(timeout=dt)
                    self._return_code = max(p.returncode, 0)
                except subprocess.TimeoutExpired:
                    self.status = "timeout"
                    self._return_code = 124
                    return


        if self._return_code > 0:
            return

        # Running the model passed, clean up the log
        shutil.copy(
            os.path.join(self._log_dir, "log"), os.path.join(self._log_dir, "run-log")
        )
        self._log_file.truncate(0)

        # Score the solution
        judger_path = os.path.join(
            self.config["data_dir"], "output_validators", "judger", "__init__.py"
        )
        try:
            subprocess.check_call(
                [
                    os.path.join(self._python_bin_path, "python"),
                    judger_path,
                    DATA_DIR,
                    output_dir,
                    output_dir,
                ],
                stderr=self._log_file,
                stdout=self._log_file,
            )
        except subprocess.CalledProcessError as err:
            self._return_code = SCORING_ERROR
            return

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
                returncode = self._return_code
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

            # Just some fake score for now

            # copy the predictions into the disk
            # no need to create the directory, it will be handle by copytree
            shutil.copytree(output_training_dir, pred_dir)
            self.status = "collected"
            return (returncode, error_msg)

    def check_timeout(self):
        """We use a different timeout mechanism"""
        return None

    def _is_submission_finished():
        """The parallelism happens at the level of test cases"""
        return True
