# -*- coding: utf-8 -*-
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

  def delete(self, ash):
    with(self.conn) as conn:
      conn.execute(''' delete from files where hash = ? ''', [ash,])

class Periscoped(object):

  def __init__(self, options):
    self.supported_formats = 'video/x-msvideo', 'video/quicktime', 'video/x-matroska', 'video/mp4'
    self.options=options
    self.log = logging.getLogger(__name__)
    self.init_logger()
    
    self.cache_folder = self.get_cache_folder()
    self.log.debug("Cache folder : '%s'"%(self.cache_folder))
    self.config = ConfigParser.SafeConfigParser()

    self.read_config()
    self.db=self.init_db()

  def read_config(self):
    self.config_file = os.path.join(self.cache_folder, "config")
    if os.path.exists(self.config_file):
      self.config.read(self.config_file)
    else:
      raise Exception("config file %s does not exists"%(self.config_file))
    self.log.debug("Read configuration")

    self.log.debug("Trying to read key run_each")
    self.run_each=self.config.get("Periscoped","run_each")
    if self.run_each == "":
      self.run_each=10
      self.log.debug("Could not read key run_each. Using default value '%s'"%(self.run_each))
    else:
      self.log.debug("Read key run_each. Using value '%s'"%(self.run_each))
    self.run_each=int(self.run_each)

    self.retry_factor=self.config.get("Periscoped","retry_factor")
    if self.retry_factor == "":
      self.retry_factor=1.5
      self.log.debug("Could not read key retry_factor. Using default value '%s'"%(self.retry_factor))
    else:
      self.log.debug("Read key retry_factor. Using value '%s'"%(self.retry_factor))
    self.retry_factor=float(self.retry_factor)


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
    ash = self.get_hash(path)

    has_sub = self.has_sub(path)
    last_seen = datetime.utcnow()
    next_run = last_seen + timedelta(minutes=next_in)
    try:
      if upsert==True:
        self.db.upsert(ash, path, has_sub, last_seen, next_in, next_run)
      else:
        self.db.insert_or_update(ash, path, has_sub, last_seen, next_in, next_run)

    except Exception, e:
      self.log.error("Path '%s' threw an exception : %s"%(path, e))

  def get_hash(self, path):
    basepath = self.get_short_filename(path)
    return md5.new(basepath).hexdigest()

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
        sub=p.downloadSubtitle(row[0], p.preferedLanguages)
        next_in=int(row[1])
        # Sub found
        if sub is not None:
          subs.append(sub)
          next_in=None
        else:
          # sub not found increasing the time before retrying it.
          if next_in == 0:
            next_in=1
          next_in=self.retry_factor*next_in
          self.log.info("Could not find a subtitle. Retrying in %s min."%(self.run_each+next_in))
   
        self.save_file(row[0], next_in, False)
       
      self.log.info("*"*50)
      self.log.info("Periscoped %s subtitles" %len(subs))
      for s in subs:
        self.log.info(s['lang'] + " - " + s['subtitlepath'])
      self.log.info("*"*50)

      self.log.info("Waiting for next iteration (%s)"%(self.run_each))
      time.sleep(self.run_each*60)

  def purge(self):
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
        self.log.debug("Removing '%s' from local database"%(path))
        self.db.delete(ash)
        dropped+=1
    self.log.info("Purged %s files from locale database"%(dropped))

  def main(self):
    self.log.info("Hello Periscoped")
    if self.options.import_lib:
      self.import_lib(self.options.import_lib[0])
    if self.options.purge:
      self.purge()
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
  parser.add_option("--purge", action="store_true", dest="purge", help="delete non existing files from database")

  parser.add_option("--run", action="store_true", dest="run", help="run the subtitle downloader")
  parser.add_option("--force", action="store_true", dest="force", help="force the operation")


  (options, args) = parser.parse_args()

  p = Periscoped(options)
  p.main()


if __name__ == "__main__":
  main()
