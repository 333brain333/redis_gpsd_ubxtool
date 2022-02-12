# Make core client functions available without prefix.
# This code is generated by scons.  Do not hand-hack it!
#
# This file is Copyright 2010 by the GPSD project
# SPDX-License-Identifier: BSD-2-Clause
#
# This code runs compatibly under Python 2 and 3.x for x >= 2.
# Preserve this property!
from __future__ import absolute_import  # Ensure Python2 behaves like Python 3

from .gps import *
from .misc import *

# Keep in sync with gpsd.h
api_version_major = 3   # bumped on incompatible changes
api_version_minor = 14   # bumped on compatible changes

# at some point this will need an override method
__iconpath__ = '/usr/local/share/gpsd/icons'

__version__ = '3.23.1'

# The 'client' module exposes some C utility functions for Python clients.
# The 'packet' module exposes the packet getter via a Python interface.

# vim: set expandtab shiftwidth=4
