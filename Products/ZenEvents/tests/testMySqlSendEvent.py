import pdb
import unittest
from Queue import Queue
import Globals
import transaction

from Products.ZenUtils.ZCmdBase import ZCmdBase
zodb = ZCmdBase(noopts=True)

from Products.ZenEvents.MySqlSendEvent import MySqlSendEventThread 
from Products.ZenEvents.Event import Event
from Products.ZenEvents.Exceptions import *
from DbConnectionPool import DbConnectionPool

class MySqlSendEventThreadTest(unittest.TestCase):
    
    def setUp(self):
        zodb.getDataRoot()
        self.zem = zodb.dmd.ZenEventManager


    def tearDown(self):
        transaction.abort()
        cpool = DbConnectionPool()
        conn = cpool.get(backend=self.dmd.ZenEventManager.backend, 
                        host=self.dmd.ZenEventManager.host, 
                        port=self.dmd.ZenEventManager.port, 
                        username=self.dmd.ZenEventManager.username, 
                        password=self.dmd.ZenEventManager.password, 
                        database=self.dmd.ZenEventManager.database)
        curs = conn.cursor()
        try:
            curs.execute("truncate status")
        finally:
            curs.close()
            cpool.put(conn)
        zodb.closedb()
        self.zem = None


    def testInit(self):
        evthread = MySqlSendEventThread(self.zem)
        self.assert_(evthread.database == "127.0.0.1")
        self.assert_(evthread.detailTable == "detail")
        self.assert_(isinstance(evthread.getqueue(), Queue)) 
        

    def testSendEvent(self):
        evthread = MySqlSendEventThread(self.zem)
        queue = evthread.getqueue()
        evt = Event()
        evt.device = "dev.test.com"
        evt.eventClass = "TestEvent"
        evt.summary = "this is a test event"
        evt.severity = 3
        queue.put(evt)
        evthread.stop()
        evthread.run()
        evts = self.zem.getEventList(where="device='dev.test.com'")
        self.assert_(len(evts) == 1)
        self.assert_(evts[0].summary == evt.summary)

        

if __name__ == "__main__":
    unittest.main()


