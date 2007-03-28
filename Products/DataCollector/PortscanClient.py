import logging

from twisted.internet import reactor, error
from twisted.python import failure

import Globals

from Products.ZenUtils import PortScan

log = logging.getLogger("zen.PortscanClient")

class PortscanClient(object):

    def __init__(self, hostname, ipaddr, options=None, device=None, 
                 datacollector=None, plugins=[]):
        self.hostname = hostname
        self.device = device
        self.options = options
        self.datacollector = datacollector
        self.plugins = plugins
        self.results = []

        maxPort = getattr(device,'zIpServiceMapMaxPort', 1024)
        self.portRange = (1, maxPort)

        #self.portList = getattr(device,'zPortscanPortList', [])
        self.portList = []

        if self.portList:
            kwds = {'portList': self.portList}
        else:
            kwds = {'portRange': self.portRange}
        kwds.update(dict(timeout=self.options.portscantimeout))
        self.scanner = PortScan.Scanner(ipaddr, **kwds)
        
    def run(self):
        """
        Start portscan collection.
        """
        for plugin in self.plugins:
            pluginName = plugin.name()
            log.debug("sending queries for plugin %s", pluginName)
            d = self.scanner.prepare()
            d.addCallback(self._cbScanComplete, pluginName)
            d.addErrback(self._ebScanError, pluginName)

    def _cbScanComplete(self, results, pluginName):
        log.debug("received plugin:%s getOids", pluginName)
        self.clientFinished(pluginName)

    def _ebScanError( self, err, pluginName):
        """Handle an error generated by one of our requests.
        """
        self.clientFinished(pluginName)
        log.debug('device %s plugin %s %s', self.hostname, pluginName, err)
        if isinstance(err, failure.Failure):
            actualError = err.value
            trace = err.getTraceback()
        else:
            actualError = err
            trace = log.getException(err)
        log.error(
            """device %s plugin %s unexpected error: %s""",
            self.hostname, pluginName, trace,
        )

    def getResults(self):
        """
        ZenUtils.PortScan records open ports in a list that are the
        values for a key in a dict where the key is the IP address
        scanned.

        For example, if we scan host 10.0.4.55 and ports 22 and 80 are
        open, getSuccesses() will return the following:

            {'10.0.4.55': [22, 80]}
        """
        return self.results

    def clientFinished(self, pluginName):
        """
        Tell the datacollector that we are all done.
        """
        log.info("portscan client finished collection for %s" % self.hostname)
        # ApplyDataMap.processClient() expect an iterable with two
        # elements: the plugin name and the results, so we set this
        # here.        
        data = (pluginName, self.scanner.getSuccesses())
        self.results.append(data)
        if self.datacollector:
            self.datacollector.clientFinished(self)
        else:
            reactor.stop()

def buildOptions(parser=None, usage=None):
    "build options list that both telnet and ssh use"
   
    if not usage:
        usage = "%prog [options] hostname[:port] oids"

    if not parser:
        from optparse import OptionParser
        parser = OptionParser(usage=usage, 
                                   version="%prog " + __version__)
    # XXX this function may need options later, so we'll keep this here
    # as a reminder for now
    #parser.add_option('--snmpCommunity',
    #            dest='snmpCommunity',
    #            default=defaultSnmpCommunity,
    #            help='Snmp Community string')

if __name__ == "__main__":
    import sys
    sys.path.extend([
        '/usr/local/zenoss/Products/DataCollector/plugins',
    ])
    import pprint
    from zenoss.portscan import IpServiceMap

    logging.basicConfig()
    log = logging.getLogger()
    log.setLevel(20)
    ipmap = IpServiceMap.IpServiceMap()
    psc = PortscanClient("localhost", '127.0.0.1', plugins=[ipmap,])
    psc.run()
    reactor.run()
    pprint.pprint(psc.getResults())
