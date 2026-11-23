import copy
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import load_config  # noqa: E402
from src.contract import load_contract  # noqa: E402


@pytest.fixture(scope="session")
def cfg():
    return load_config()


@pytest.fixture()
def cfg_copy(cfg):
    return copy.deepcopy(cfg)


@pytest.fixture(scope="session")
def contract():
    return load_contract()
