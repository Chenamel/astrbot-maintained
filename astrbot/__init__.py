import logging

__version__ = "4.28.2-mtn1"
#: PEP 440 parseable base of __version__ (strips a custom suffix such as
#: "-mtn1"), for callers that must hand a strict Version() a valid string.
__version_base__ = __version__.split("-")[0].split("+")[0]
logger = logging.getLogger("astrbot")
