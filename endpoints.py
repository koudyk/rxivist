"""Functions linked directly to functionality called from API endpoints.

"""

import bottle

import config
import db
import helpers
import models


def get_categories(connection):
  """Fetches a list of all known bioRxiv categories.

  bioRxiv separates all papers into categories (or "collections"), such
  as "bioinformatics", "genomics", etc. This function lists all the ones
  we've pulled from the site so far. Rxivist uses the term "categories"
  instead of "collections" to make this more broadly applicable in case
  it's one day expanded to index more than just bioRxiv.

  Arguments:
    - connection: a Connection object with an active database session

  Returns:
    - a list of strings, one for each bioRxiv collection

  """
  results = []
  categories = connection.read("SELECT DISTINCT collection FROM articles ORDER BY collection;")
  for cat in categories:
    if len(cat) > 0:
      results.append(cat[0])
  return results

def paper_query(connection, q, categories, timeframe, metric, page, page_size):
  """Returns a list of the most downloaded papers that meet a given set of constraints.

  Arguments:
    - connection: a database Connection object.
    - q:  A search string to compare against article abstracts,
          titles and author names. (Title matches are weighted more heavily.)
    - categories: A list of bioRxiv categories the results can be in.
    - timeframe: A description of the range of dates on which to
          base the rankings (i.e. "alltime" or "lastmonth")
    - metric: Which article-level statistic to use when sorting results
    - page: Which page of the results to display (0-indexed)
    - page_size: How many entries should be returned
  Returns:
    - An list of Article objects that meet the search criteria, sorted by the
          specified metric in descending order.

  """
  # We build two queries, 'select' and 'countselect': one to get the
  # current page of results, and one to figure out the total number
  # of results
  select = "SELECT "
  if metric == "downloads":
    select += "r.downloads"
  elif metric == "twitter":
    select += "SUM(r.count)"
  select += ", a.id, a.url, a.title, a.abstract, a.collection, a.origin_month, a.origin_year, a.posted, a.doi"

  countselect = "SELECT COUNT(DISTINCT a.id)"
  params = ()

  query = ""
  if q != "": # if there's a text search specified
    params = (q,)
  query += " FROM articles AS a INNER JOIN "
  if metric == "twitter":
    query += "crossref_daily"
  elif metric == "downloads":
    query_times = {
      "alltime": "alltime_ranks",
      "ytd": "ytd_ranks",
      "lastmonth": "month_ranks",
    }
    query += query_times[timeframe]

  if metric == "twitter":
    query += " AS r ON r.doi=a.doi"
  elif metric == "downloads":
    query += " AS r ON r.article=a.id"

  if q != "":
    query += """, plainto_tsquery(%s) query,
    coalesce(setweight(a.title_vector, 'A') || setweight(a.abstract_vector, 'C') || setweight(a.author_vector, 'D')) totalvector
    """
  # add a WHERE clause if we need one:
  # (all-time twitter stats don't require it)
  if metric == "downloads" or (metric == "twitter" and timeframe != "alltime") or len(categories) > 0:
    query += " WHERE "
    if metric == "downloads":
      query += "r.downloads > 0"
      if q != "" or len(categories) > 0:
        query += " AND "
    if q != "":
      query += "query @@ totalvector "
      if len(categories) > 0 or (metric == "twitter" and timeframe != "alltime"):
        query += " AND "

    if len(categories) > 0:
      query += "collection=ANY(%s)"
      if q != "":
        params = (q,categories)
      else:
        params = (categories,)
      if metric == "twitter" and timeframe != "alltime":
        query += " AND "
    if metric == "twitter" and timeframe != "alltime":
      query += "r.source_date > now() - interval "
      query_times = {
        "day": 2,
        "week": 7,
        "month": 30,
        "year": 365
      }
      query += "'{} days' ".format(query_times[timeframe])
  # this is the last piece of the query we need for the one
  # that counts the total number of results
  countselect += query
  resp = connection.read(countselect, params)
  total = resp[0][0]
  # continue building the query to get the full list of results:
  if metric == "twitter":
    query += " GROUP BY a.id"
  query += " ORDER BY "
  if metric == "downloads":
    query += "r.rank ASC"
  elif metric == "twitter":
    query += "SUM(r.count) DESC"

  query += " LIMIT {}".format(page_size)
  if page > 0:
    query += " OFFSET {}".format(page * page_size)
  query += ";"
  select += query
  result = connection.read(select, params)
  results = [models.SearchResultArticle(a, connection) for a in result]
  return results, total

def author_rankings(connection, category=""):
  """Fetches a list of authors with the most cumulative downloads.

  Arguments:
    - connection: a database Connection object.
    - category: (Optionally) a single bioRxiv collection to base download rankings on.
  Returns:
    - A list of Author objects that meet the search criteria.

  """
  if category == "": # all time, all categories
    table = "detailed_author_ranks" # TODO: just make a category called "alltime"
    where = ""
    params = ()
  else:
    table = "detailed_author_ranks_category"
    where = "WHERE r.category=%s"
    params = (category,)
  query = """
    SELECT a.id, a.name, r.rank, r.downloads, r.tie
    FROM detailed_authors AS a
    INNER JOIN {} r ON a.id=r.author
    {}
    ORDER BY r.rank
    LIMIT {}
  """.format(table, where, config.author_ranks_limit)

  authors = connection.read(query, params)
  return [models.SearchResultAuthor(*a) for a in authors]

def author_details(connection, author_id):
  """Returns information about a single author, including a list of
      all their papers.

  Arguments:
    - connection: a database Connection object.
    - author_id: the Rxivist-issued ID of the author being queried.
  Returns:
    - An Author object containing information about that
        author's publications and contact info.

  """
  result = models.Author(author_id)
  result.GetInfo(connection)
  return result

def paper_details(connection, article_id):
  """Returns information about a single paper.

  Arguments:
    - connection: a database Connection object.
    - article_id: the ID given to the author being queried.
  Returns:
    - A Paper object containing details about the paper and
        its authors.

  """
  result = models.ArticleDetails(article_id, connection) # TODO: some of these functions put id first, some connection first
  return result

def paper_downloads(connection, a_id):
  """Returns time-series data from bioRxiv about how many
  times a paper's webpage and PDF have been downloaded.

  Arguments:
    - connection: a database Connection object.
    - a_id: the Rxivist-issued ID given to the paper being queried.
  Returns:
    - A list of months and the download stats for each month

  """
  result = models.Article(a_id)
  result.GetDetailedTraffic(connection)
  return {
    "query": {
      "id": a_id
    },
    "results": [{"month": x.month, "year": x.year, "downloads": x.downloads, "views": x.views} for x in result.traffic]
  }

def get_distribution(connection, category, metric):
  """Returns time-series data from bioRxiv about how many
  times a paper's webpage and PDF have been downloaded.

  Arguments:
    - connection: a database Connection object.
    - a_id: the Rxivist-issued ID given to the paper being queried.
  Returns:
    - A list of months and the download stats for each month

  """
  # "category" param can be either "author" or "paper"
  # "metric" param is (right now) limited to just "downloads"
  data = connection.read("SELECT bucket, count FROM download_distribution WHERE category=%s ORDER BY bucket", (category,))
  results = [(entry[0], entry[1]) for entry in data]
  averages = {}
  for avg in ["mean", "median"]:
    cat = "{}_{}".format(category, avg)
    answer = connection.read("SELECT count FROM download_distribution WHERE category=%s", (cat,))
    averages[avg] = answer[0][0]
  return results, averages

def site_stats(connection):
  """Returns a (very) brief summary of the information indexed by Rxivist

  Arguments:
    - connection: a database Connection object.
  Returns:
    - A dict with the total indexed papers and authors

  """

  # Counting up how many of each entity we have
  resp = connection.read("SELECT COUNT(id) FROM articles;")
  if len(resp) != 1 or len(resp[0]) != 1:
    paper_count = 0
  else:
    paper_count = resp[0][0]

  resp = connection.read("SELECT COUNT(id) FROM detailed_authors;")
  if len(resp) != 1 or len(resp[0]) != 1:
    author_count = 0
  else:
    author_count = resp[0][0]

  resp = connection.read("SELECT COUNT(id) FROM articles WHERE abstract IS NULL;")
  if len(resp) != 1 or len(resp[0]) != 1:
    no_abstract = 0
  else:
    no_abstract = resp[0][0]

  resp = connection.read("SELECT COUNT(id) FROM articles WHERE posted IS NULL;")
  if len(resp) != 1 or len(resp[0]) != 1:
    no_posted = 0
  else:
    no_posted = resp[0][0]

  outdated = {}
  resp = connection.read("SELECT collection, COUNT(id) FROM articles WHERE last_crawled < now() - interval %s GROUP BY collection ORDER BY collection;", (config.outdated_limit,))
  if len(resp) > 0:
    for entry in resp:
      if len(entry) < 2:
        continue # something fishy with this entry
      outdated[entry[0]] = entry[1]


  return {
    "papers_indexed": paper_count,
    "authors_indexed": author_count,
    "missing_abstract": no_abstract,
    "missing_date": no_posted,
    "outdated_count": outdated
  }