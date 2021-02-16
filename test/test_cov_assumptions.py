import os

import pytest
from coverage import Coverage
from testmon.testmon_core import Testmon as CoreTestmon, is_coverage5

pytest_plugins = ("pytester",)
