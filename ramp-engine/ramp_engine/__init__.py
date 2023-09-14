from .aws import AWSWorker
from .dispatcher import Dispatcher  # noqa
from .local import CondaEnvWorker
from .cpp_runner import CppCondaEnvWorker
from .remote import DaskWorker

from ._version import __version__

available_workers = {
    "conda": CondaEnvWorker,
    "aws": AWSWorker,
    "dask": DaskWorker,
    "conda-cpp": CppCondaEnvWorker,
}

__all__ = [
    "AWSWorker",
    "CondaEnvWorker",
    "DaskWorker",
    "Dispatcher",
    "available_workers",
    "__version__",
]
