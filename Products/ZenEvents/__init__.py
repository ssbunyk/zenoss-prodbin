###########################################################################
#
# This program is part of Zenoss Core, an open source monitoring platform.
# Copyright (C) 2007, Zenoss Inc.
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 2 or (at your
# option) any later version as published by the Free Software Foundation.
#
# For complete information please visit: http://www.zenoss.com/oss/
#
###########################################################################

"""__init__

Initializer for netcool connector product

$Id: __init__.py,v 1.8 2004/04/22 19:08:47 edahl Exp $"""

__version__ = "$Revision: 1.8 $"[11:-2]

from Products.CMFCore.DirectoryView import registerDirectory

registerDirectory('skins', globals())

productNames = (
    "EventClass",
    "EventClassInst",
    "EventManagerBase",
)
