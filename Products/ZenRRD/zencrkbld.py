#################################################################
#
#   Copyright (c) 2003 Zentinel Systems, Inc. All rights reserved.
#
#################################################################

__doc__="""ZenCrkBld

Gets cricket config from dmd and writes it out on the cricket server

$Id: ZenCrkBld.py,v 1.6 2004/04/07 00:02:44 edahl Exp $"""

__version__ = "$Revision: 1.6 $"[11:-2]

import time
import os
import xmlrpclib
import pprint
import popen2

import Globals

from Products.ZenUtils.ZenDaemon import ZenDaemon
from Products.ZenUtils.Utils import basicAuthUrl

from utils import RRDException

class TargetDataError(RRDException):pass

class ZenCrkBld(ZenDaemon):

    def __init__(self):
        ZenDaemon.__init__(self)
        self.curtargetpath = ''
        self.curtarget = ''
        self.cycletime = self.options.cycletime*60
        crkhome = os.path.join(os.environ['ZENHOME'], "cricket")
        self.crkcfg = os.path.join(crkhome, "cricket-config")
        self.crkcompile = os.path.join(crkhome, "bin", "compile")


    def buildOptions(self):
        ZenDaemon.buildOptions(self)
        self.parser.add_option("-z", "--zopeurl",
                    dest="zopeurl",
                    help="XMLRPC url path for cricket configuration server ")
        self.parser.add_option("-u", "--zopeusername",
                    dest="zopeusername",
                    help="username for zope server")
        self.parser.add_option("-p", "--zopepassword",
                    dest="zopepassword")
        self.parser.add_option("-d", "--devicename",
                    dest="devicename")
        self.parser.add_option("-F", "--force",
                    dest="force", action='store_true',
                    help="force generation of cricket data " 
                         "(even without change to the device)")
        self.parser.add_option("--debug",
                    dest="debug", action='store_true')
        self.parser.add_option("--cycletime",
                    dest="cycletime", type='int', default=60)
   

    def build(self):
        if not os.path.exists(self.crkcfg):
            self.log.critical("directory: %s not found", self.crkcfg)
            raise SystemExit
        os.chdir(self.crkcfg)
        url = basicAuthUrl(self.options.zopeusername, 
                            self.options.zopepassword,
                            self.options.zopeurl)
        server = xmlrpclib.Server(url, allow_none=True)
        cricketDataSources = server.cricketDataSources()
        dsfile = open('ZenossDataSources', 'w')
        self.writeHeader(dsfile)
        dsfile.write(cricketDataSources)
        dsfile.close()
        cricketDevices = server.cricketDeviceList(self.options.force)
        if self.options.devicename:
            cricketDevices = filter(
                lambda x: x.endswith(self.options.devicename), cricketDevices)
        if self.options.debug:
            pprint.pprint(cricketDevices)
        for devurl in cricketDevices:
            self.buildDevice(devurl)
        child = popen2.Popen4(self.crkcompile)
        child.wait()
        #os.system(self.crkcompile)


    def buildDevice(self, devurl):        
        try:
            self.log.info("building device %s", devurl)
            devurl = basicAuthUrl(self.options.zopeusername, 
                                  self.options.zopepassword, devurl)
            device = xmlrpclib.Server(devurl)
            cricketData = device.cricketGenerate()
            if self.options.debug:
                pprint.pprint(cricketData)
            for targetpath, targettypes, targetdatas in cricketData:
                if targetpath[0] == '/': targetpath = targetpath[1:]
                tfile = self.opentargets(targetpath)
                self.writeHeader(tfile)
                for tname, dsnames in targettypes.items():
                    self.printTargetType(tfile, tname, dsnames)
                tfile.write("\n")
                for targetdata in targetdatas:
                    self.printTargets(tfile, targetdata)
                tfile.close()
        except (SystemExit, KeyboardInterrupt): raise
        except:
            self.log.exception("Exception processing device %s", devurl)


    def opentargets(self, targetpath):
        """open targets file based on targetpath"""
        self.curtargetpath = targetpath
        self.log.debug("building target file %s" % targetpath)
        if not os.path.exists(targetpath):
            os.makedirs(targetpath, 0755)
        targetfile = targetpath + '/targets'
        return open(targetfile, 'w')

        
    def writeHeader(self, ofile):   
        ofile.write("# Generated by zencrkbld.py on %s\n" 
                        % time.strftime('%Y/%m/%d %H:%M:%S %Z'))
        ofile.write("# From DMD %s\n" % self.options.zopeurl)
        ofile.write("# !!! Do not edit manually !!!\n\n")


    def printTargetType(self, tfile, targetname, dsnames):
        tttmpl = """targetType %s
        ds = "%s\"""" % (targetname, ",".join(dsnames))
        tfile.write(tttmpl+"\n")

    
    def printTargets(self, tfile, targetdata):
        """print out target file using target data"""
        if not targetdata.has_key('target'):
            raise TargetDataError, "Malformed targetdata no target found"
        self.curtarget = targetdata['target']
        self.log.debug("building target %s" % self.curtarget)
        tfile.write('target "%s"\n' % self.curtarget)
        for attrib, value in targetdata.items():
            if attrib == 'target' or value == '' or value == None: continue
            value = str(value)
            self.log.debug("attrib=%s value=%s" % (attrib, value))
            if value.find(' ') > -1: value = '"%s"' % value
            tfile.write("\t%s = %s\n" % (attrib, value))
        tfile.write('\n')
 

    def main(self):
        if not self.options.cycle:
            return self.build()
        while 1:
            startLoop = time.time()
            runTime = 0
            try:
                self.log.debug("starting build loop")
                self.build()
                runTime = time.time()-startLoop
                self.log.debug("ending build loop")
                self.log.info("build time = %0.2f seconds",runTime)
            except:
                self.log.exception("problem in main loop")
            if runTime < self.cycletime:
                time.sleep(self.cycletime - runTime)

        

if __name__ == '__main__':
    cb = ZenCrkBld()
    cb.main()
