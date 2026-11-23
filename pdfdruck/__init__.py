# SPDX-License-Identifier: GPL-3.0-or-later
# Passermark – Copyright (C) 2026 Hias
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public
# License, version 3 or (at your option) any later version.
# It is provided WITHOUT ANY WARRANTY. See the file LICENSE.
__version__ = "1.20.1"

import logging

# Recoverable errors are logged as warnings (logger "pdfdruck.<module>"). Without a configured log (CLI, tests)
# they stay silent; the GUI writes them to the error log (crashlog.install), the render process to stderr.
logging.getLogger(__name__).addHandler(logging.NullHandler())
