import logging

__version__ = "4.29.4+mtn1"
#: PEP 440 parseable base of __version__ (drops any local version or custom
#: suffix), for callers that must hand a strict Version() a valid string.
__version_base__ = __version__.split("-")[0].split("+")[0]
logger = logging.getLogger("astrbot")
