# Elasticsearch with the analysis plugins the catalog's languages need.
#
# analysis-icu  - `icu_folding`, which folds the letters `asciifolding` leaves
#                 alone (Polish 'ł', Turkish 'ı', Scandinavian 'ø'), so a query
#                 typed without diacritics still finds the book.
# analysis-stempel - Polish stemming; without it Polish text is only lowercased
#                 and folded, and "książki" never matches "książka".
#
# Both are optional at runtime: app/es_client.py detects what the cluster has
# and degrades the analysis chain instead of failing to build an index.
FROM docker.elastic.co/elasticsearch/elasticsearch:8.17.4

RUN elasticsearch-plugin install --batch analysis-icu \
    && elasticsearch-plugin install --batch analysis-stempel
