#!/usr/bin/env python2.7

import os, sys
import logging, logging.config
import time
from datetime import datetime, timedelta
import mimetypes
import sqlite3
import md5
from optparse import OptionParser
import ConfigParser
import periscope
import pyinotify



class StdOutputsManager(object):
  """
  A class to turn off stderr and stdout.
  Mainly to get rid of unhandled periscope eception which make garbage in the logs.
  """
  class writer(object):
    """
    A dummy writer that just do nothing.
    """
    def write(self, data):
      pass
  def __init__(self):
    self.stderr = sys.stderr
    self.stdout = sys.stdout
    self.dummy_stdout = self.writer()
    self.dummy_stderr = self.writer()
  def turn_off_stds(self):
    sys.stdout = self.dummy_stdout
    sys.stderr = self.dummy_stderr
  def turn_on_stds(self):
    sys.stdout = self.stdout
    sys.stderr = self.stderr



class EventHandler(pyinotify.ProcessEvent):
  """
  Pyinotify events handler
  """

  def __init__(self, periscoped, log=None):
    self.log = log
    if self.log is None:
      self.log = logging.getLogger('eventhandler')
    self.p = periscoped
  
  def process_IN_CREATE(self, event):
    self.log.debug("IN_CREATE")
    self.new_file(event.pathname, 2)
  
  def process_IN_CLOSE_WRITE(self, event):
    self.log.debug("IN_CLOSE_WRITE")
    self.new_file(event.pathname, 0)

  def process_IN_MOVED_TO(self, event):
    self.log.debug("IN_MOVED_TO")
    self.new_file(event.pathname, 0)

  def process_IN_DELETE(self, event):
    path = event.pathname
    if self.p.is_format_supported(path):
      self.p.delete_file(path)
    elif self.p.is_sub(path):
      self.log.info("Sub removed : %s"%(path))
      #TODO: update corresponding entry with has_sub = 0 if no sub availables
    elif os.path.isdir(path):
      self.log.info("Folder removed : %s"%(path))
      self.p.delete_folder(path)

  def new_file(self, path, next_in):
    if self.p.is_sub(path):
      self.log.info("New sub arrived ! : %s"%(path))
    elif self.p.is_format_supported(path):
      self.log.info("New file arrived ! : %s"%(path))
      self.p.import_file(path, next_in)
    elif os.path.isdir(path):
      self.log.info("New folder created ! : %s"%(path))
      self.p.recursive_import(path)



class PeriscopedDb(object):
  def __init__(self, full_dbname, log=None):
    self.log = log
    if self.log is None:
      self.log = logging.getLogger('periscopeddb')

    self.log.debug("Using database '%s'"%(full_dbname))
    self.conn = sqlite3.connect(full_dbname)
    self.create_db()
    self.conn.text_factory = str

  def create_db(self):
    with self.conn as con: 
      con.execute('''
          create table if not exists Files(
            hash string not null primary key,
            path string not null,
            has_sub boolean not null,
            last_seen datetime,
            next_in int, 
            next_run datetime
          )
          ''')
      con.execute('''
      create index if not exists IX_file_path on Files(path)
          ''')
      con.execute('''
      create index if not exists IX_hash_path on Files(hash)
          ''')

  def insert_or_update(self, ash, path, has_sub, last_seen, next_in, next_run):
    """
    Insert a new row or update all its fields.
    """
    with self.conn as con: 
      con.execute("insert or replace into files(hash, path, has_sub, last_seen, next_in, next_run) values (?,?,?,?,?,?)", [ash, path, has_sub, last_seen, next_in, next_run])

  def upsert(self, ash, path, has_sub, last_seen, next_in, next_run):
    """
    Insert a new row or update its fields, excepted 'next_in' and 'next_run'
    """
    with self.conn as con: 
      con.execute('''
      insert or replace into files(hash, path, has_sub, last_seen, next_in, next_run)
      values (?,?,?,?,
        COALESCE( ( select next_in from files where hash = ?), ?),
        coalesce( ( select next_run from files where hash = ?), ?)
      )
      ''', 
      [ash, path, has_sub, last_seen, ash, next_in, ash, next_run]
      )

  def exists(self, ash):
    with self.conn as con: 
      rows = [row for row in con.execute('''select 1 from files where hash=?''', [ash]) ]
      return len(rows)>0


  def delete_file(self, ash):
    with(self.conn) as conn:
      conn.execute(''' delete from files where hash = ? ''', [ash,])
  
  def delete_folder(self, folder):
    with(self.conn) as conn:
      conn.execute(''' delete from files where file like '?%' ''', [folder,])


class Periscoped(object):
  """Main class for periscope-daemon"""
  def __init__(self, options, log=None):
    """Constructor for Perisope daemon """
    self.config = ConfigParser.SafeConfigParser()
    self.supported_formats = 'video/x-msvideo', 'video/quicktime', 'video/x-matroska', 'video/mp4'
    self.options=options
    self.init_logger()
    self.log = self.getLogger(log)
    
    self.check_config() # Will raise an exception if cannot reach the configs file
    self.config.read(self.config_file())
    
    self.log.debug("Cache folder : '%s'"%(self.get_cache_folder()))

    self.p = periscope.Periscope(self.get_cache_folder())
    self.read_config()
    self.db=self.init_db()
    mimetypes.add_type("video/x-matroska", ".mkv")
    
  def getLogger(self, log):
    """ Return the appropriate logger"""
    ret=log
    if ret is None:
      if self.options.isDaemon == True:
        ret = logging.getLogger('periscoped_daemon')
      else:
        ret = logging.getLogger('periscoped')
    return ret

  def config_file(self):
    """Returns the custom main config file in ~/.config/periscope-daemon or the default distributed one."""
    dist_config = os.path.join(os.path.dirname(__file__), 'config', 'daemon.conf')
    custom_config = os.path.join(self.get_cache_folder(),  "daemon.conf")
    if (os.path.exists(custom_config)):
      return custom_config
    else:
      return dist_config
  
  def logging_config_file(self):
    """Returns the custom logger config file in ~/.config/periscope-daemon or the default distributed one."""
    dist_config = os.path.join(os.path.dirname(__file__), 'config', 'logging.conf')
    custom_config = os.path.join(self.get_cache_folder() ,  "logging.conf")
    if (os.path.exists(custom_config)):
      return custom_config
    else:
      return dist_config


  def check_config(self):
    """Check the presence for config files and raise an exception if one is missing """
    if not os.path.exists(self.config_file()):
      raise Exception("config file %s does not exists"%(self.config_file()))
    if not os.path.exists(self.logging_config_file()):
      raise Exception("config file %s does not exists"%(self.logging_config_file()))

  def read_config(self):
    """Read and load the main configuration file"""
    self.log.debug("Read configuration")

    self.log.debug("Trying to read key run_each")
    self.run_each=self.config.get("DEFAULT","run_each")
    if self.run_each == "":
      self.run_each=10
      self.log.debug("Could not read key run_each. Using default value '%s'"%(self.run_each))
    else:
      self.log.debug("Read key run_each. Using value '%s'"%(self.run_each))
    self.run_each=int(self.run_each)

    self.retry_factor=self.config.get("DEFAULT","retry_factor")
    if self.retry_factor == "":
      self.retry_factor=1.5
      self.log.debug("Could not read key retry_factor. Using default value '%s'"%(self.retry_factor))
    else:
      self.log.debug("Read key retry_factor. Using value '%s'"%(self.retry_factor))
    self.retry_factor=float(self.retry_factor)

    self.langs=""
    try:
      self.langs=self.config.get("DEFAULT","lang")
      if self.langs == "":
        self.langs=self.p.preferedLanguages
        self.log.debug("Could not read key lang. Using default value '%s'"%(self.langs))
      else:
        self.langs=self.langs.split(',')
        self.log.debug("Read key lang. Using value '%s'"%(self.langs))
    except:
      self.langs=self.p.preferedLanguages
    if self.options.force is None:
      self.options.force=False


  def init_db(self):
    """initialize the database access object"""
    db_name="periscoped"
    if self.options.db_name is not None:
      db_name = self.options.db_name[0]
    full_dbname = "%s.%s"%(os.path.join(self.get_cache_folder(), db_name),'sqlite')
    db = PeriscopedDb(full_dbname, self.log)
    return db

  def init_logger(self):
    """Initialize the logger"""
    if (self.options.debug):
      logging.basicConfig(level=logging.DEBUG)
    elif (self.options.quiet):
      logging.basicConfig(level=logging.CRITICAL)
    else:
      logging.config.fileConfig(self.logging_config_file())


  def get_cache_folder(self):
    if not self.options.cache_folder:
      try:
        import xdg.BaseDirectory as bd
        self.options.cache_folder = os.path.join(bd.xdg_config_home, "periscope-daemon")
      except:
        home = os.path.expanduser("~")
        if home == "~":
          log.error("Could not generate a cache folder at the home location using XDG (freedesktop). You must specify a --cache-config folder where the cache and config will be located (always use the same folder).")
          exit()
        self.options.cache_folder = os.path.join(home, ".config", "periscope-daemon")
    return self.options.cache_folder


  def recursive_import(self, path, force=False):
    """Recursively import a folder and its subfolders"""
    files = []
    if os.path.isdir(path):
      for e in os.listdir(path):
        self.recursive_import(os.path.join(path, e), force)
    elif os.path.isfile(path):
      # Add mkv mimetype to the list
      self.import_file(path, 0, force)

  def is_format_supported(self, path):
    """Returns True if the file is a supported video format"""
    mimetype = mimetypes.guess_type(path)[0]
    return mimetype in self.supported_formats

  def import_file(self, path, next_in=0, force=False):
    """Import a video file"""
    if self.is_format_supported(path):
      self.log.debug("Importing '%s'"%(path))
      self.save_file(path, next_in, not force)


  def get_short_filename(self, path):
    """Returns the given path without extension"""
    return os.path.splitext(path)[0]

  def has_sub(self, path):
    """Returns True if the file has a subtitle file"""
    basepath = self.get_short_filename(path)
    found=False
    langs=['',]+[''+l for l in self.langs]
    exts=['srt','sub']
    found = False
    for lang in langs:
      for ext in exts:
        found=found or os.path.exists(basepath+lang+'.'+ext)
    return found
        
  def is_sub(self, path):
    """Returns True if the file is a subtitle file"""
    return path.endswith('.srt') or path.endswith('.sub')

  def save_file(self, path, next_in, upsert=True):
    basepath = self.get_short_filename(path)
    ash = self.get_hash(path)

    has_sub = self.has_sub(path)
    last_seen = datetime.utcnow()
    next_run = last_seen + timedelta(minutes=next_in)
    try:
      if self.db.exists(ash):
        self.log.debug("Updating '%s' (subtitle : %s)"%(path, has_sub))
      else:
        self.log.info("Adding new file '%s' (subtitle : %s)"%(path, has_sub))
      if upsert==True:
        self.db.upsert(ash, path, has_sub, last_seen, next_in, next_run)
      else:
        self.db.insert_or_update(ash, path, has_sub, last_seen, next_in, next_run)

    except Exception, e:
      self.log.error("Path '%s' threw an exception : %s"%(path, e))

  def get_hash(self, path):
    basepath = self.get_short_filename(path)
    return md5.new(basepath).hexdigest()

  def import_libs(self, lib_folders):
    """Import multiples path as a library folder"""
    for path in lib_folders:
      self.import_lib(path)

  def import_lib(self, lib_folder):
    """Import the given path as a library folder"""
    lib_folder=os.path.abspath(lib_folder)
    self.log.info("Importing '%s'"%(lib_folder))
    force = self.options.force is not None and self.options.force
    self.log.debug("Force : %s"%(force))
    self.recursive_import(lib_folder, force)

  def delete_file(self, path, ash=None):
    """Delete the given path from local db"""
    self.log.info("Removing '%s' from local database"%(path))
    h=ash
    if h is None:
      h = self.get_hash(path)
    self.db.delete_file(h)

  def run(self):
    omanager = StdOutputsManager()
    while True:
      #fetch files without subtitles
      rows = [row for row in self.db.conn.execute('''
        select path, next_in, hash
        from files where has_sub=0 
        and 
        (
         datetime(next_run) <= datetime('now')
         or next_run is null
        )
        and ( (has_sub = 0 and ? = 0) or ?=1)
      ''', [self.options.force, self.options.force])]

      if len(rows)>0:
        self.log.info("Emerging from the deep")
        self.log.info("Running subtitles search for %s items"%(len(rows)))
        self.log.info("Looking around...")

      subs = []
      for row in rows:
        path = row[0]
        if os.path.exists(path):
          self.log.debug("Searching '%s'"%(path))
          next_in=0
          if not self.has_sub(path):
            omanager.turn_off_stds()
            sub=self.p.downloadSubtitle(row[0], self.langs)
            omanager.turn_on_stds()
            next_in=int(row[1])
            # Sub found
            if sub is not None:
              subs.append(sub)
            else:
              # sub not found increasing the time before retrying it.
              if next_in == 0:
                next_in=1
              next_in=self.retry_factor*next_in
              self.log.debug("'%s' : Could not find a subtitle. Retrying in %s min."%(path, self.run_each+next_in)) 
          self.save_file(path, next_in, False)
        else:
          ash=row[2]
          self.delete_file(path, ash)

      if len(subs)>0:
        self.log.info("*"*50)
        self.log.info("Periscoped %s subtitles" %len(subs))
        for s in subs:
          self.log.info(s['lang'] + " - " + s['subtitlepath'])
        self.log.info("*"*50)
      if len(rows)>0:
        self.log.info("Going in immersion for %s minute(s)."%(self.run_each))
      time.sleep(self.run_each*60)

  def purge(self,folder=None):
    """
    Remove deleted files from library from database.
    """
    self.log.info("Cleaning database...")
    rows = [row for row in self.db.conn.execute('''select hash, path from files''')]
    dropped=0
    self.log.info("%s files in the database."%(len(rows)))
    for row in rows:
      ash = row[0]
      path=row[1]
      if not os.path.exists(path):
        self.delete_file(path, ash)
        dropped+=1
    self.log.info("Purged %s files from locale database"%(dropped))
    
    
  def watch(self, watched):
    for path in watched:
      self.add_watch(path)
    import asyncore
    asyncore.loop()

  def add_watch(self, watched):
    self.log.info("watching %s"%watched)
    wm = pyinotify.WatchManager()
    mask = pyinotify.IN_DELETE | pyinotify.IN_CREATE | pyinotify.IN_CLOSE_WRITE | pyinotify.IN_MOVED_TO # watched events
    handler = EventHandler(self, self.log)
    notifier = pyinotify.AsyncNotifier(wm, handler)
    wdd = wm.add_watch(watched, mask, rec=True)

  def main(self):
    self.log.info("Ready to sail the sea!")
    if self.options.import_lib:
      self.log.info("Starting import")
      self.import_libs(self.options.import_lib)
    if self.options.purge:
      self.log.info("Starting purge")
      self.purge()
    if self.options.watch:
      self.log.info("Starting watch")
      self.watch(self.options.watch)
    if self.options.run:
      self.run()


def main():
  '''Main method'''
  # parse command line options
  parser = OptionParser("usage: %prog [options] [folder]", version = periscope.VERSION)

  parser.add_option("--cache-folder", action="store", type="string", dest="cache_folder", help="location of the periscope cache/config folder (default is ~/.config/periscope)")
  parser.add_option("--quiet", action="store_true", dest="quiet", help="run in quiet mode (only show warn and error messages)")
  parser.add_option("--debug", action="store_true", dest="debug", help="set the logging level to debug")

  parser.add_option("--db", action="append", dest="db_name", help="database name")

  parser.add_option("--import", action="append", dest="import_lib", help="import video library")
  parser.add_option("--purge", action="store_true", dest="purge", help="delete non existing files from database")

  parser.add_option("--run", action="store_true", dest="run", help="run the subtitle downloader")
  parser.add_option("--watch", action="append", dest="watch", help="run the subtitle downloader")
  parser.add_option("--force", action="store_true", dest="force", help="force the operation")

  parser.add_option("--daemon", action="store_true", dest="isDaemon", help="Run as a daemon")

  (options, args) = parser.parse_args()

  p = Periscoped(options)
  p.main()


if __name__ == "__main__":
  main()
