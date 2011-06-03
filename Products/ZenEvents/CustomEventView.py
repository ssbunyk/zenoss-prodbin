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

import logging
log = logging.getLogger("zen.EventView")

from Globals import DTMLFile, InitializeClass
from AccessControl import ClassSecurityInfo
from Acquisition import aq_parent
from zope.interface import implements

from Products.ZenModel.ZenModelRM import ZenModelRM
from Products.ZenEvents.EventFilter import EventFilter
from Products.ZenModel.EventView import IEventView

def manage_addCustomEventView(context, id, REQUEST=None):
    """Create an aciton rule"""
    ed = CustomEventView(id)
    context._setObject(id, ed)
    if REQUEST is not None:
        REQUEST['RESPONSE'].redirect(context.absolute_url() + '/manage_main') 

addCustomEventView = DTMLFile('dtml/addCustomEventView',globals())

__pychecker__='no-argsused no-varargsused'

class CustomEventView(ZenModelRM, EventFilter):

    implements(IEventView)

    meta_type = "CustomEventView"

    type = "status"
    evtypes = ("status", "history")
    orderby = ""
    where = ""
    resultFields = ()

    _properties = ZenModelRM._properties + (
        {'id':'type', 'type':'selection',
            'select_variable':'evtypes', 'mode':'w'},
        {'id':'orderby', 'type':'string', 'mode':'w'},
        {'id':'where', 'type':'text', 'mode':'w'},
        {'id':'resultFields', 'type':'lines', 'mode':'w'},
    )

    security = ClassSecurityInfo()

InitializeClass(CustomEventView)
