#!/usr/bin/env python

from numpy import array, ndarray
from operator import itemgetter
from biom.util import flatten
import _sparsemat

__author__ = "Daniel McDonald"
__copyright__ = "Copyright 2012, BIOM-Format Project"
__credits__ = ["Daniel McDonald", "Jai Rideout", "Greg Caporaso", 
               "Jose Clemente", "Justin Kuczynski"]
__license__ = "GPL"
__url__ = "http://biom-format.org"
__version__ = "0.9.3-dev"
__maintainer__ = "Daniel McDonald"
__email__ = "daniel.mcdonald@colorado.edu"
__status__ = "Release"

class SparseMat():
    """Support wrapper for the light weight c++ sparse mat

    Must specify rows and columns in advance

    Object cannot "grow" in shape

    There is additional overhead on inserts in order to support rapid lookups
    across rows or columns
    """

    def __init__(self, rows, cols, dtype=float, enable_indices=True):
        self.shape = (rows, cols) 
        self.dtype = dtype # casting is minimal, trust the programmer...
        
        if dtype == float:
            self._data = _sparsemat.PySparseMatFloat()
        elif dtype == int:
            self._data = _sparsemat.PySparseMatInt()
        else:
            raise ValueError, "Unsupported type %s for _sparsemat" % dtype
            
        if enable_indices:
            self._index_rows = [set() for i in range(rows)]
            self._index_cols = [set() for i in range(cols)]
            self._keys = set([])
        else:
            self._index_rows = None
            self._index_rows = None
            self._keys = None
        self._indices_enabled = enable_indices

    def keys(self):
        """Return keys as a list"""
        if self._indices_enabled:
            return list(self._keys)
        else:
            raise AttributeError, "_indices_enabled is not set!"

    def items(self):
        """Generater returning ((r,c),v)"""
        for k in self.keys():
            yield self._data.get(k)
    iteritems = items

    def __contains__(self, args):
        """Return True if args are in self, false otherwise"""
        row, col = args
        if self._data.contains(row, col):
            return True
        else:
            return False
    
    def erase(self, args):
        """Deletes the item at args"""
        row, col = args
        self._data.erase(row, col)
        self._update_internal_indices((row,col), 0)
             
    def copy(self):
        """Return a copy of self"""
        new_self = self.__class__(self.shape[0], self.shape[1], self.dtype, \
                                  self._indices_enabled)
        new_self.update(self)
        raise NotImplementedError, "update() is expecting a dict, not a SparseMat"
        return new_self

    def __eq__(self, other):
        """Returns true if both SparseMats are the same"""
        print self._keys
        print other._keys
        self_keys = set(self._keys)
        other_keys = set(other._keys)
        print self_keys
        print other_keys
        if self_keys != other_keys:
            return False
        
        for k in self_keys:
            if self[k] != other[k]:
                return False
        
        return True
        
    def __setitem__(self,args,value):
        """Wrap setitem, complain if out of bounds"""
        row,col = args
        in_self_rows, in_self_cols = self.shape

        if row >= in_self_rows or row < 0:
            raise KeyError, "The specified row is out of bounds"
        if col >= in_self_cols or col < 0:
            raise KeyError, "The specified col is out of bounds"

        if value == 0:
            if args in self:
                self._update_internal_indices(args, value)
                self.erase(args)
            else:
                return
        else:
            self._update_internal_indices(args, value)
            self._data.insert(row,col,value)
            
    def __getitem__(self,args):
        """Wrap getitem to handle slices"""
        try:
            row,col = args
        except TypeError:
            raise IndexError, "Must specify (row, col)"

        if isinstance(row, slice): 
            if row.start is None and row.stop is None:
                return self.getCol(col)
            else:
                raise AttributeError, "Can only handle full : slices per axis"
        elif isinstance(col, slice):
            if col.start is None and col.stop is None:
                return self.getRow(row)
            else:
                raise AttributeError, "Can only handle full : slices per axis"
        else:
            # boundary check
            self_rows, self_cols = self.shape
            if row >= self_rows or row < 0:
                raise IndexError, "Row index out of range"
            if col >= self_cols or col < 0:
                raise IndexError, "Col index out of range"

            return self._data.get(row,col)

    def _update_internal_indices(self, args, value):
        """Update internal row,col indices"""
        row,col = args
        if value == 0:
            if args in self:
                self._index_rows[row].remove(args)
                self._index_cols[col].remove(args)
                self._keys.remove(args)
            else:
                return # short circuit, no point in setting 0
        else:
            self._index_rows[row].add(args)
            self._index_cols[col].add(args)
            self._keys.add(args)

    def getRow(self, row):
        """Returns a row in SparseMat form"""
        in_self_rows, in_self_cols = self.shape
        if row >= in_self_rows or row < 0:
            raise IndexError, "The specified row is out of bounds"
    
        new_row = SparseMat(1, in_self_cols, enable_indices=False, \
                            dtype=self.dtype)
        
        for r,c in self._index_rows[row]:
            v = self._data.get(r,c) # hit directly, trust thyself...
            if v == 0:
                continue
            new_row._data.insert(r, c, v)
        
        return new_row

    def getCol(self, col):
        """Return a col in SparseMat form"""
        in_self_rows, in_self_cols = self.shape
        if col >= in_self_cols or col < 0:
            raise IndexError, "The specified col is out of bounds"

        new_col = SparseMat(in_self_rows, 1, enable_indices=False, \
                            dtype=self.dtype)
        
        for r,c in self._index_cols[col]:
            v = self._data.get(r,c) # hit directly, trust thyself
            if v == 0:
                continue
            new_col._data.insert(r, c, v)
        
        return new_col

    def transpose(self):
        """Transpose self"""
        new_self = self.__class__(*self.shape[::-1], \
                enable_indices=self._indices_enabled, dtype=self.dtype)
        
        raise NotImplementedError, "C++ object should provide a bulk export method"
        
        ### however... we could iterate over the indices, but are fucked if they're disabled
        
        new_self.update(dict([((c,r),v) for (r,c),v in self.iteritems()]))
        return new_self
    T = property(transpose)

    def update(self, update_dict):
        """Update self"""
        in_self_rows, in_self_cols = self.shape
    
        # handle zero values different and dont pass them to update
        for (row,col),value in update_dict.items():
            #if row >= in_self_rows or row < 0:
            #    raise KeyError, "The specified row is out of bounds"
            #if col >= in_self_cols or col < 0:
            #    raise KeyError, "The specified col is out of bounds"
            #if value == 0:
            #    self.__setitem__((row,col), 0)
            #else:
            
            # the above is all covered in __setitem__
            self[row,col] = value
            
            if self._indices_enabled:
                self._update_internal_indices((row,col), value)

def to_sparsemat(values, transpose=False, dtype=float):
    """Tries to returns a populated SparseMat object

    NOTE: assumes the max value observed in row and col defines the size of the
    matrix
    """
    # if it is a vector
    if isinstance(values, ndarray) and len(values.shape) == 1:
        if transpose:
            mat = nparray_to_sparsemat(values[:,newaxis], dtype)
        else:
            mat = nparray_to_sparsemat(values, dtype)
        return mat
    # the empty list
    elif isinstance(values, list) and len(values) == 0:
        mat = SparseMat(0,0)
        return mat
    # list of np vectors
    elif isinstance(values, list) and isinstance(values[0], ndarray):
        mat = list_nparray_to_sparsemat(values, dtype)
        if transpose:
            mat = mat.T
        return mat
    # list of dicts, each representing a row in row order
    elif isinstance(values, list) and isinstance(values[0], dict):
        mat = list_dict_to_sparsemat(values, dtype)
        if transpose:
            mat = mat.T
        return mat
    elif isinstance(values, dict):
        mat = dict_to_sparsemat(values, dtype)
        if transpose:
            mat = mat.T
        return mat
    else:
        raise TableException, "Unknown input type"
        
def list_list_to_sparsemat(data, dtype=float, shape=None):
    """Convert a list of lists into a SparseMat

    [[row, col, value], ...]
    """
    d = dict([((r,c),dtype(v)) for r,c,v in data if v != 0])

    if shape is None:
        n_rows = 0
        n_cols = 0
        for (r,c) in d:
            if r >= n_rows:
                n_rows = r + 1 # deal with 0-based indexes
            if c >= n_cols:
                n_cols = c + 1

        mat = SparseMat(n_rows, n_cols)
    else:
        mat = SparseMat(*shape)

    mat.update(d)
    return mat

def nparray_to_sparsemat(data, dtype=float):
    """Convert a numpy array to a SparseMat"""
    if len(data.shape) == 1:
        mat = SparseMat(1, data.shape[0])

        for idx,v in enumerate(data):
            if v != 0:
                mat[(0,idx)] = dtype(v)
    else:
        mat = SparseMat(*data.shape)
        for row_idx, row in enumerate(data):
            for col_idx, value in enumerate(row):
                if value != 0:
                    mat[(row_idx, col_idx)] = dtype(value)
    return mat

def list_nparray_to_sparsemat(data, dtype=float):
    """Takes a list of numpy arrays and creates a SparseMat"""
    mat = SparseMat(len(data), len(data[0]))
    for row_idx, row in enumerate(data):
        if len(row.shape) != 1:
            raise TableException, "Cannot convert non-1d vectors!"
        if len(row) != mat.shape[1]:
            raise TableException, "Row vector isn't the correct length!"

        for col_idx, val in enumerate(row):
            mat[row_idx, col_idx] = dtype(val)
    return mat

def list_dict_to_sparsemat(data, dtype=float):
    """Takes a list of dict {(0,col):val} and creates a SparseMat"""
    raise NotImplementedError, "SparseMat needs a notion of len"
    if isinstance(data[0], SparseMat):
        if data[0].shape[0] > data[0].shape[1]:
            is_col = True
            n_cols = len(data)
            n_rows = data[0].shape[0]
        else:
            is_col = False
            n_rows = len(data)
            n_cols = data[0].shape[1]
    else:
        all_keys = flatten([d.keys() for d in data])
        n_rows = max(all_keys, key=itemgetter(0))[0] + 1
        n_cols = max(all_keys, key=itemgetter(1))[1] + 1
        if n_rows > n_cols:
            is_col = True
            n_cols = len(data)
        else:
            is_col = False
            n_rows = len(data)

    mat = SparseMat(n_rows, n_cols)
    for row_idx,row in enumerate(data):
        for (foo,col_idx),val in row.items():
            if is_col:
                mat[foo,row_idx] = dtype(val)
            else:
                mat[row_idx,col_idx] = dtype(val)

    return mat

def dict_to_sparsemat(data, dtype=float):
    """takes a dict {(row,col):val} and creates a SparseMat"""
    n_rows = max(data.keys(), key=itemgetter(0))[0] + 1
    n_cols = max(data.keys(), key=itemgetter(1))[1] + 1
    mat = SparseMat(n_rows, n_cols)
    mat.update(data)
    return mat