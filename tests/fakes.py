"""supabase-py 클라이언트의 최소 동작을 흉내내는 테스트 더블.

``conn.table("t").select(...).eq(...).order(...).limit(...).execute()`` 형태의
호출 체인과 ``conn.rpc(name, params).execute()`` 를 지원한다. 실제 Postgres
제약(check, unique 등)은 흉내내지 않는다.
"""

import itertools
import re


class Response:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


def _row_matches(row: dict, filters: list[tuple[str, str, object]]) -> bool:
    for kind, col, val in filters:
        if kind == "eq" and row.get(col) != val:
            return False
        if kind == "in" and row.get(col) not in val:
            return False
        if kind == "ilike":
            pattern = "^" + re.escape(val).replace("%", ".*").replace("_", ".") + "$"
            if not re.match(pattern, str(row.get(col) or ""), re.IGNORECASE):
                return False
    return True


class Query:
    def __init__(self, table: "Table", op: str, payload=None):
        self.table = table
        self.op = op
        self.payload = payload
        self.filters: list[tuple[str, str, object]] = []
        self.order_col = None
        self.order_desc = False
        self.limit_n = None
        self.count_mode = None

    def select(self, cols="*", count=None):
        self.op = "select"
        self.count_mode = count
        return self

    def eq(self, col, val):
        self.filters.append(("eq", col, val))
        return self

    def in_(self, col, vals):
        self.filters.append(("in", col, list(vals)))
        return self

    def ilike(self, col, pattern):
        self.filters.append(("ilike", col, pattern))
        return self

    def order(self, col, desc=False):
        self.order_col = col
        self.order_desc = desc
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def execute(self) -> Response:
        if self.op == "insert":
            return self._execute_insert()
        if self.op == "update":
            return self._execute_update()
        if self.op == "delete":
            return self._execute_delete()
        return self._execute_select()

    def _execute_insert(self) -> Response:
        exc = self.table.db._insert_failures.pop(self.table.name, None)
        if exc:
            raise exc
        rows = self.payload if isinstance(self.payload, list) else [self.payload]
        inserted = []
        for row in rows:
            row = dict(row)
            row.setdefault("id", self.table.db._next_id())
            self.table.rows.append(row)
            inserted.append(dict(row))
        return Response(inserted)

    def _execute_update(self) -> Response:
        updated = []
        for row in self.table.rows:
            if _row_matches(row, self.filters):
                row.update(self.payload)
                updated.append(dict(row))
        return Response(updated)

    def _execute_delete(self) -> Response:
        remaining, deleted = [], []
        for row in self.table.rows:
            (deleted if _row_matches(row, self.filters) else remaining).append(row)
        self.table.rows[:] = remaining
        return Response(deleted)

    def _execute_select(self) -> Response:
        matched = [r for r in self.table.rows if _row_matches(r, self.filters)]
        if self.order_col:
            matched = sorted(
                matched, key=lambda r: r.get(self.order_col), reverse=self.order_desc
            )
        count = len(matched) if self.count_mode == "exact" else None
        if self.limit_n is not None:
            matched = matched[: self.limit_n]
        return Response([dict(r) for r in matched], count=count)


class Table:
    def __init__(self, db: "FakeSupabase", name: str):
        self.db = db
        self.name = name
        self.rows: list[dict] = db.tables.setdefault(name, [])

    def select(self, cols="*", count=None):
        return Query(self, "select").select(cols, count=count)

    def insert(self, payload):
        return Query(self, "insert", payload)

    def update(self, payload):
        return Query(self, "update", payload)

    def delete(self):
        return Query(self, "delete")


class RpcCall:
    def __init__(self, value):
        self.value = value

    def execute(self) -> Response:
        return Response(self.value)


class FakeSupabase:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {}
        self._id_counter = itertools.count(1)
        self._rpc_handlers: dict[str, callable] = {}
        self._insert_failures: dict[str, Exception] = {}

    def _next_id(self) -> str:
        return f"fake-id-{next(self._id_counter)}"

    def table(self, name: str) -> Table:
        return Table(self, name)

    def set_rpc(self, name: str, handler) -> None:
        self._rpc_handlers[name] = handler

    def rpc(self, name: str, params: dict) -> RpcCall:
        handler = self._rpc_handlers.get(name)
        if handler is None:
            raise KeyError(f"no fake rpc handler registered for {name!r}")
        return RpcCall(handler(params))

    def fail_next_insert(self, table_name: str, exc: Exception) -> None:
        self._insert_failures[table_name] = exc


def install_order_seq_rpc(fake: FakeSupabase) -> None:
    """live_next_order_seq 를 live_broadcasts.last_order_seq 원자 증가로 흉내낸다."""

    def handler(params: dict) -> int:
        broadcast_id = params["p_broadcast_id"]
        for row in fake.tables.get("live_broadcasts", []):
            if row["id"] == broadcast_id:
                row["last_order_seq"] = row.get("last_order_seq", 0) + 1
                return row["last_order_seq"]
        raise KeyError(f"broadcast not found: {broadcast_id}")

    fake.set_rpc("live_next_order_seq", handler)
