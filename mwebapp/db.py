# -*- coding: utf-8 -*-
# __author__ = 'MingLei Ji'
import functools
import threading

from mwebapp.environ import Dict


class DBError(Exception):
    pass


class MultiColumnsError(DBError):
    pass


class _LasyConnection(object):
    def __init__(self, connect):
        self._connect = connect
        self.connection = None

    def cursor(self):
        if self.connection is None:
            connection = self._connect()
            self.connection = connection
        return self.connection.cursor()

    def commit(self):
        self.connection.commit()

    def rollback(self):
        self.connection.rollback()

    def cleanup(self):
        if self.connection:
            connection = self.connection
            self.connection = None
            connection.close()


class _DbCtx(threading.local):
    def __init__(self):
        self.connection = None

    def is_init(self):
        return not self.connection is None

    def init(self, connect):
        self.connection = _LasyConnection(connect)

    def cleanup(self):
        self.connection.cleanup()
        self.connection = None

    def cursor(self):
        return self.connection.cursor()


_db_ctx = _DbCtx()

connect = None

def create_engine(user, password, database, host='127.0.0.1', port=3306, **kw):
    if _db_ctx.is_init():
        raise DBError('Engine is already initialized.')
    import mysql.connector
    params = dict(user=user, password=password, database=database, host=host, port=port)
    defaults = dict(use_unicode=True, charset='utf8', collation='utf8_general_ci', autocommit=False)
    for k, v in defaults.items():
        params[k] = kw.pop(k, v)
    params.update(kw)
    params['buffered'] = True
    global connect
    connect = lambda: mysql.connector.connect(**params)
    _db_ctx.init(connect)


class ConnectionCtx(object):
    def __enter__(self):
        global _db_ctx
        self.should_cleanup = False
        if not _db_ctx.is_init():
            _db_ctx.init(connect)
            self.should_cleanup = True
        return self

    def __exit__(self, exctype, excvalue, traceback):
        global _db_ctx
        if self.should_cleanup:
            _db_ctx.cleanup()


def with_connection(func):
    @functools.wraps(func)
    def _wrapper(*args, **kw):
        with ConnectionCtx():
            return func(*args, **kw)

    return _wrapper


def _select(sql, first, *args):
    cursor = None
    sql = sql.replace('?', '%s')
    try:
        cursor = _db_ctx.cursor()
        cursor.execute(sql, args)
        if cursor.description:
            names = [x[0] for x in cursor.description]
        if first:
            values = cursor.fetchone()
            if not values:
                return None
            return Dict(names, values)
        return [Dict(names, x) for x in cursor.fetchall()]
    finally:
        if cursor:
            cursor.close()


def _update(sql, *args):
    cursor = None
    sql = sql.replace('?', '%s')
    try:
        cursor = _db_ctx.cursor()
        cursor.execute(sql, args)
        r = cursor.rowcount
        _db_ctx.connection.commit()
        return r
    finally:
        if cursor:
            cursor.close()


@with_connection
def select_one(sql, *args):
    return _select(sql, True, *args)


@with_connection
def select_int(sql, *args):
    d = _select(sql, True, *args)
    if len(d) != 1:
        raise MultiColumnsError('Expect only one column.')
    return d.values()[0]


@with_connection
def select(sql, *args):
    return _select(sql, False, *args)


@with_connection
def insert(table, **kw):
    cols, args = zip(*kw.items())
    sql = 'insert into `%s` (%s) values (%s)' % (
        table, ','.join(['`%s`' % col for col in cols]), ','.join(['?' for i in range(len(cols))]))
    return _update(sql, *args)


@with_connection
def update(sql, *args):
    return _update(sql, *args)


if __name__ == '__main__':
    create_engine('root', 'password', 'test')
    user_list = select('select * from user where id>?', 1000)
    for user in user_list:
        print(user)
