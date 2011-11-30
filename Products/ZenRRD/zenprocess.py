#! /usr/bin/env python
###########################################################################
#
# This program is part of Zenoss Core, an open source monitoring platform.
# Copyright (C) 2007, 2009, 2011 Zenoss Inc.
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 2 or (at your
# option) any later version as published by the Free Software Foundation.
#
# For complete information please visit: http://www.zenoss.com/oss/
#
###########################################################################
__doc__ = """zenprocess

Gets SNMP process data from a device's HOST-RESOURCES-MIB
and store process performance in RRD files.
"""

import logging
import sys
import re
from md5 import md5
from pprint import pformat
import os.path

import Globals

import zope.component
import zope.interface

from Products.ZenCollector.daemon import CollectorDaemon
from Products.ZenCollector.interfaces import ICollectorPreferences,\
    IScheduledTask, IEventService, IDataService, IConfigurationListener
from Products.ZenCollector.tasks import SimpleTaskFactory, SimpleTaskSplitter,\
    TaskStates
from Products.ZenEvents import Event
from Products.ZenEvents.ZenEventClasses import Status_Snmp, Status_OSProcess,\
    Status_Perf
from Products.ZenUtils.observable import ObservableMixin

# We retrieve our configuration data remotely via a Twisted PerspectiveBroker
# connection. To do so, we need to import the class that will be used by the
# configuration service to send the data over, i.e. DeviceProxy.
from Products.ZenUtils.Utils import unused
from Products.ZenCollector.services.config import DeviceProxy

unused(DeviceProxy)
from Products.ZenHub.services.ProcessConfig import ProcessProxy

unused(ProcessProxy)
from Products.ZenHub.services.PerformanceConfig import SnmpConnInfo

unused(SnmpConnInfo)

from twisted.internet import defer, error
from pynetsnmp.twistedsnmp import Snmpv3Error

log = logging.getLogger("zen.zenprocess")

# HOST-RESOURCES-MIB OIDs used
HOSTROOT = '.1.3.6.1.2.1.25'
RUNROOT = HOSTROOT + '.4'
NAMETABLE = RUNROOT + '.2.1.2'
PATHTABLE = RUNROOT + '.2.1.4'
ARGSTABLE = RUNROOT + '.2.1.5'
PERFROOT = HOSTROOT + '.5'
CPU = PERFROOT + '.1.1.1.'        # note trailing dot
MEM = PERFROOT + '.1.1.2.'        # note trailing dot

# Max size for CPU numbers
WRAP = 0xffffffffL

# Regex to see if a string is all hex digits
IS_MD5 = re.compile('^[a-f0-9]{32}$')

PROC_SCAN_ERROR = 'Unable to read processes on device %s'

class HostResourceMIBExecption(Exception):
    pass

# Create an implementation of the ICollectorPreferences interface so that the
# ZenCollector framework can configure itself from our preferences.
class ZenProcessPreferences(object):
    zope.interface.implements(ICollectorPreferences)

    def __init__(self):
        """
        Constructs a new ZenProcessPreferences instance and provide default
        values for needed attributes.
        """
        self.collectorName = "zenprocess"
        self.defaultRRDCreateCommand = None
        self.configCycleInterval = 20 # minutes

        #will be updated based on Performance Config property of same name
        self.processCycleInterval = 3 * 60

        #will be filled in based on buildOptions
        self.options = None

        # the configurationService attribute is the fully qualified class-name
        # of our configuration service that runs within ZenHub
        self.configurationService = 'Products.ZenHub.services.ProcessConfig'

    @property
    def cycleInterval(self):
        """
        defined as a property since it is needed by the interface    
        """
        return self.processCycleInterval

    def buildOptions(self, parser):
        """
        Build a list of command-line options
        """
        parser.add_option('--showprocs',
                          dest='showprocs',
                          action="store_true",
                          default=False,
                          help="Show the list of processes found."\
                               "For debugging purposes only.")
        parser.add_option('--showrawtables',
                          dest='showrawtables',
                          action="store_true",
                          default=False,
                          help="Show the raw SNMP processes data returned "\
                               "from the device. For debugging purposes only.")
        parser.add_option('--captureFilePrefix', dest='captureFilePrefix',
                          default='',
                          help="Directory and filename to use as a template"
                               " to store SNMP results from device.")

    def postStartup(self):
        pass


class DeviceStats:
    def __init__(self, deviceProxy):
        self.config = deviceProxy
        # map pid number to ProcessStats object
        self._pidToProcess = {}
        # map ProcessProxy id to ProcessStats object
        self._processes = {}
        for id, process in deviceProxy.processes.items():
            self._processes[id] = ProcessStats(process)

    def update(self, deviceProxy):
        unused = set(self._processes.keys())
        for id, process in deviceProxy.processes.items():
            unused.discard(id)
            if self._processes.get(id):
                self._processes[id].update(process)
            else:
                self._processes[id] = ProcessStats(process)

        #delete the left overs
        for id in unused:
            del self._processes[id]

    @property
    def processStats(self):
        """
        The ProcessStats: processes configured to be monitored
        """
        return self._processes.values()

    @property
    def pids(self):
        """
        returns the pids from being tracked
        """
        return self._pidToProcess.keys()

    @property
    def monitoredProcs(self):
        """
        returns ProcessStats for which we have a pid
        """
        return self._pidToProcess.values()


class ProcessStats:
    def __init__(self, processProxy):
        self._pids = {}
        self._config = processProxy
        self.cpu = 0
        self.digest = md5('').hexdigest()
        if not self._config.ignoreParameters:
            # The modeler plugin computes the MD5 hash of the args,
            # and then tosses that into the name of the process
            result = self._config.name.rsplit(' ', -1)
            if len(result) == 2 and result[1] != '':
                self.digest = result[1]

    def update(self, processProxy):
        self._config = processProxy

    def __str__(self):
        """
        Override the Python default to represent ourselves as a string
        """
        return str(self._config.name)

    __repr__ = __str__

    def match(self, name, args, useMd5Digest=True):
        """
        Perform exact comparisons on the process names.

        @parameter name: name of a process to compare
        @type name: string
        @parameter args: argument list of the process
        @type args: string
        @parameter useMd5Digest: ignore true result if MD5 doesn't match the process name?
        @type useMd5Digest: boolean
        @return: does the name match this process's info?
        @rtype: Boolean
        """
        if self._config.name is None:
            return False

        # SNMP agents return a 'flexible' number of characters,
        # so exact matching isn't always reliable.
        if self._config.ignoreParameters:
            processName = name
        else:
            processName = ('%s %s' % (name, args or '')).strip()

        # Make the comparison
        result = re.search(self._config.regex, processName) is not None

        # We can a match, but it might not be for us
        if result and useMd5Digest:
            # Compare this arg list against the digest of this proc
            digest = md5(args).hexdigest()
            if self.digest and digest != self.digest:
                result = False

        return result

    def updateCpu(self, pid, value):
        """
        """
        pid = self._pids.setdefault(pid, Pid())
        cpu = pid.updateCpu(value)
        if cpu is not None:
            self.cpu += cpu
            self.cpu %= WRAP

    def getCpu(self):
        """
        """
        return self.cpu

    def updateMemory(self, pid, value):
        """
        """
        self._pids.setdefault(pid, Pid()).memory = value

    def getMemory(self):
        """
        """
        return sum(x.memory for x in self._pids.values() if x.memory is not None)

    def discardPid(self, pid):
        """
        """
        if pid in self._pids:
            del self._pids[pid]


class Pid:
    """
    Helper class to track process id information
    """
    cpu = None
    memory = None

    def updateCpu(self, n):
        """
        """
        if n is not None:
            try:
                n = int(n)
            except ValueError:
                log.warning("Bad value for CPU: '%s'", n)

        if self.cpu is None or n is None:
            self.cpu = n
            return None
        diff = n - self.cpu
        if diff < 0:
            # don't provide a value when the counter falls backwards
            n = None
            diff = None
        self.cpu = n
        return diff

    def updateMemory(self, n):
        """
        """
        self.memory = n

    def __str__(self):
        """
        Override the Python default to represent ourselves as a string
        """
        return '<Pid> memory: %s cpu: %s' % (self.memory, self.cpu)

    __repr__ = __str__


class ConfigListener(object):
    zope.interface.implements(IConfigurationListener)

    def deleted(self, configurationId):
        """
        Called when a configuration is deleted from the collector
        """
        log.debug('ConfigListener: configuration %s deleted' % configurationId)
        ZenProcessTask.DEVICE_STATS.pop(configurationId, None)

    def added(self, configuration):
        """
        Called when a configuration is added to the collector
        """
        log.debug('ConfigListener: configuration %s added' % configuration)


    def updated(self, newConfiguration):
        """
        Called when a configuration is updated in collector
        """
        log.debug('ConfigListener: configuration %s updated' % newConfiguration)

# Create an implementation of the IScheduledTask interface that will perform
# the actual collection work needed by this collector.
class ZenProcessTask(ObservableMixin):
    """
    A scheduled task that finds instances of configure processes and collects 
    metrics on the processes 
    """
    zope.interface.implements(IScheduledTask)

    #Keep state about process stats across task updates
    DEVICE_STATS = {}

    #counter to keep track of total restarted and missing processes
    RESTARTED = 0
    MISSING = 0

    STATE_CONNECTING = 'CONNECTING'
    STATE_SCANNING_PROCS = 'SCANNING_PROCESSES'
    STATE_FETCH_PERF = 'FETCH_PERF_DATA'
    STATE_STORE_PERF = 'STORE_PERF_DATA'
    STATE_PARSING_TABLE_DATA = 'PARSING_TABLE_DATA'

    statusEvent = {'eventClass': Status_OSProcess,
                   'eventGroup': 'Process'}

    def __init__(self,
                 deviceId,
                 taskName,
                 scheduleIntervalSeconds,
                 taskConfig):
        super(ZenProcessTask, self).__init__()

        #needed for interface
        self.name = taskName
        self.configId = deviceId
        self.interval = scheduleIntervalSeconds
        self.state = TaskStates.STATE_IDLE

        #the task config corresponds to a DeviceProxy
        self._device = taskConfig
        self._devId = self._device.name
        self._manageIp = self._device.manageIp
        self._maxOidsPerRequest = self._device.zMaxOIDPerRequest

        self._dataService = zope.component.queryUtility(IDataService)
        self._eventService = zope.component.queryUtility(IEventService)
        self._preferences = zope.component.queryUtility(ICollectorPreferences,
                                                        "zenprocess")
        self.snmpProxy = None
        self.snmpConnInfo = self._device.snmpConnInfo

        self._deviceStats = ZenProcessTask.DEVICE_STATS.get(self._devId)
        if self._deviceStats:
            self._deviceStats.update(self._device)
        else:
            self._deviceStats = DeviceStats(self._device)
            ZenProcessTask.DEVICE_STATS[self._devId] = self._deviceStats

    @defer.inlineCallbacks
    def doTask(self):
        """
        Contact to one device and return a deferred which gathers data from
        the device.

        @return: job to scan a device
        @rtype: Twisted deferred object
        """
        try:
            # see if we need to connect first before doing any collection
            self.openProxy()
            log.debug("Opened proxy to %s [%s]", self._devId, self._manageIp)
            yield self._collectCallback()
        finally:
            self._finished()


    @defer.inlineCallbacks
    def _collectCallback(self):
        """
        Callback called after a connect or previous collection so that another
        collection can take place.
        """
        log.debug("Scanning for processes from %s [%s]",
                  self._devId, self._manageIp)

        self.state = ZenProcessTask.STATE_SCANNING_PROCS
        tables = [NAMETABLE, PATHTABLE, ARGSTABLE]
        try:
            tableResult = yield self._getTables(tables)
            summary = 'Process table up for device %s' % self._devId
            self._clearSnmpError("%s - timeout cleared" % summary, 'table_scan_timeout')
            if self.snmpConnInfo.zSnmpVer == 'v3':
                self._clearSnmpError("%s - v3 error cleared" % summary, 'table_scan_v3_error')
            processes = self._parseProcessNames(tableResult)
            self._clearSnmpError(summary, 'resource_mib')
            processStatuses = self._determineProcessStatus(processes)
            self._sendProcessEvents(processStatuses)
            self._clearSnmpError(summary)
            yield self._fetchPerf()
            log.debug("Device %s [%s] scanned successfully",
                      self._devId, self._manageIp)
        except HostResourceMIBExecption as e:
            summary = 'Device %s does not publish HOST-RESOURCES-MIB' %\
                      self._devId
            resolution = "Verify with snmpwalk %s %s" %\
                         (self._devId, NAMETABLE )
            log.warn(summary)
            self._sendSnmpError(summary, "resource_mib", resolution=resolution)

        except error.TimeoutError as e:
            log.debug('Timeout fetching tables on device %s' % self._devId)
            self._sendSnmpError('%s; Timeout on device' % PROC_SCAN_ERROR % self._devId, 'table_scan_timeout')
        except Snmpv3Error as e:
            msg = "Cannot connect to SNMP agent on {0._devId}: {1.value}".format(self, str(e))
            log.debug(msg)
            self._sendSnmpError('%s; %s' % (PROC_SCAN_ERROR % self._devId, msg), 'table_scan_v3_error')
        except Exception as e:
            log.exception('Unexpected Error on device %s' % self._devId)
            msg = '%s; error: %s' % (PROC_SCAN_ERROR % self._devId, e)
            self._sendSnmpError(msg)

    def _finished(self):
        """
        Callback activated when the task is complete
        """
        try:
            self._close()
        except Exception, e:
            log.warn("Failed to close device %s: error %s" %
                     (self._devId, str(e)))


    def cleanup(self):
        return self._close()

    def capturePacket(self, hostname, data):
        """
        Store SNMP results into files for unit-testing.
        """
        # Prep for using capture replay module later
        if not hasattr(self, 'captureSerialNum'):
            self.captureSerialNum = 0

        log.debug("Capturing packet from %s", hostname)
        name = "%s-%s-%d" % (self._preferences.options.captureFilePrefix,
                             hostname, self.captureSerialNum)

        # Don't overwrite previous captures, which will happen if we remodel
        # and the serial number gets reset to zero
        while os.path.exists(name):
            self.captureSerialNum += 1
            name = "%s-%s-%d" % (self._preferences.options.captureFilePrefix,
                             hostname, self.captureSerialNum)

        try:
            capFile = open(name, "w")
            capFile.write(pformat(data))
            capFile.close()
            self.captureSerialNum += 1
        except Exception, ex:
            log.warn("Couldn't write capture data to '%s' because %s",
                     name, str(ex))

    def sendRestartEvents(self, afterByConfig, beforeByConfig, restarted):
        for procStats, pConfig in restarted.iteritems():
            droppedPids = []
            for pid in beforeByConfig[procStats]:
                if pid not in afterByConfig[procStats]:
                    droppedPids.append(pid)
            summary = 'Process restarted: %s' % pConfig.originalName
            message = '%s\n Using regex \'%s\' Discarded dead pid(s) %s Using new pid(s) %s'\
            % (summary, pConfig.regex, droppedPids, afterByConfig[procStats])
            self._eventService.sendEvent(self.statusEvent,
                                         device=self._devId,
                                         summary=summary,
                                         message=message,
                                         component=pConfig.originalName,
                                         eventKey=pConfig.processClass,
                                         severity=pConfig.severity)
            log.info("(%s) %s" % (self._devId, message))

    def sendFoundProcsEvents(self, afterByConfig, restarted):
        # report alive processes
        for processStat in afterByConfig.keys():
            if processStat in restarted: continue
            summary = "Process up: %s" % processStat._config.originalName
            message = '%s\n Using regex \'%s\' with pid\'s %s '\
            % (summary, processStat._config.regex, afterByConfig[processStat])
            self._eventService.sendEvent(self.statusEvent,
                                         device=self._devId,
                                         summary=summary,
                                         message=message,
                                         component=processStat._config.originalName,
                                         eventKey=processStat._config.processClass,
                                         severity=Event.Clear)
            log.debug("(%s) %s" % (self._devId, message))

    def _parseProcessNames(self, results):
        """
        Parse the process tables and reconstruct the list of processes
        that are on the device.

        @parameter results: results of SNMP table gets
        @type results: dictionary of dictionaries
        """
        self.state = ZenProcessTask.STATE_PARSING_TABLE_DATA
        if not results or not results[NAMETABLE]:
            raise HostResourceMIBExecption()

        if self._preferences.options.captureFilePrefix:
            self.capturePacket(self._devId, results)

        showrawtables = self._preferences.options.showrawtables
        args, procs = mapResultsToDicts(showrawtables, results)
        if self._preferences.options.showprocs:
            self._showProcessList(procs)
        return procs

    def sendMissingProcsEvents(self, missing):
        # Look for missing processes
        for procConfig in missing:
            ZenProcessTask.MISSING += 1
            summary = 'Process not running: %s' % procConfig.originalName
            message = "%s\n   Using regex \'%s\' \n   All Processes have stopped since the last model occurred. Last Modification time (%s)" \
                        % (summary,procConfig.regex,self._device.lastmodeltime)
            self._eventService.sendEvent(self.statusEvent,
                                             device=self._devId,
                                             summary=summary,
                                             message=message,
                                             component=procConfig.originalName,
                                             eventKey=procConfig.processClass,
                                             severity=procConfig.severity)
            log.warning("(%s) %s" % (self._devId, message))

    def _sendProcessEvents(self, results):
        (afterByConfig, afterPidToProcessStats,
         beforeByConfig, newPids, restarted, deadPids, missing) = results

        self.sendRestartEvents(afterByConfig, beforeByConfig, restarted)
        self.sendFoundProcsEvents(afterByConfig, restarted)

        for pid in newPids:
            log.debug("Found new %s %s pid %d on %s " % (
                afterPidToProcessStats[pid]._config.originalName, afterPidToProcessStats[pid]._config.name, pid,
                self._devId))
        self._deviceStats._pidToProcess = afterPidToProcessStats
        self.sendMissingProcsEvents(missing)

        # Store the total number of each process into an RRD
        pidCounts = dict((p, 0) for p in self._deviceStats.processStats)

        for procStat in self._deviceStats.monitoredProcs:
            # monitoredProcs is determined from the current pids in _pidToProcess
            # pidCounts is from _deviceStats.processStats which is modeled data
            if procStat in pidCounts:
                pidCounts[procStat] += 1
            else:
                log.warn('%s monitored proc %s %s not in process stats', self._devId, procStat._config.name,
                         procStat._config.originalName)
                log.debug("%s pidcounts is %s", self._devId, pidCounts)
        for procName, count in pidCounts.items():
            self._save(procName, 'count_count', count, 'GAUGE')
        return "Sent events"

    def _determineProcessStatus(self, procs):
        """
        Determine the up/down/restarted status of processes.

        @parameter procs: array of pid, (name, args) info
        @type procs: list
        """
        beforePids = set(self._deviceStats.pids)
        afterPidToProcessStats = {}
        pStatsWArgsAndSums, pStatsWoArgs = self._splitPStatMatchers()
        for pid, (name, psargs) in procs:
            pStats = self._deviceStats._pidToProcess.get(pid)
            if pStats:
                # We saw the process before, so there's a good
                # chance that it's the same.
                if pStats.match(name, psargs):
                    # Yep, it's the same process
                    log.debug("Found process %d on %s, matching %s %s with MD5",
                              pid, pStats._config.name, name, psargs)
                    log.debug("%s found existing stat %s %s for pid %s - using MD5", self._devId, pStats._config.name,
                              pStats._config.originalName, pid)
                    afterPidToProcessStats[pid] = pStats
                    continue

                elif pStats.match(name, psargs, useMd5Digest=False):
                    # In this case, our raw SNMP data from the
                    # remote agent got futzed
                    # It's the same process. Yay!
                    log.debug("%s - Found process %d on %s, matching %s %s without MD5",
                              self._devId, pid, pStats._config.name, name, psargs)
                    afterPidToProcessStats[pid] = pStats
                    continue

            # Search for the first match in our list of regexes
            # that have arguments AND an MD5-sum argument matching.
            # Explicitly *IGNORE* any matchers not modeled by zenmodeler
            for pStats in pStatsWArgsAndSums:
                if pStats.match(name, psargs):
                    log.debug("%s Found process %d on %s %s",
                              self._devId, pid, pStats._config.originalName, pStats._config.name)
                    afterPidToProcessStats[pid] = pStats
                    break
            else:
                # Now look for the first match in our list of regexes
                # that don't have arguments.
                for pStats in pStatsWoArgs:
                    if pStats.match(name, psargs, useMd5Digest=False):
                        log.debug("Found process %d on %s",
                                      pid, pStats._config.name)
                        afterPidToProcessStats[pid] = pStats
                        break

        # If the hashes get trashed by the SNMP agent, try to
        # make sensible guesses.
        missingModeledStats = sorted(set(self._deviceStats.processStats) -
                                     set(afterPidToProcessStats.values()), key=lambda x:x._config.name)
        if missingModeledStats:
            log.info("Searching for possible matches for %s", missingModeledStats)
        for pStats in missingModeledStats:
            for pid, (name, args) in procs:
                if pid in afterPidToProcessStats:
                    continue

                if pStats.match(name, args, useMd5Digest=False):
                    log.debug("%s missingModeledStats - Found process %d on %s %s",
                              self._devId, pid, pStats._config.originalName, pStats._config.name)
                    afterPidToProcessStats[pid] = pStats
                    break

        afterPids = set(afterPidToProcessStats.keys())
        afterByConfig = reverseDict(afterPidToProcessStats)
        newPids = afterPids - beforePids
        deadPids = beforePids - afterPids

        restarted = {}
        for pid in deadPids:
            procStats = self._deviceStats._pidToProcess[pid]
            procStats.discardPid(pid)
            if procStats in afterByConfig:
                ZenProcessTask.RESTARTED += 1
                pConfig = procStats._config
                if pConfig.restart:
                    restarted[procStats] = pConfig

        # Now that we've found all of the stragglers, check to see
        # what really is missing or not.
        missing = []
        for procStat in self._deviceStats.processStats:
            if procStat not in afterByConfig:
                missing.append(procStat._config)

        # For historical reasons, return the beforeByConfig
        beforeByConfig = reverseDict(self._deviceStats._pidToProcess)

        return (afterByConfig, afterPidToProcessStats,
                beforeByConfig, newPids, restarted, deadPids,
                missing)

    def _splitPStatMatchers(self):
        pStatsWArgsAndSums = []; pStatsWoArgs = []
        for pStat in self._deviceStats.processStats:
            if pStat._config.ignoreParameters:
                pStatsWoArgs.append(pStat)
            else:
                nameList = pStat._config.name.split()
                if len(nameList) < 2: # (name, md5sum)
                    nameList = (nameList[0], md5('').hexdigest())

                possibleMd5Sum = nameList[-1].lower()
                if IS_MD5.match(possibleMd5Sum):
                    pStatsWArgsAndSums.append(pStat)
        return pStatsWArgsAndSums, pStatsWoArgs

    @defer.inlineCallbacks
    def _fetchPerf(self):
        """
        Get performance data for all the monitored processes on a device

        @parameter results: results of SNMP table gets
        @type results: list of (success, result) tuples
        """
        self.state = ZenProcessTask.STATE_FETCH_PERF

        oids = []
        for pid in self._deviceStats.pids:
            oids.extend([CPU + str(pid), MEM + str(pid)])
        if oids:
            singleOids = set()
            results = {}
            oidsToTest = oids
            chunkSize = self._maxOidsPerRequest
            while oidsToTest:
                for oidChunk in chunk(oids, chunkSize):
                    try:
                        log.debug("%s fetching oid(s) %s" % (self._devId, oidChunk))
                        result = yield self._get(oidChunk)
                        results.update(result)
                    except (error.TimeoutError, Snmpv3Error) as e:
                        log.debug("error reading oid(s) %s - $s " % (oidChunk, e))
                        singleOids.update(oidChunk)
                oidsToTest = []
                if singleOids and chunkSize > 1:
                    chunkSize = 1
                    log.debug("running oids for %s in single mode %s" % (self._devId, singleOids))
                    oidsToTest = list(singleOids)
            self._storePerfStats(results)

    def _storePerfStats(self, results):
        """
        Save the process performance data in RRD files

        @parameter results: results of SNMP table gets
        @type results: list of {oid:value} dictionaries
        @parameter device: proxy object to the remote computer
        @type device: Device object
        """
        self.state = ZenProcessTask.STATE_STORE_PERF
        byConf = reverseDict(self._deviceStats._pidToProcess)
        for procStat, pids in byConf.items():
            if len(pids) != 1:
                log.debug("There are %d pids by the name %s - %s",
                          len(pids), procStat._config.name, procStat._config.originalName)
            procName = procStat._config.name
            for pid in pids:
                cpu = results.get(CPU + str(pid), None)
                mem = results.get(MEM + str(pid), None)
                procStat.updateCpu(pid, cpu)
                procStat.updateMemory(pid, mem)
            self._save(procName, 'cpu_cpu', procStat.getCpu(),
                       'DERIVE', min=0)
            self._save(procName, 'mem_mem',
                       procStat.getMemory() * 1024, 'GAUGE')
        return results

    def _getTables(self, oids):
        """
        Perform SNMP getTable for specified OIDs

        @parameter oids: OIDs to gather
        @type oids: list of strings
        @return: Twisted deferred
        @rtype: Twisted deferred
        """
        repetitions = self._maxOidsPerRequest / len(oids)
        t = self.snmpProxy.getTable(oids,
                                    timeout=self.snmpConnInfo.zSnmpTimeout,
                                    retryCount=self.snmpConnInfo.zSnmpTries,
                                    maxRepetitions=repetitions,
                                    limit=sys.maxint)
        return t

    def _get(self, oids):
        """
        Perform SNMP get for specified OIDs

        @parameter oids: OIDs to gather
        @type oids: list of strings
        @return: Twisted deferred
        @rtype: Twisted deferred
        """
        return self.snmpProxy.get(oids,
                                  self.snmpConnInfo.zSnmpTimeout,
                                  self.snmpConnInfo.zSnmpTries)

    def openProxy(self):
        """
        Create a connection to the remote device
        """
        self.state = ZenProcessTask.STATE_CONNECTING
        if (self.snmpProxy is None or
            self.snmpProxy.snmpConnInfo != self.snmpConnInfo):
            self.snmpProxy = self.snmpConnInfo.createSession()
            self.snmpProxy.open()

    def _close(self):
        """
        Close down the connection to the remote device
        """
        if self.snmpProxy:
            self.snmpProxy.close()
        self.snmpProxy = None


    def _showProcessList(self, procs):
        """
        Display the processes in a sane manner.

        @parameter procs: list of (pid, (name, args))
        @type procs: list of tuples
        """
        device_name = self._devId
        proc_list = ['%s %s %s' % (pid, name, args) for pid, (name, args) in sorted(procs)]
        proc_list.append('')
        log.info("#===== Processes on %s:\n%s", device_name, '\n'.join(proc_list))


    def _sendSnmpError(self, message, eventKey=None, **kwargs):
        event = self.statusEvent.copy()
        event.update(kwargs)
        self._eventService.sendEvent(event,
                                     eventClass=Status_Snmp,
                                     device=self._devId,
                                     severity=Event.Error,
                                     eventKey=eventKey,
                                     summary=message)

    def _clearSnmpError(self, message, eventKey=None):
        """
        Send an event to clear other events.

        @parameter message: clear text
        @type message: string
        """
        self._eventService.sendEvent(self.statusEvent,
                                     eventClass=Status_Snmp,
                                     device=self._devId,
                                     summary=message,
                                     agent='zenprocess',
                                     eventKey=eventKey,
                                     severity=Event.Clear)

    def _save(self, pidName, statName, value, rrdType, min='U'):
        """
        Save a value into an RRD file

        @param pidName: process id of the monitored process
        @type pidName: string
        @param statName: metric name
        @type statName: string
        @param value: data to be stored
        @type value: number
        @param rrdType: RRD data type (eg ABSOLUTE, DERIVE, COUNTER)
        @type rrdType: string
        """
        deviceName = self._devId
        path = 'Devices/%s/os/processes/%s/%s' % (deviceName, pidName, statName)
        try:
            self._dataService.writeRRD(path, value, rrdType, min=min)
        except Exception, ex:
            summary = "Unable to save data for process-monitor RRD %s" %\
                      path
            log.critical(summary)

            message = "Data was value= %s, type=%s" %\
                      ( value, rrdType )
            log.critical(message)
            log.exception(ex)

            import traceback

            trace_info = traceback.format_exc()

            self._eventService.sendEvent(dict(
                dedupid="%s|%s" % (self._preferences.options.monitor,
                                   'RRD write failure'),
                severity=Event.Critical,
                device=self._preferences.options.monitor,
                eventClass=Status_Perf,
                component="RRD",
                pidName=pidName,
                statName=statName,
                path=path,
                message=message,
                traceback=trace_info,
                summary=summary))


def mapResultsToDicts(showrawtables, results):
    """
    Parse the process tables and reconstruct the list of processes
    that are on the device.

    @parameter showrawtables: log the raw table info?
    @type showrawtables: boolean
    @parameter results: results of SNMP table gets ie (OID + pid, value)
    @type results: dictionary of dictionaries
    @return: maps relating names and pids to each other
    @rtype: dictionary, list of tuples
    """

    def extract(dictionary, oid, value):
        """
        Helper function to extract SNMP table data.
        """
        pid = int(oid.split('.')[-1])
        dictionary[pid] = value.strip()

    names, paths, args = {}, {}, {}
    if showrawtables:
        log.info("NAMETABLE = %r", results[NAMETABLE])
    for row in results[NAMETABLE].items():
        extract(names, *row)

    if showrawtables:
        log.info("PATHTABLE = %r", results[PATHTABLE])
    for row in results[PATHTABLE].items():
        extract(paths, *row)

    if showrawtables:
        log.info("ARGSTABLE = %r", results[ARGSTABLE])
    for row in results[ARGSTABLE].items():
        extract(args, *row)

    procs = []
    for pid, name in names.items():
        path = paths.get(pid, '')
        if path and path.find('\\') == -1:
            name = path
        arg = args.get(pid, '')
        procs.append((pid, (name, arg) ))

    return args, procs


def reverseDict(d):
    """
    Return a dictionary with keys and values swapped:
    all values are lists to handle the different keys mapping to the same value
    """
    result = {}
    for a, v in d.items():
        result.setdefault(v, []).append(a)
    return result


def chunk(lst, n):
    """
    Break lst into n-sized chunks
    """
    return [lst[i:i + n] for i in range(0, len(lst), n)]

# Collector Daemon Main entry point
#
if __name__ == '__main__':
    myPreferences = ZenProcessPreferences()

    myTaskFactory = SimpleTaskFactory(ZenProcessTask)
    myTaskSplitter = SimpleTaskSplitter(myTaskFactory)
    daemon = CollectorDaemon(myPreferences, myTaskSplitter, ConfigListener())
    daemon.run()
