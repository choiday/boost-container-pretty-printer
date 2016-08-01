# Pretty-printers for boost container.

# Copyright (C) 2008-2015 Free Software Foundation, Inc.

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import gdb
import itertools
import re
import sys

### Python 2 + Python 3 compatibility code

# Resources about compatibility:
#
#  * <http://pythonhosted.org/six/>: Documentation of the "six" module

# FIXME: The handling of e.g. std::basic_string (at least on char)
# probably needs updating to work with Python 3's new string rules.
#
# In particular, Python 3 has a separate type (called byte) for
# bytestrings, and a special b"" syntax for the byte literals; the old
# str() type has been redefined to always store Unicode text.
#
# We probably can't do much about this until this GDB PR is addressed:
# <https://sourceware.org/bugzilla/show_bug.cgi?id=17138>

if sys.version_info[0] > 2:
    ### Python 3 stuff
    Iterator = object
    # Python 3 folds these into the normal functions.
    imap = map
    izip = zip
    # Also, int subsumes long
    long = int
else:
    ### Python 2 stuff
    class Iterator:
        """Compatibility mixin for iterators

        Instead of writing next() methods for iterators, write
        __next__() methods and use this mixin to make them work in
        Python 2 as well as Python 3.

        Idea stolen from the "six" documentation:
        <http://pythonhosted.org/six/#six.Iterator>
        """

        def next(self):
            return self.__next__()

    # In Python 2, we still need these from itertools
    from itertools import imap, izip

# Try to use the new-style pretty-printing if available.
_use_gdb_pp = True
try:
    import gdb.printing
except ImportError:
    _use_gdb_pp = False

def find_type(orig, name):
    typ = orig.strip_typedefs()
    while True:
        # Use typ.name here instead of str(typ) to discard any const,etc.
        # qualifiers.  PR 67440.
        search = typ.name + '::' + name
        try:
            return gdb.lookup_type(search)
        except RuntimeError:
            pass
        # The type was not found, so try the superclass.  We only need
        # to check the first superclass, so we don't bother with
        # anything fancier here.
        field = typ.fields()[0]
        if not field.is_base_class:
            raise ValueError("Cannot find type %s::%s" % (str(orig), name))
        typ = field.type
        
class StringPrinter:
    "Print a boost::container::basic_string of some kind"

    def __init__(self, typename, val):
        self.val = val

    def to_string(self):
        # Make sure &string works, too.
        type = self.val.type
        if type.code == gdb.TYPE_CODE_REF:
            type = type.target ()

        # Calculate the length of the string so that to_string returns
        # the string according to length, not according to first null
        # encountered.
        ptr = None
        is_short = self.val['members_']['m_repr']['s']['h']['is_short']
        if is_short:
            length = self.val['members_']['m_repr']['s']['h']['length']
            ptr = self.val['members_']['m_repr']['s']['data']
        else:
            ptr = self.val['members_']['m_repr']['r'].address
            realtype = type.unqualified ().strip_typedefs ()
            reptype = gdb.lookup_type (str (realtype) + '::long_t').pointer ()
            header = ptr.cast(reptype)
            length = header.dereference ()['length']
            ptr = header.dereference ()['start']

        return ptr.string (length = length)

    def display_hint (self):
        return 'string'
class ListPrinter:
    "Print a list"
 
    class _iter (Iterator):
        def __init__(self, nodetype, valtype, head):
            self.nodetype = nodetype
            self.valtype = valtype
            self.base = head
            self.head = head.address
            self.count = 0
 
        def __iter__(self):
            return self
 
        def __next__(self):
            if self.base == self.head:
                raise StopIteration
            elt = self.base.cast(self.nodetype)
            self.base = elt.dereference()['next_']
            count = self.count
            self.count = self.count + 1
            return ('[%d]' % count, (elt + 1).cast(self.valtype).dereference())
 
    def __init__(self, typename, val):
        self.typename = typename
        self.val = val
 
    def children(self):
        nodetype = self.val['members_']['m_icont']['data_']['root_plus_size_']['m_header']['next_'].type
        nodetype = nodetype.strip_typedefs()
        return self._iter (nodetype, self.val.type.template_argument(0).pointer(), self.val['members_']['m_icont']['data_']['root_plus_size_']['m_header']['next_'])
 
    def to_string(self):
        return '%s with %d elements' % (self.typename, self.val['members_']['m_icont']['data_']['root_plus_size_']['size_'])
    
    def display_hint (self):
        return 'list'

class VectorPrinter:
    "Print a vector"
 
    class _iter (Iterator):
        def __init__ (self, start, size):
            self.count = 0
            self.start = start
            self.size = size
 
        def __iter__(self):
            return self
 
        def __next__(self):
            if self.count == self.size:
                raise StopIteration
            elt = self.start[self.count]
            result = ('[%d]' % self.count, elt)
            self.count = self.count + 1 
            return result
 
    def __init__(self, typename, val):
        self.typename = typename
        self.val = val
 
    def children(self):
        return self._iter (self.val['m_holder']['m_start'], self.val['m_holder']['m_size'])
 
    def to_string(self):
        return ('%s of length %d, capacity %d'
                % (self.typename, self.val['m_holder']['m_size'], self.val['m_holder']['m_capacity']))
 
    def display_hint(self):
        return 'array'

class VectorIteratorPrinter:
    "Print vector::iterator"
 
    def __init__(self, typename, val):
        self.val = val
 
    def to_string(self):
        return self.val['m_ptr'].dereference()

def pointer_plus_bits(p):
    return gdb.Value(long(p) & ~((1 << 1) - 1)).cast(p.type)

class RbtreeIterator(Iterator):
    def __init__(self, rbtree):
        self.size = rbtree['members_']['m_icont']['size_']
        self.node = rbtree['members_']['m_icont']['holder']['root']['left_']
        self.count = 0

    def __iter__(self):
        return self

    def __len__(self):
        return int (self.size)

    def __next__(self):
        if self.count == self.size:
            raise StopIteration
        result = self.node
        self.count = self.count + 1
        if self.count < self.size:
            # Compute the next node.
            node = self.node
            if node.dereference()['right_']:
                node = node.dereference()['right_']
                while node.dereference()['left_']:
                    node = node.dereference()['left_']
            else:
                parent = pointer_plus_bits(node.dereference()['parent_'])
                while node == parent.dereference()['right_']:
                    node = parent
                    parent = pointer_plus_bits(parent.dereference()['parent_'])
                if node.dereference()['right_'] != parent:
                    node = parent
            self.node = node
        return result

class IteratorPrinter:
    "Print iterator"

    def __init__ (self, typename, val):
        self.val = val
        rep_type = self.val.type.name
        rep_type = rep_type[0:rep_type.rfind('::')] + '::value_type'
        try:
            self.link_type = gdb.lookup_type(rep_type).pointer()
        except:
            self.link_type = rep_type.template_argument(0)

    def to_string (self):
        node = (self.val['m_iit']['members_']['nodeptr_'] + 1).cast(self.link_type).dereference()
        return node

class MapPrinter:
    "Print a map or multimap"

    # Turn an RbtreeIterator into a pretty-print iterator.
    class _iter(Iterator):
        def __init__(self, rbiter, type):
            self.rbiter = rbiter
            self.count = 0
            self.type = type

        def __iter__(self):
            return self

        def __next__(self):
            if self.count % 2 == 0:
                n = next(self.rbiter) + 1
                n = n.cast(self.type).dereference()
                self.pair = n
                item = n['first']
            else:
                item = self.pair['second']
            result = ('[%d]' % self.count, item)
            self.count = self.count + 1
            return result

    def __init__ (self, typename, val):
        self.typename = typename
        self.val = val

    def to_string (self):
        return '%s with %d elements' % (self.typename, len (RbtreeIterator (self.val)))

    def children (self):
        rep_type = find_type(self.val.type, 'value_type')
        rep_type = rep_type.strip_typedefs()
        return self._iter (RbtreeIterator (self.val), rep_type.pointer())

    def display_hint (self):
        return 'map'

class UnorderedMapPrinter:
    class _iter (Iterator):
        def __init__(self, nodetype, valtype, head):
            self.nodetype = nodetype
            self.valtype = valtype
            self.base = head
            self.head = head.address
            self.count = 0
 
        def __iter__(self):
            return self
 
        def __next__(self):
            if self.count % 2 == 0:
                if self.base == self.head:
                    raise StopIteration
                if self.base == 0:
                    raise StopIteration
                elt = self.base.cast(self.nodetype)
                self.base = elt.dereference()['next_']
                self.pair = (elt + 2).cast(self.valtype).dereference()
                item = self.pair['first']
            else:
                item = self.pair['second']
            result = ('[%d]' % self.count, item)
            self.count = self.count + 1
            return result
 
    def __init__(self, typename, val):
        self.typename = typename
        self.val = val
 
    def children(self):
        rep_type = find_type(self.val.type, 'value_type')
        rep_type = rep_type.strip_typedefs()
        node = self.val['table_']['buckets_'][self.val['table_']['bucket_count_']]['next_']
        nodetype = node.type
        nodetype = nodetype.strip_typedefs()
        return self._iter (nodetype, rep_type.pointer(), node)
 
    def to_string(self):
        return '%s with %d elements' % (self.typename, self.val['table_']['size_'])
 
    def display_hint (self):
        return 'map'
    
# A "regular expression" printer which conforms to the
# "SubPrettyPrinter" protocol from gdb.printing.
class RxPrinter(object):
    def __init__(self, name, function):
        super(RxPrinter, self).__init__()
        self.name = name
        self.function = function
        self.enabled = True

    def invoke(self, value):
        if not self.enabled:
            return None

        if value.type.code == gdb.TYPE_CODE_REF:
            if hasattr(gdb.Value,"referenced_value"):
                value = value.referenced_value()

        return self.function(self.name, value)

# A pretty-printer that conforms to the "PrettyPrinter" protocol from
# gdb.printing.  It can also be used directly as an old-style printer.
class Printer(object):
    def __init__(self, name):
        super(Printer, self).__init__()
        self.name = name
        self.subprinters = []
        self.lookup = {}
        self.enabled = True
        self.compiled_rx = re.compile('^([a-zA-Z0-9_:]+)(<.*>)?$')

    def add(self, name, function):
        # A small sanity check.
        # FIXME
        if not self.compiled_rx.match(name):
            raise ValueError('boost container programming error: "%s" does not match' % name)
        printer = RxPrinter(name, function)
        self.subprinters.append(printer)
        self.lookup[name] = printer

    @staticmethod
    def get_basic_type(type):
        # If it points to a reference, get the reference.
        if type.code == gdb.TYPE_CODE_REF:
            type = type.target ()

        # Get the unqualified type, stripped of typedefs.
        type = type.unqualified ().strip_typedefs ()

        return type.tag

    def __call__(self, val):
        typename = self.get_basic_type(val.type)
        if not typename:
            return None

        # All the types we match are template types, so we can use a
        # dictionary.
        match = self.compiled_rx.match(typename)
        if not match:
            return None

        basename = match.group(1)

        if val.type.code == gdb.TYPE_CODE_REF:
            if hasattr(gdb.Value,"referenced_value"):
                val = val.referenced_value()

        if basename in self.lookup:
            return self.lookup[basename].invoke(val)

        # Cannot find a pretty printer.  Return None.
        return None

boost_container_printer = None

def register_boost_container_printers (obj):
    global boost_container_printer
    gdb.printing.register_pretty_printer(obj, boost_container_printer)

def build_boost_container_dictionary ():
    global boost_container_printer

    boost_container_printer = Printer("boost-container")
    boost_container_printer.add('boost::container::basic_string', StringPrinter)
    boost_container_printer.add('boost::container::map', MapPrinter)
    boost_container_printer.add('boost::container::multimap', MapPrinter)
    boost_container_printer.add('boost::container::list', ListPrinter)
    boost_container_printer.add('boost::container::vector', VectorPrinter)
    boost_container_printer.add('boost::container::container_detail::iterator_from_iiterator', IteratorPrinter)
    boost_container_printer.add('boost::container::container_detail::vec_iterator', VectorIteratorPrinter)

build_boost_container_dictionary ()
