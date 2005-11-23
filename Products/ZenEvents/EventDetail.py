
from ZEvent import ZEvent
from Products.ZenModel.ZenModelItem import ZenModelItem
from Acquisition import Implicit

from AccessControl import Permissions as permissions
from Globals import InitializeClass
from AccessControl import ClassSecurityInfo

class EventDetail(ZEvent, ZenModelItem, Implicit):
    security = ClassSecurityInfo()
    security.setDefaultAccess("allow")

    factory_type_information = ( 
        { 
            'id'             : 'EventDetail',
            'meta_type'      : 'EventDetail',
            'description'    : """Detail view of netcool event""",
            'icon'           : 'EventDetail_icon.gif',
            'product'        : 'ZenEvents',
            'factory'        : '',
            'immediate_view' : 'viewEventFields',
            'actions'        :
            ( 
                { 'id'            : 'fields'
                , 'name'          : 'Fields'
                , 'action'        : 'viewEventFields'
                , 'permissions'   : (
                  permissions.view, )
                },
                { 'id'            : 'details'
                , 'name'          : 'Details'
                , 'action'        : 'viewEventDetail'
                , 'permissions'   : (
                  permissions.view, )
                },
                { 'id'            : 'log'
                , 'name'          : 'Log'
                , 'action'        : 'viewEventLog'
                , 'permissions'   : (
                  permissions.view, )
                },
            )
          },
        )

    def __init__(self, manager, fields, data, details=None, logs=None):
        ZEvent.__init__(self, manager, fields, data)
        self._fields = fields
        self._details = details
        self._logs = logs

    def getEventFields(self):
        """return an array of event fields tuples (field,value)"""
        return [(x, getattr(self, x)) for x in self._fields]


    def getEventDetails(self):
        """return array of detail tuples (field,value)"""
        return self._details


    def getEventLogs(self):
        """return an array of log tuples (user,date,text)"""
        return self._logs
        

InitializeClass(EventDetail)

class EventData:
    security = ClassSecurityInfo()
    security.setDefaultAccess("allow")
    def __init__(self, field, value):
        self.field = field
        self.value = value
InitializeClass(EventData)


class EventLog:
    security = ClassSecurityInfo()
    security.setDefaultAccess("allow")
    def __init__(self, user, date, text):
        self.user = user
        self.date = date
        self.text = text
InitializeClass(EventLog)
