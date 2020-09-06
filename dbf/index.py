class Index(_Navigation):
    """
    non-persistent index for a table
    """

    def __init__(self, table, key):
        self._table = table
        self._values = []             # ordered list of values
        self._rec_by_val = []         # matching record numbers
        self._records = {}            # record numbers:values
        self.__doc__ = key.__doc__ or 'unknown'
        self._key = key
        self._previous_status = []
        for record in table:
            value = key(record)
            if value is DoNotIndex:
                continue
            rec_num = recno(record)
            if not isinstance(value, tuple):
                value = (value, )
            vindex = bisect_right(self._values, value)
            self._values.insert(vindex, value)
            self._rec_by_val.insert(vindex, rec_num)
            self._records[rec_num] = value
        table._indexen.add(self)

    def __call__(self, record):
        rec_num = recno(record)
        key = self.key(record)
        if rec_num in self._records:
            if self._records[rec_num] == key:
                return
            old_key = self._records[rec_num]
            vindex = bisect_left(self._values, old_key)
            self._values.pop(vindex)
            self._rec_by_val.pop(vindex)
            del self._records[rec_num]
            assert rec_num not in self._records
        if key == (DoNotIndex, ):
            return
        vindex = bisect_right(self._values, key)
        self._values.insert(vindex, key)
        self._rec_by_val.insert(vindex, rec_num)
        self._records[rec_num] = key

    def __contains__(self, data):
        if not isinstance(data, (Record, RecordTemplate, tuple, dict)):
            raise TypeError("%r is not a record, templace, tuple, nor dict" % (data, ))
        try:
            value = self.key(data)
            return value in self._values
        except Exception:
            for record in self:
                if record == data:
                    return True
            return False

    def __getitem__(self, key):
        '''if key is an integer, returns the matching record;
        if key is a [slice | string | tuple | record] returns a List;
        raises NotFoundError on failure'''
        if isinstance(key, baseinteger):
            count = len(self._values)
            if not -count <= key < count:
                raise NotFoundError("Record %d is not in list." % key)
            rec_num = self._rec_by_val[key]
            return self._table[rec_num]
        elif isinstance(key, slice):
            result = List()
            start, stop, step = key.start, key.stop, key.step
            if start is None: start = 0
            if stop is None: stop = len(self._rec_by_val)
            if step is None: step = 1
            if step < 0:
                start, stop = stop - 1, -(stop - start + 1)
            for loc in range(start, stop, step):
                record = self._table[self._rec_by_val[loc]]
                result._maybe_add(item=(self._table, self._rec_by_val[loc], result.key(record)))
            return result
        elif isinstance (key, (basestring, tuple, Record, RecordTemplate)):
            if isinstance(key, (Record, RecordTemplate)):
                key = self.key(key)
            elif isinstance(key, basestring):
                key = (key, )
            lo = self._search(key, where='left')
            hi = self._search(key, where='right')
            if lo == hi:
                raise NotFoundError(key)
            result = List(desc='match = %r' % (key, ))
            for loc in range(lo, hi):
                record = self._table[self._rec_by_val[loc]]
                result._maybe_add(item=(self._table, self._rec_by_val[loc], result.key(record)))
            return result
        else:
            raise TypeError('indices must be integers, match objects must by strings or tuples')

    def __enter__(self):
        self._table.__enter__()
        return self

    def __exit__(self, *exc_info):
        self._table.__exit__()
        return False

    def __iter__(self):
        return Iter(self)

    def __len__(self):
        return len(self._records)

    def _clear(self):
        """
        removes all entries from index
        """
        self._values[:] = []
        self._rec_by_val[:] = []
        self._records.clear()

    def _key(self, record):
        """
        table_name, record_number
        """
        self._still_valid_check()
        return source_table(record), recno(record)

    def _nav_check(self):
        """
        raises error if table is closed
        """
        if self._table._meta.status == CLOSED:
            raise DbfError('indexed table %s is closed' % self.filename)

    def _partial_match(self, target, match):
        target = target[:len(match)]
        if isinstance(match[-1], basestring):
            target = list(target)
            target[-1] = target[-1][:len(match[-1])]
            target = tuple(target)
        return target == match

    def _purge(self, rec_num):
        value = self._records.get(rec_num)
        if value is not None:
            vindex = bisect_left(self._values, value)
            del self._records[rec_num]
            self._values.pop(vindex)
            self._rec_by_val.pop(vindex)

    def _reindex(self):
        """
        reindexes all records
        """
        for record in self._table:
            self(record)

    def _search(self, match, lo=0, hi=None, where=None):
        if hi is None:
            hi = len(self._values)
        if where == 'left':
            return bisect_left(self._values, match, lo, hi)
        elif where == 'right':
            return bisect_right(self._values, match, lo, hi)

    def index(self, record, start=None, stop=None):
        """
        returns the index of record between start and stop
        start and stop default to the first and last record
        """
        if not isinstance(record, (Record, RecordTemplate, dict, tuple)):
            raise TypeError("x should be a record, template, dict, or tuple, not %r" % type(record))
        self._nav_check()
        if start is None:
            start = 0
        if stop is None:
            stop = len(self)
        for i in range(start, stop):
            if record == (self[i]):
                return i
        else:
            raise NotFoundError("dbf.Index.index(x): x not in Index", data=record)

    def index_search(self, match, start=None, stop=None, nearest=False, partial=False):
        """
        returns the index of match between start and stop
        start and stop default to the first and last record.
        if nearest is true returns the location of where the match should be
        otherwise raises NotFoundError
        """
        self._nav_check()
        if not isinstance(match, tuple):
            match = (match, )
        if start is None:
            start = 0
        if stop is None:
            stop = len(self)
        loc = self._search(match, start, stop, where='left')
        if loc == len(self._values):
            if nearest:
                return IndexLocation(loc, False)
            raise NotFoundError("dbf.Index.index_search(x): x not in index", data=match)
        if self._values[loc] == match \
        or partial and self._partial_match(self._values[loc], match):
            return IndexLocation(loc, True)
        elif nearest:
            return IndexLocation(loc, False)
        else:
            raise NotFoundError("dbf.Index.index_search(x): x not in Index", data=match)

    def key(self, record):
        result = self._key(record)
        if not isinstance(result, tuple):
            result = (result, )
        return result

    def query(self, criteria):
        """
        criteria is a callback that returns a truthy value for matching record
        """
        self._nav_check()
        return pql(self, criteria)

    def search(self, match, partial=False):
        """
        returns dbf.List of all (partially) matching records
        """
        self._nav_check()
        result = List()
        if not isinstance(match, tuple):
            match = (match, )
        loc = self._search(match, where='left')
        if loc == len(self._values):
            return result
        while loc < len(self._values) and self._values[loc] == match:
            record = self._table[self._rec_by_val[loc]]
            result._maybe_add(item=(self._table, self._rec_by_val[loc], result.key(record)))
            loc += 1
        if partial:
            while loc < len(self._values) and self._partial_match(self._values[loc], match):
                record = self._table[self._rec_by_val[loc]]
                result._maybe_add(item=(self._table, self._rec_by_val[loc], result.key(record)))
                loc += 1
        return result


class Relation(object):
    """
    establishes a relation between two dbf tables (not persistent)
    """

    relations = {}

    def __new__(cls, src, tgt, src_names=None, tgt_names=None):
        if (len(src) != 2 or  len(tgt) != 2):
            raise DbfError("Relation should be called with ((src_table, src_field), (tgt_table, tgt_field))")
        if src_names and len(src_names) !=2 or tgt_names and len(tgt_names) != 2:
            raise DbfError('src_names and tgt_names, if specified, must be ("table","field")')
        src_table, src_field = src
        tgt_table, tgt_field = tgt
        try:
            if isinstance(src_field, baseinteger):
                table, field = src_table, src_field
                src_field = table.field_names[field]
            else:
                src_table.field_names.index(src_field)
            if isinstance(tgt_field, baseinteger):
                table, field = tgt_table, tgt_field
                tgt_field = table.field_names[field]
            else:
                tgt_table.field_names.index(tgt_field)
        except (IndexError, ValueError):
            raise DbfError('%r not in %r' % (field, table)).from_exc(None)
        if src_names:
            src_table_name, src_field_name = src_names
        else:
            src_table_name, src_field_name = src_table.filename, src_field
            if src_table_name[-4:].lower() == '.dbf':
                src_table_name = src_table_name[:-4]
        if tgt_names:
            tgt_table_name, tgt_field_name = tgt_names
        else:
            tgt_table_name, tgt_field_name = tgt_table.filename, tgt_field
            if tgt_table_name[-4:].lower() == '.dbf':
                tgt_table_name = tgt_table_name[:-4]
        relation = cls.relations.get(((src_table, src_field), (tgt_table, tgt_field)))
        if relation is not None:
            return relation
        obj = object.__new__(cls)
        obj._src_table, obj._src_field = src_table, src_field
        obj._tgt_table, obj._tgt_field = tgt_table, tgt_field
        obj._src_table_name, obj._src_field_name = src_table_name, src_field_name
        obj._tgt_table_name, obj._tgt_field_name = tgt_table_name, tgt_field_name
        obj._tables = dict()
        cls.relations[((src_table, src_field), (tgt_table, tgt_field))] = obj
        return obj

    def __eq__(yo, other):
        if (yo.src_table == other.src_table
        and yo.src_field == other.src_field
        and yo.tgt_table == other.tgt_table
        and yo.tgt_field == other.tgt_field):
            return True
        return False

    def __getitem__(yo, record):
        """
        record should be from the source table
        """
        key = (record[yo.src_field], )
        try:
            return yo.index[key]
        except NotFoundError:
            return List(desc='%s not found' % key)

    def __hash__(yo):
        return hash((yo.src_table, yo.src_field, yo.tgt_table, yo.tgt_field))

    def __ne__(yo, other):
        if (yo.src_table != other.src_table
        or  yo.src_field != other.src_field
        or  yo.tgt_table != other.tgt_table
        or  yo.tgt_field != other.tgt_field):
            return True
        return False

    def __repr__(yo):
        return "Relation((%r, %r), (%r, %r))" % (yo.src_table_name, yo.src_field, yo.tgt_table_name, yo.tgt_field)

    def __str__(yo):
        return "%s:%s --> %s:%s" % (yo.src_table_name, yo.src_field_name, yo.tgt_table_name, yo.tgt_field_name)

    @property
    def src_table(yo):
        "name of source table"
        return yo._src_table

    @property
    def src_field(yo):
        "name of source field"
        return yo._src_field

    @property
    def src_table_name(yo):
        return yo._src_table_name

    @property
    def src_field_name(yo):
        return yo._src_field_name

    @property
    def tgt_table(yo):
        "name of target table"
        return yo._tgt_table

    @property
    def tgt_field(yo):
        "name of target field"
        return yo._tgt_field

    @property
    def tgt_table_name(yo):
        return yo._tgt_table_name

    @property
    def tgt_field_name(yo):
        return yo._tgt_field_name

    @LazyAttr
    def index(yo):
        def index(record, field=yo._tgt_field):
            return record[field]
        index.__doc__ = "%s:%s --> %s:%s" % (yo.src_table_name, yo.src_field_name, yo.tgt_table_name, yo.tgt_field_name)
        yo.index = yo._tgt_table.create_index(index)
        source = List(yo._src_table, key=lambda rec, field=yo._src_field: rec[field])
        target = List(yo._tgt_table, key=lambda rec, field=yo._tgt_field: rec[field])
        if len(source) != len(yo._src_table):
            yo._tables[yo._src_table] = 'many'
        else:
            yo._tables[yo._src_table] = 'one'
        if len(target) != len(yo._tgt_table):
            yo._tables[yo._tgt_table] = 'many'
        else:
            yo._tables[yo._tgt_table] = 'one'
        return yo.index

    def one_or_many(yo, table):
        yo.index    # make sure yo._tables has been populated
        try:
            if isinstance(table, basestring):
                table = (yo._src_table, yo._tgt_table)[yo._tgt_table_name == table]
            return yo._tables[table]
        except IndexError:
            raise NotFoundError("table %s not in relation" % table).from_exc(None)


class IndexFile(_Navigation):
    pass

class BytesType(object):

    def __init__(self, offset):
        self.offset = offset

    def __get__(self, inst, cls=None):
        if inst is None:
            return self
        start = self.offset
        end = start + self.size
        byte_data = inst._data[start:end]
        return self.from_bytes(byte_data)

    def __set__(self, inst, value):
        start = self.offset
        end = start + self.size
        byte_data = self.to_bytes(value)
        inst._data = inst._data[:start] + byte_data + inst._data[end:]


class IntBytesType(BytesType):
    """
    add big_endian and neg_one to __init__
    """

    def __init__(self, offset, big_endian=False, neg_one_is_none=False, one_based=False):
        self.offset = offset
        self.big_endian = big_endian
        self.neg_one_is_none = neg_one_is_none
        self.one_based = one_based

    def from_bytes(self, byte_data):
        if self.neg_one_is_none and byte_data == '\xff' * self.size:
            return None
        if self.big_endian:
            value = struct.unpack('>%s' % self.code, byte_data)[0]
        else:
            value = struct.unpack('<%s' % self.code, byte_data)[0]
        if self.one_based:
            # values are stored one based, convert to standard Python zero-base
            value -= 1
        return value

    def to_bytes(self, value):
        if value is None:
            if self.neg_one_is_none:
                return '\xff\xff'
            raise DbfError('unable to store None in %r' % self.__name__)
        limit = 2 ** (self.size * 8) - 1
        if self.one_based:
            limit -= 1
        if value > 2 ** limit:
            raise DataOverflowError("Maximum Integer size exceeded.  Possible: %d.  Attempted: %d" % (limit, value))
        if self.one_based:
            value += 1
        if self.big_endian:
            return struct.pack('>%s' % self.code, value)
        else:
            return struct.pack('<%s' % self.code, value)


class Int8(IntBytesType):
    """
    1-byte integer
    """

    size = 1
    code = 'B'


class Int16(IntBytesType):
    """
    2-byte integer
    """

    size = 2
    code = 'H'


class Int32(IntBytesType):
    """
    4-byte integer
    """

    size = 4
    code = 'L'


class Bytes(BytesType):

    def __init__(self, offset, size=0, fill_to=0, strip_null=False):
        if not (size or fill_to):
            raise DbfError("either size or fill_to must be specified")
        self.offset = offset
        self.size = size
        self.fill_to = fill_to
        self.strip_null = strip_null

    def from_bytes(self, byte_data):
        if self.strip_null:
            return byte_data.rstrip('\x00')
        else:
            return byte_data

    def to_bytes(self, value):
        if not isinstance(value, bytes):
            raise DbfError('value must be bytes [%r]' % value)
        if self.strip_null and len(value) < self.size:
            value += '\x00' * (self.size - len(value))
        return value


class DataBlock(object):
    """
    adds _data as a str to class
    binds variable name to BytesType descriptor
    """

    def __init__(self, size):
        self.size = size

    def __call__(self, cls):
        fields = []
        initialized = stringified = False
        for name, thing in cls.__dict__.items():
            if isinstance(thing, BytesType):
                thing.__name__ = name
                fields.append((name, thing))
            elif name in ('__init__', '__new__'):
                initialized = True
            elif name in ('__repr__', ):
                stringified = True
        fields.sort(key=lambda t: t[1].offset)
        for _, field in fields:
            offset = field.offset
            if not field.size:
                field.size = field.fill_to - offset
        total_field_size = field.offset + field.size
        if self.size and total_field_size > self.size:
            raise DbfError('Fields in %r are using %d bytes, but only %d allocated' % (cls, total_field_size, self.size))
        total_field_size = self.size or total_field_size
        cls._data = str('\x00' * total_field_size)
        cls.__len__ = lambda s: len(s._data)
        cls._size_ = total_field_size
        if not initialized:
            def init(self, data):
                if len(data) != self._size_:
                    raise Exception('%d bytes required, received %d' % (self._size_, len(data)))
                self._data = data
            cls.__init__ = init
        if not stringified:
            def repr(self):
                clauses = []
                for name, _ in fields:
                    value = getattr(self, name)
                    if isinstance(value, str) and len(value) > 12:
                        value = value[:9] + '...'
                    clauses.append('%s=%r' % (name, value))
                return ('%s(%s)' % (cls.__name__, ', '.join(clauses)))
            cls.__repr__ = repr
        return cls


class LruCache(object):
    """
    keep the most recent n items in the dict

    based on code from Raymond Hettinger: http://stackoverflow.com/a/8334739/208880
    """

    class Link(object):
        __slots__ = 'prev_link', 'next_link', 'key', 'value'
        def __init__(self, prev=None, next=None, key=None, value=None):
            self.prev_link, self.next_link, self.key, self.value = prev, next, key, value

        def __iter__(self):
            return iter((self.prev_link, self.next_link, self.key, self.value))

        def __repr__(self):
            value = self.value
            if isinstance(value, str) and len(value) > 15:
                value = value[:12] + '...'
            return 'Link<key=%r, value=%r>' % (self.key, value)

    def __init__(self, maxsize, func=None):
        self.maxsize = maxsize
        self.mapping = {}
        self.tail = self.Link()                      # oldest
        self.head = self.Link(self.tail)             # newest
        self.head.prev_link = self.tail
        self.func = func
        if func is not None:
            self.__name__ = func.__name__
            self.__doc__ = func.__doc__

    def __call__(self, *func):
        if self.func is None:
            [self.func] = func
            self.__name__ = func.__name__
            self.__doc__ = func.__doc__
            return self
        mapping, head, tail = self.mapping, self.head, self.tail
        link = mapping.get(func, head)
        if link is head:
            value = self.func(*func)
            if len(mapping) >= self.maxsize:
                old_prev, old_next, old_key, old_value = tail.next_link
                tail.next_link = old_next
                old_next.prev_link = tail
                del mapping[old_key]
            behind = head.prev_link
            link = self.Link(behind, head, func, value)
            mapping[func] = behind.next_link = head.prev_link = link
        else:
            link_prev, link_next, func, value = link
            link_prev.next_link = link_next
            link_next.prev_link = link_prev
            behind = head.prev_link
            behind.next_link = head.prev_link = link
            link.prev_link = behind
            link.next_link = head
        return value


class Idx(object):
    # default numeric storage is little-endian
    # numbers used as key values, and the 4-byte numbers in leaf nodes are big-endian

    @DataBlock(512)
    class Header(object):
        root_node = Int32(0)
        free_node_list = Int32(4, neg_one_is_none=True)
        file_size = Int32(8)
        key_length = Int16(12)
        index_options = Int8(14)
        index_signature = Int8(15)
        key_expr = Bytes(16, 220, strip_null=True)
        for_expr = Bytes(236, 220, strip_null=True)

    @DataBlock(512)
    class Node(object):
        attributes = Int16(0)
        num_keys = Int16(2)
        left_peer = Int32(4, neg_one_is_none=True)
        right_peer = Int32(8, neg_one_is_none=True)
        pool = Bytes(12, fill_to=512)
        def __init__(self, byte_data, node_key, record_key):
            if len(byte_data) != 512:
                raise DbfError("incomplete header: only received %d bytes" % len(byte_data))
            self._data = byte_data
            self._node_key = node_key
            self._record_key = record_key
        def is_leaf(self):
            return self.attributes in (2, 3)
        def is_root(self):
            return self.attributes in (1, 3)
        def is_interior(self):
            return self.attributes in (0, 1)
        def keys(self):
            result = []
            if self.is_leaf():
                key = self._record_key
            else:
                key = self._node_key
            key_len = key._size_
            for i in range(self.num_keys):
                start = i * key_len
                end = start + key_len
                result.append(key(self.pool[start:end]))
            return result

    def __init__(self, table, filename, size_limit=100):
        self.table = weakref.ref(table)
        self.filename = filename
        self.limit = size_limit
        with open(filename, 'rb') as idx:
            self.header = header = self.Header(idx.read(512))
            # offset = 512
            @DataBlock(header.key_length+4)
            class NodeKey(object):
                key = Bytes(0, header.key_length)
                rec_no = Int32(header.key_length, big_endian=True)
            @DataBlock(header.key_length+4)
            class RecordKey(object):
                key = Bytes(0, header.key_length)
                rec_no = Int32(header.key_length, big_endian=True, one_based=True)
            self.NodeKey = NodeKey
            self.RecordKey = RecordKey
            # set up root node
            idx.seek(header.root_node)
            self.root_node = self.Node(idx.read(512), self.NodeKey, self.RecordKey)
        # set up node reader
        self.read_node = LruCache(maxsize=size_limit, func=self.read_node)
        # set up iterating members
        self.current_node = None
        self.current_key = None

    def __iter__(self):
        # find the first leaf node
        table = self.table()
        if table is None:
            raise DbfError('the database linked to %r has been closed' % self.filename)
        node = self.root_node
        if not node.num_keys:
            yield
            return
        while "looking for a leaf":
            # travel the links down to the first leaf node
            if node.is_leaf():
                break
            node = self.read_node(node.keys()[0].rec_no)
        while "traversing nodes":
            for key in node.keys():
                yield table[key.rec_no]
            next_node = node.right_peer
            if next_node is None:
                return
            node = self.read_node(next_node)
    forward = __iter__

    def read_node(self, offset):
        """
        reads the sector indicated, and returns a Node object
        """
        with open(self.filename, 'rb') as idx:
            idx.seek(offset)
            return self.Node(idx.read(512), self.NodeKey, self.RecordKey)

    def backward(self):
        # find the last leaf node
        table = self.table()
        if table is None:
            raise DbfError('the database linked to %r has been closed' % self.filename)
        node = self.root_node
        if not node.num_keys:
            yield
            return
        while "looking for last leaf":
            # travel the links down to the last leaf node
            if node.is_leaf():
                break
            node = self.read_node(node.keys()[-1].rec_no)
        while "traversing nodes":
            for key in reversed(node.keys()):
                yield table[key.rec_no]
            prev_node = node.left_peer
            if prev_node is None:
                return
            node = self.read_node(prev_node)



