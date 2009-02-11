from rdflib import Variable
from telescope.sparql.expressions import Expression, and_
from telescope.sparql import operators
from telescope.sparql.util import v, to_variable, to_list

__all__ = ['Triple', 'Filter', 'GraphPattern', 'GroupGraphPattern',
           'UnionGraphPattern', 'union', 'pattern', 'Select']

class Triple(object):
    def __init__(self, subject, predicate, object):
        self.subject = subject
        self.predicate = predicate
        self.object = object
    
    def __iter__(self):
        return iter((self.subject, self.predicate, self.object))
    
    def __repr__(self):
        return "Triple(%r, %r, %r)" % tuple(self)
    
    @classmethod
    def from_obj(cls, obj):
        if isinstance(obj, Triple):
            return obj
        else:
            return cls(*obj)

class Filter(object):
    def __init__(self, constraint):
        self.constraint = constraint
    
    def __repr__(self):
        return "Filter(%r)" % (self.constraint,)

class GraphPattern(object):
    def __init__(self, patterns):
        self.patterns = []
        self.filters = []
        self.add(*patterns)
    
    def add(self, *patterns):
        for pattern in patterns:
            if not isinstance(pattern, GraphPattern):
                pattern = Triple.from_obj(pattern)
            self.patterns.append(pattern)
    
    def filter(self, *expressions):
        self.filters.append(Filter(and_(*expressions)))
    
    def __nonzero__(self):
        return bool(self.patterns)
    
    def __len__(self):
        return len(self.patterns)
    
    def __getitem__(self, item):
        return self.patterns[item]
    
    def __or__(self, other):
        return UnionGraphPattern([self, GraphPattern.from_obj(other)])
    
    def __ror__(self, other):
        return UnionGraphPattern([GraphPattern.from_obj(other), self])
    
    def _clone(self, **kwargs):
        clone = self.__class__.__new__(self.__class__)
        clone.__dict__.update(self.__dict__)
        clone.patterns = self.patterns[:]
        clone.__dict__.update(kwargs)
        return clone
    
    @classmethod
    def from_obj(cls, obj, **kwargs):
        if isinstance(obj, GraphPattern):
            return obj._clone(**kwargs)
        else:
            if isinstance(obj, Triple):
                obj = [obj]
            return cls(obj, **kwargs)

class GroupGraphPattern(GraphPattern):
    def __init__(self, patterns, optional=False):
        GraphPattern.__init__(self, patterns)
        self.optional = optional

class UnionGraphPattern(GraphPattern):
    def __init__(self, patterns):
        GraphPattern.__init__(self, patterns)

def union(*graph_patterns):
    return UnionGraphPattern(map(GraphPattern.from_obj, graph_patterns))

def pattern(*patterns, **kwargs):
    return GroupGraphPattern(patterns, **kwargs)

def optional(*patterns):
    return GroupGraphPattern(patterns, optional=True)

class Select(object):
    def __init__(self, variables, *patterns, **kwargs):
        self.variables = tuple(map(to_variable, to_list(variables)))
        self._where = GroupGraphPattern(patterns)
        self._distinct = kwargs.pop('distinct', False)
        self._reduced = kwargs.pop('reduced', False)
        if self._distinct and self._reduced:
            raise ValueError("DISTINCT and REDUCED are mutually exclusive.")
        
        self._limit = kwargs.pop('limit', None)
        self._offset = kwargs.pop('offset', None)
        self._order_by = kwargs.pop('order_by', None)
        self.graph = kwargs.pop('graph', None)
        if kwargs:
            key, value = kwargs.popitem()
            raise TypeError("Unexpected keyword argument: %r" % key)
    
    def __getitem__(self, item):
        if isinstance(item, slice):
            if item.step is None or item.step == 1:
                offset = item.start
                limit = item.stop
                if offset is not None and limit is not None:
                    limit -= offset
                return self._clone(_offset=offset, _limit=limit)
            else:
                raise ValueError("Stepped slicing is not supported.")
        else:
            raise ValueError("Indexing is not supported.")
    
    def _clone(self, **kwargs):
        clone = self.__class__.__new__(self.__class__)
        clone.__dict__.update(self.__dict__)
        clone._where = self._where._clone()
        clone.__dict__.update(kwargs)
        return clone
    
    def project(self, *variables, **kwargs):
        add = kwargs.pop('add', False)
        projection = []
        for arg in variables:
            for obj in to_list(arg):
                variable = to_variable(obj)
                if variable:
                    projection.append(variable)
        if add:
            projection[:0] = self.variables
        return self._clone(variables=tuple(projection))
    
    def where(self, *patterns, **kwargs):
        clone = self._clone()
        if patterns:
            graph_pattern = GroupGraphPattern.from_obj(patterns, **kwargs)
            clone._where.add(graph_pattern)
        return clone
    
    def filter(self, *constraints, **kwargs):
        constraints = list(constraints)
        for key, value in kwargs.iteritems():
            constraints.append(v[key] == value)
        clone = self._clone()
        clone._where.filter(*constraints)
        return clone
    
    def limit(self, number):
        """Return a new `Select` with LIMIT `number` applied."""
        return self._clone(_limit=number)
    
    def offset(self, number):
        """Return a new `Select` with OFFSET `number` applied."""
        return self._clone(_offset=number)
    
    def order_by(self, *variables):
        """Return a new `Select` with ORDER BY `variables` applied."""
        return self._clone(_order_by=variables)
    
    def distinct(self, value=True):
        """Return a new `Select` with DISTINCT modified according to `value`.
        
        If `value` is True (the default), then `reduced` is forced to False.
        """
        return self._clone(_distinct=value, _reduced=not value and self._reduced)
    
    def reduced(self, value=True):
        """Return a new `Select` with REDUCED modified according to `value`.
        
        If `value` is True (the default), then `distinct` is forced to False.
        """
        return self._clone(_reduced=value, _distinct=not value and self._distinct)
    
    def execute(self, graph, prefix_map=None):
        return graph.query(unicode(self.compile(prefix_map)))
    
    def compile(self, prefix_map=None):
        from telescope.sparql.compiler import SelectCompiler
        compiler = SelectCompiler(prefix_map)
        return compiler.compile(self)

