import logging
from threading import Thread

class ZenZopeThread(Thread):
    """ 
    Thread running inside zope that has its own read-only connection to the db.
    """

    def __init__(self):
        Thread.__init__(self)
        self.setDaemon(1)


    def opendb(self):
        """Open a connection to the zope database.
        """
        try:
            from Zope2 import DB
            self.conn = DB.open()
            root = self.conn.root()
            self.app  = root['Application']
        except:
            logging.exception("failed to start thread %s", 
                                self.__class__.__name__)

    def syncdb(self):
        """Sync the connection to the zope database.
        """
        self.conn.sync()


    def closedb(self):
        """Abort our transaction (we are read-only) and close connection.
        """
        try:
            import transaction
            transaction.abort()
            self.conn.close() 
        except:
            pass
