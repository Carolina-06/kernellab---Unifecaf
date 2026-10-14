import os
import sys

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from schedulers import load_config  # noqa: E402

DATA = os.path.join(os.path.dirname(SRC), "data", "processes.json")


def medcontrol():
    return load_config(DATA)["processes"]
