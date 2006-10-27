#################################################################
#
#   Copyright (c) 2006 Zenoss, Inc. All rights reserved.
#
#################################################################

__doc__='''

Add Processes organizer and friends.

'''

__version__ = "$Revision$"[11:-2]

import Migrate
import os

class Processes(Migrate.Step):
    version = Migrate.Version(0, 22, 0)

    def cutover(self, dmd):
        
        if hasattr(dmd, 'Processes'):
            if not dmd.Processes.hasProperty('zFailSeverity'):
                dmd.Processes._setProperty("zFailSeverity", 4, type="int")
            return

        from Products.ZenModel.OSProcessOrganizer \
             import manage_addOSProcessOrganizer
        manage_addOSProcessOrganizer(dmd, 'Processes')

        if getattr(dmd.Devices.rrdTemplates, 'OSProcess', None) is None:
            from Products.ZenRelations.ImportRM import ImportRM
            imp = ImportRM(noopts=True, app=dmd.getPhysicalRoot())
            imp.options.noCommit = True
            imp.options.noindex = True
            imp.options.infile = os.path.join(os.environ['ZENHOME'],
                'Products', 'ZenModel', 'data', 'osproc.update')
            imp.loadDatabase()

Processes()
