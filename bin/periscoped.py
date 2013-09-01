#*-*coding: utf-8 *-*
#!/usr/bin/python2.7

import logging
import mimetypes
import os
import sqlite3
from datetime import datetime, timedelta
import md5
import time

from optparse import OptionParser
import periscope

import ConfigParser

class PeriscopedDb(object):
  def __init__(self, full_dbname, log=logging.getLogger(__name__)):
    self.log = log
    self.log.info("Using database '%s'"%(full_dbname))
    self.conn = sqlite3.connect(full_dbname)
    self.create_db()

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

class Periscoped(object):

  def __init__(self, options):
    self.supported_formats = 'video/x-msvideo', 'video/quicktime', 'video/x-matroska', 'video/mp4'
    self.options=options
    self.log = logging.getLogger(__name__)
    self.init_logger()
    
    self.cache_folder = self.get_cache_folder()
    self.log.debug("Cache folder : '%s'"%(self.cache_folder))
    self.config = ConfigParser.SafeConfigParser({"lang": "", "plugins" : "" })
    self.config_file = os.path.join(self.cache_folder, "config")

    if os.path.exists(self.config_file):
      self.config.read(self.config_file)
    else:
      raise Exception("config file %s does not exists"%(self.config_file))

    self.db=self.init_db()

  def init_db(self):
    db_name="periscoped"
    if self.options.db_name is not None:
      db_name = self.options.db_name[0]
    full_dbname = "%s.%s"%(os.path.join(self.cache_folder, db_name),'sqlite')
    db = PeriscopedDb(full_dbname)
    return db

  def init_logger(self):
    if self.options.debug :
      logging.basicConfig(level=logging.DEBUG)
    elif self.options.quiet :
      logging.basicConfig(level=logging.WARN)
    else :
      logging.basicConfig(level=logging.INFO)

  def get_cache_folder(self):
    home = os.path.expanduser("~")
    home = os.path.expanduser("/tmp")
    return os.path.join(home, ".config", "periscope")


  def recursive_import(self, path, force=False):
    files = []
    if os.path.isdir(path):
      for e in os.listdir(path):
        self.recursive_import(os.path.join(path, e), force)
    elif os.path.isfile(path):
      # Add mkv mimetype to the list
      self.insert_file(path, force)
  
  def insert_file(self, path, force=False):
    mimetypes.add_type("video/x-matroska", ".mkv")
    mimetype = mimetypes.guess_type(path)[0]
    if mimetype in self.supported_formats:
      self.log.debug("Importing '%s'"%(path))
      self.save_file(path, 0, not force)

  def get_short_filename(self, path):
      return os.path.splitext(path)[0]
  
  def has_sub(self, path):
      basepath = self.get_short_filename(path)
      return (os.path.exists(basepath+'.srt') or os.path.exists(basepath + '.sub')) 

  def save_file(self, path, next_in, upsert=True):
    basepath = self.get_short_filename(path)
    ash = md5.new(basepath).hexdigest()
    has_sub = self.has_sub(path)
    last_seen = datetime.utcnow()
    next_run = last_seen + timedelta(minutes=next_in)
    try:
      if upsert==True:
        #self.log.debug("upsERT")
        self.db.upsert(ash, path, has_sub, last_seen, next_in, next_run)
      else:
        self.db.insert_or_update(ash, path, has_sub, last_seen, next_in, next_run)

    except Exception, e:
      self.log.error("Path '%s' threw an exception : %s"%(path, e))

  def import_lib(self, lib_folder):
    self.log.info("Importing '%s'"%(lib_folder))
    force = self.options.force is not None and self.options.force
    self.log.debug("Force : %s"%(force))
    self.recursive_import(lib_folder, force)



  def run(self):
    self.log.info("Running subtitle downloader")
    p = periscope.Periscope(self.cache_folder)
    while True:
      #fetch files without subtitles
      rows = [row for row in self.db.conn.execute('''
        select path, next_in
        from files where has_sub=0 
        and 
        (
         datetime(next_run) <= datetime('now')
         or next_run is null
        )
      ''')]
      self.log.info("Running subtitles search for %s items"%(len(rows)))
      subs = []
      for row in rows:
        sub=None
        #p.downloadSubtitle(row[0], p.preferedLanguages)
        self.save_file(row[0], row[1]+10, False)
        if sub is not None:
          subs.append(sub)
       
      self.log.info("Running subtitles search for %s items"%(len(rows)))
      self.log.info("*"*50)
      self.log.info("Periscoped %s subtitles" %len(subs))
      for s in subs:
        self.log.info(s['lang'] + " - " + s['subtitlepath'])
      self.log.info("*"*50)

      self.log.info("Waiting for next iteration")
      time.sleep(10*60)
      self.log.info(s['lang'] + " - " + s['subtitlepath'])
      self.log.info("*"*50)

      self.log.info("Waiting for next iteration")
      time.sleep(10*60)

  def main(self):
    self.log.info("Hello Periscoped")
    if self.options.import_lib:
      self.import_lib(self.options.import_lib[0])
    if self.options.run:
      self.run()


def main():
  '''Download subtitles'''
  # parse command line options
  parser = OptionParser("usage: %prog [options] file1 file2", version = periscope.VERSION)

  parser.add_option("--cache-folder", action="store", type="string", dest="cache_folder", help="location of the periscope cache/config folder (default is ~/.config/periscope)")
  parser.add_option("--quiet", action="store_true", dest="quiet", help="run in quiet mode (only show warn and error messages)")
  parser.add_option("--debug", action="store_true", dest="debug", help="set the logging level to debug")
  parser.add_option("--db", action="append", dest="db_name", help="database name")

  parser.add_option("--import", action="append", dest="import_lib", help="import video library")
  parser.add_option("--run", action="store_true", dest="run", help="run the subtitle downloader")
  parser.add_option("--force", action="store_true", dest="force", help="force the operation")


  (options, args) = parser.parse_args()

  p = Periscoped(options)
  p.main()


if __name__ == "__main__":
  main()
