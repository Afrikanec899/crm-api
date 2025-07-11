import hashlib
import logging
from functools import cached_property

from django.core.cache import caches
from django.core.paginator import Paginator
from django.db import connection

from rest_framework.pagination import LimitOffsetPagination

# from django.utils import functional


logger = logging.getLogger(__name__)


class LargeTablePaginator(Paginator):
    @cached_property
    def count(self):
        query = self.object_list.query
        if not query.where:
            try:
                cursor = connection.cursor()
                cursor.execute('SELECT reltuples FROM pg_class WHERE relname = %s', [query.model._meta.db_table])
                count = int(cursor.fetchone()[0])
                return count
            except Exception as e:  # noqa
                logger.warning(e)

        return super().count


def CachedCountQueryset(queryset, timeout=60 * 5, cache_name='default'):
    """
        Return copy of queryset with queryset.count() wrapped to cache result for `timeout` seconds.
    """
    cache = caches[cache_name]
    queryset = queryset._chain()
    real_count = queryset.count

    def count(queryset):
        cache_key = 'query-count:' + hashlib.md5(str(queryset.query).encode('utf8')).hexdigest()

        # return existing value, if any
        value = cache.get(cache_key)
        if value is not None:
            return value

        # cache new value
        value = real_count()
        cache.set(cache_key, value, timeout)
        return value

    queryset.count = count.__get__(queryset, type(queryset))
    return queryset


class CachedCountLimitOffsetPagination(LimitOffsetPagination):
    def paginate_queryset(self, queryset, *args, **kwargs):
        if hasattr(queryset, 'count'):
            queryset = CachedCountQueryset(queryset)
        return super().paginate_queryset(queryset, *args, **kwargs)
