import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

class Connection(object):
  def __init__(self, host, db, user, password):
    dbname = db
    self.db = None
    self._ensure_database_exists(dbname, host, user, password)

    params = 'host={} dbname={} user={} password={}'.format(host, dbname, user, password)
    self.db = psycopg2.connect(params)
    self.db.set_session(autocommit=True)
    self.cursor = self.db.cursor()

    self._ensure_tables_exist()

  def _ensure_database_exists(self, dbname, host, user, password):
    params = 'host={} dbname={} user={} password={}'.format(host, dbname, user, password)
    db = psycopg2.connect(params)
    db.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT) # for creating DB
    cursor = db.cursor()
    cursor.execute("SELECT datname FROM pg_database WHERE datistemplate = false;")
    for result in cursor:
      if result[0] == dbname: break
    else:
      cursor.execute("CREATE DATABASE {};".format(dbname))
    db.close()

  def _ensure_tables_exist(self):
    self.cursor.execute("CREATE TABLE IF NOT EXISTS articles (id SERIAL PRIMARY KEY, url text UNIQUE, title text NOT NULL, abstract text, doi text UNIQUE, origin_month integer, origin_year integer, collection text, title_vector tsvector, abstract_vector tsvector, author_vector tsvector, last_crawled DATE NOT NULL DEFAULT CURRENT_DATE);")
    self.cursor.execute("CREATE TABLE IF NOT EXISTS authors (id SERIAL PRIMARY KEY, given text NOT NULL, surname text, UNIQUE (given, surname));")
    self.cursor.execute("CREATE TABLE IF NOT EXISTS article_authors (id SERIAL PRIMARY KEY, article integer NOT NULL, author integer NOT NULL, UNIQUE (article, author));")
    self.cursor.execute("CREATE TABLE IF NOT EXISTS article_traffic (id SERIAL PRIMARY KEY, article integer NOT NULL, month integer, year integer NOT NULL, abstract integer, pdf integer, UNIQUE (article, month, year));")

    self.cursor.execute("CREATE TABLE IF NOT EXISTS altmetric_daily (id SERIAL PRIMARY KEY, article integer, crawled DATE NOT NULL DEFAULT CURRENT_DATE, score integer, day_score integer, week_score integer, tweets integer, altmetric_id integer);")

    self.cursor.execute("CREATE TABLE IF NOT EXISTS alltime_ranks (article integer PRIMARY KEY, rank integer NOT NULL, downloads integer NOT NULL);")
    self.cursor.execute("CREATE TABLE IF NOT EXISTS alltime_ranks_working (article integer PRIMARY KEY, rank integer NOT NULL, downloads integer NOT NULL);")
    self.cursor.execute("CREATE TABLE IF NOT EXISTS category_ranks (article integer PRIMARY KEY, rank integer NOT NULL);")
    self.cursor.execute("CREATE TABLE IF NOT EXISTS category_ranks_working (article integer PRIMARY KEY, rank integer NOT NULL);")
    self.cursor.execute("CREATE TABLE IF NOT EXISTS bounce_ranks (article integer PRIMARY KEY, rank integer NOT NULL, rate NUMERIC(6,5) NOT NULL);")
    self.cursor.execute("CREATE TABLE IF NOT EXISTS bounce_ranks_working (article integer PRIMARY KEY, rank integer NOT NULL, rate NUMERIC(6,5) NOT NULL);")
    self.cursor.execute("CREATE TABLE IF NOT EXISTS ytd_ranks (article integer PRIMARY KEY, rank integer NOT NULL, downloads integer NOT NULL);")
    self.cursor.execute("CREATE TABLE IF NOT EXISTS ytd_ranks_working      (article integer PRIMARY KEY, rank integer NOT NULL, downloads integer NOT NULL);")
    self.cursor.execute("CREATE TABLE IF NOT EXISTS month_ranks            (article integer PRIMARY KEY, rank integer NOT NULL, downloads integer NOT NULL);")
    self.cursor.execute("CREATE TABLE IF NOT EXISTS month_ranks_working    (article integer PRIMARY KEY, rank integer NOT NULL, downloads integer NOT NULL);")
    self.cursor.execute("CREATE TABLE IF NOT EXISTS hotness_ranks          (article integer PRIMARY KEY, rank integer, score integer NOT NULL);")
    self.cursor.execute("CREATE TABLE IF NOT EXISTS hotness_ranks_working  (article integer PRIMARY KEY, rank integer, score integer NOT NULL);")
    self.cursor.execute("CREATE TABLE IF NOT EXISTS author_ranks           (author integer PRIMARY KEY, rank integer NOT NULL, tie boolean, downloads integer NOT NULL);")
    self.cursor.execute("CREATE TABLE IF NOT EXISTS author_ranks_working   (author integer PRIMARY KEY, rank integer NOT NULL, tie boolean, downloads integer NOT NULL);")
    self.cursor.execute("CREATE TABLE IF NOT EXISTS author_ranks_category   (id SERIAL PRIMARY KEY, author integer, category text NOT NULL, rank integer NOT NULL, tie boolean, downloads integer NOT NULL, UNIQUE (author, category));") # TODO: can we ditch the SERIAL id and do a composite key here?
    self.cursor.execute("CREATE TABLE IF NOT EXISTS author_ranks_category_working   (id SERIAL PRIMARY KEY, author integer, category text NOT NULL,  rank integer NOT NULL, tie boolean, downloads integer NOT NULL, UNIQUE (author, category));")

    self.cursor.execute("CREATE TABLE IF NOT EXISTS download_distribution (id SERIAL PRIMARY KEY, bucket integer NOT NULL, count integer NOT NULL, category text NOT NULL);")
    self.db.commit()

  def _clear_out(self):
    # NOTE: DON'T DO THIS UNLESS YOU REALLY WANT ALL YOUR STUFF GONE
    for table in ["articles", "authors", "article_authors",
       "article_traffic", "alltime_ranks", "alltime_ranks_working",
       "bounce_ranks", "bounce_ranks_working"]:
      self.cursor.execute("TRUNCATE TABLE {};".format(table))
    self.db.commit()
    # Other NOTE: This won't reset the ID numbers in each table

  def __del__(self):
    if self.db is not None:
      self.db.close()
