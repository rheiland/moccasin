#!/usr/bin/env python
#
# @file    matlab.py
# @brief   Objects to represent a parsed version of MATLAB code.
# @author  Michael Hucka
#
# <!---------------------------------------------------------------------------
# This software is part of MOCCASIN, the Model ODE Converter for Creating
# Awesome SBML INteroperability. Visit https://github.com/sbmlteam/moccasin/.
#
# Copyright (C) 2014-2015 jointly by the following organizations:
#  1. California Institute of Technology, Pasadena, CA, USA
#  2. Mount Sinai School of Medicine, New York, NY, USA
#  3. Boston University, Boston, MA, USA
#
# This is free software; you can redistribute it and/or modify it under the
# terms of the GNU Lesser General Public License as published by the Free
# Software Foundation.  A copy of the license agreement is provided in the
# file named "COPYING.txt" included with this software distribution and also
# available online at https://github.com/sbmlteam/moccasin/.
# ------------------------------------------------------------------------- -->

from __future__ import print_function
import sys
import pdb
import collections


# MatlabNode -- base class for all parse tree nodes.
# .........................................................................

class MatlabNode(object):
    _attr_names = None                 # Default set of node attributes.
    _location   = (0, 0)               # Location in file (tuple: line, col).

    # The following is based on code in Section 8.11 of the Python Cookbook,
    # 3rd ed., by David Beazley and Brian K. Jones (O'Reilly Media, 2013).
    def __init__(self, *args, **kwargs):
        if not self._attr_names:
            if len(args) > 0 or len(kwargs) > 0:
                raise TypeError('{} takes no arguments'.format(type(self)))
            else:
                return

        # Set all of the positional arguments:
        for name, value in zip(self._attr_names, args):
            setattr(self, name, value)

        # Set the remaining keyword arguments:
        for name in self._attr_names[len(args):]:
            setattr(self, name, kwargs.pop(name))

        # Check for any remaining unknown arguments:
        if kwargs:
            raise TypeError('Invalid argument(s): {}'.format(','.join(kwargs)))


    def __repr__(self):
        return 'MatlabNode()'


    def __str__(self):
        return '{MatlabNode}'


    def children(self):
        '''A sequence of all children that are MatlabNodes.'''
        # This is the default implementation.  Subclasses should specialize it.
        nodelist=[]
        return nodelist


    # Idea for the following were drawn from the code at
    # https://github.com/eliben/pycparser/blob/master/pycparser/c_ast.py
    def show(self, buf=sys.stdout, offset=0, show_location=False):
        """Pretty print the Node and all its attributes and children
        recursively to a buffer.

        buf:
            Open IO buffer into which the Node is printed.

        offset:
            Initial offset (amount of leading spaces)

        show_location:
            True if you want the location in the input to be printed too.
        """

        lead = ' ' * offset
        buf.write(lead + str(self))
        if show_location:
            buf.write(' <line %s, column %s>'.format(self.location))
        for child in self.children():
            child.show(buf, offset=offset + 1, show_location=show_location)
        buf.write('\n')


# Entity -- parent class of things that show up in expressions.
# .........................................................................

class Entity(MatlabNode):
    '''Parent class for entities in expressions.'''

    def __repr__(self):
        return 'Entity()'


#
# Primitive entities.
#
# All primitive entities have a single attribute named "value".
#

class Primitive(Entity):
    '''Parent class for primitive terms, such as numbers and strings.'''
    _attr_names = ['value']

    def __repr__(self):
        return '{}(value={})'.format(self.__class__.__name__, repr(self.value))

    def __str__(self):
        return '{{{}: {}}}'.format(self.__class__.__name__.lower(), self.value)


class Number(Primitive):
    '''Any numerical value.  Note that it is stored as a text string.'''
    pass


class Boolean(Primitive):
    '''A Boolean value.'''
    pass


class String(Primitive):
    '''A text string.'''

    # Overrides default printer to put double quotes around value.
    def __str__(self):
        return '{{string: "{}"}}'.format(self.value)


class Special(Primitive):
    '''A literal ~, :, or "end" used in an array context.'''

    # This is not strictly necessary, but the old printer/formatter in
    # grammar.py did it this way, so I'm repeating it here to make comparing
    # results easier.
    def __str__(self):
        if self.value == ':':
            return '{colon}'
        elif self.value == '~':
            return '{tilde}'
        elif self.value == 'end':
            return '{end}'


#
# Bare arrays.
#
# This represents either unnamed, square-bracket delimited arrays, or
# unnamed cell arrays.  They are here because they are half-way between
# primitive values and named things.
#

class Array(Entity):
    '''The field `is_cell` is True if this is a cell array.'''
    _attr_names = ['is_cell', 'rows']

    def __repr__(self):
        return 'Array(is_cell={}, rows={})'.format(self.is_cell, self.rows)


    def __str__(self):
        if self.is_cell:
            if self.rows:
                return '{{cell array: [ {} ]}}'.format(_str_format_rowlist(self.rows))
            else:
                return '{cell array: []}'
        else:
            if self.rows:
                return '{{array: [ {} ]}}'.format(_str_format_rowlist(self.rows))
            else:
                return '{array: [] }'


#
# Handles
#
# Function handles could potentially be considered a subclass of Primitive,
# because they're basically literal values, but they have an implication of
# being closures and thus callers might want to treat them differently than
# Primitive objects.  Anonymous functions are not a Primitive or Reference
# subclass because they are closures, because they're not simple literal
# values, and because they don't have names.

class Handle(Entity):
    pass


class FunHandle(Handle):
    _attr_names = ['name']

    def __repr__(self):
        return 'FunHandle(name={})'.format(repr(self.name))

    def __str__(self):
        return '{{function @ handle: {}}}'.format(_str_format(self.name))


class AnonFun(Handle):
    _attr_names = ['args', 'body']

    def __repr__(self):
        return 'AnonFun(args={}, body={})'.format(repr(self.args), repr(self.body))

    def __str__(self):
        return '{{anon @ handle: args {} body {} }}'.format(_str_format_args(self.args),
                                                            _str_format(self.body))


#
# References.
#
# When it's impossible to determine whether a reference is to an array or
# a function, the Reference object will not be of a more specific subtype.
# If something can be determined to be, say, an ArrayReference, that's the
# type it will have.

class Reference(Entity):
    # Default field is a name.
    _attr_names = ['name']


class Identifier(Reference):
    '''Identifiers NOT used in the syntactic context of a function call or
    array reference.  The value they represent may still be an array or
    function, but where we encountered it, we did not see it used in the
    manner of an array reference or functon call.'''

    _attr_names = ['name']

    def __repr__(self):
        return 'Identifier(name={})'.format(repr(self.name))

    def __str__(self):
        return '{{identifier: "{}"}}'.format(self.name)


class ArrayOrFunCall(Reference):
    '''Syntactically looks like either an array reference or a function call.'''

    _attr_names = ['name', 'args']

    def __repr__(self):
        return 'ArrayOrFunCall(name={}, args={})'.format(repr(self.name),
                                                         repr(self.args))

    def __str__(self):
        return '{{function/array: {} {}}}'.format(_str_format(self.name),
                                                  _str_format_args(self.args))


class FunCall(Reference):
    '''Objects that are determined to be function calls.'''

    _attr_names = ['name', 'args']

    def __repr__(self):
        return 'FunCall(name={}, args={})'.format(repr(self.name),
                                                  repr(self.args))

    def __str__(self):
        return '{{function {} {} }}'.format(_str_format(self.name),
                                            _str_format_args(self.args))


class ArrayRef(Reference):
    '''Objects that are determined to be array references.
    The field `is_cell` is True if this is a cell array.'''

    _attr_names = ['name', 'args', 'is_cell']

    def __repr__(self):
        return 'ArrayRef(is_cell={}, name={}, args={})'.format(self.is_cell,
                                                               repr(self.name),
                                                               repr(self.args))

    def __str__(self):
        if self.is_cell:
            if self.args:
                return '{{cell array: {} [ {} ]}}'.format(_str_format(self.name),
                                                          _str_format_subscripts(self.args))
            else:
                return '{{cell array: {} []}}'.format(_str_format(self.name))
        else:
            if self.args:
                return '{{array {}: [ {} ]}}'.format(_str_format(self.name),
                                                     _str_format_subscripts(self.args))
            else:
                return '{{array {}: [] }}'.format(_str_format(self.name))


class StructRef(Reference):
    '''Objects that are determined to be structure references.
    Warning: `name` may be an expression, not just an identifier.'''

    _attr_names = ['name', 'field']

    def __repr__(self):
        return 'StructRef(name={}, field={})'.format(repr(self.name), repr(self.field))

    def __str__(self):
        return '{{struct: {}.{} }}'.format(_str_format(self.name), _str_format(self.field))


#
# Operators.
#

class Operator(Entity):
    '''Parent class for operators.'''
    _attr_names = ['op']


class UnaryOp(Operator):
    def __repr__(self):
        return 'UnaryOp(op=\'{}\')'.format(self.op)

    def __str__(self):
        return '{{unary op: {}}}'.format(self.op)


class BinaryOp(Operator):
    def __repr__(self):
        return 'BinaryOp(op=\'{}\')'.format(self.op)

    def __str__(self):
        return '{{binary op: {}}}'.format(self.op)


class TernaryOp(Operator):
    # FIXME this is currently wrong.
    _attr_names = ['op']

    def __repr__(self):
        return 'TernaryOp(op=\'{}\')'.format(self.op)

    def __str__(self):
        return '{colon operator}'


class Transpose(Operator):
    _attr_names = ['op', 'operand']

    def __repr__(self):
        return 'Transpose(op=\'{}\', operand={})'.format(self.op, repr(self.operand))

    def __str__(self):
        return '{{transpose: {} operator {} }}'.format(_str_format(self.operand), self.op)


# Expressions
#
# An expression is represented as a list of nodes of either type Entity or
# type Expression.  It's always a list, even if there is a single entity
# inside of it.  Parenthesized expressions are represented as nested
# Expression objects.
# .........................................................................

class Expression(MatlabNode):
    '''The `content` field stores a list of Expression or Entity nodes.'''
    _attr_names = ['content']

    def __repr__(self):
        return 'Expression({})'.format(self.content)

    def __str__(self):
        return _str_format(self.content)


# Definitions: assignments, function definitions, scripts.
# .........................................................................

class Definition(MatlabNode):
    '''Parent class for definitions.'''
    pass


class Assignment(Definition):
    _attr_names = ['lhs', 'rhs']

    def __repr__(self):
        # return _repr_format('Assignment(lhs={}, rhs={})', self.lhs, self.rhs)
        return 'Assignment(lhs={}, rhs={})'.format(repr(self.lhs), repr(self.rhs))

    def __str__(self):
        return '{{assign: {} = {}}}'.format(_str_format(self.lhs),
                                            _str_format(self.rhs))


class FunDef(Definition):
    _attr_names = ['name', 'parameters', 'output', 'body']

    def __repr__(self):
        return 'FunDef(name={}, parameters={}, output={}, body={})'.format(
            repr(self.name), repr(self.parameters), repr(self.output), repr(self.body))

    def __str__(self):
        # This conditonal is only here because the old format didn't print
        # parentheses around the output if the output was a single thing (i.e.,
        # not a list).
        if self.output:
            if len(self.output) > 1:
                output = '[ ' + _str_format_subscripts(self.output) + ' ]'
            else:
                output = _str_format(self.output[0])
        else:
            output = 'none'
        if self.parameters:
            params = _str_format_args(self.parameters)
        else:
            params = '( none )'
        return '{{function definition: {} parameters {} output {}}}'.format(
            _str_format(self.name), params, output)


# Decided not to do this for now.

# class Script(Definition):
#     _attr_names = ['name', 'body']



# Flow control.
# .........................................................................

class FlowControl(MatlabNode):
    pass
    # FIXME


class Try(FlowControl):
    def __repr__(self):
        return 'Try()'

    def __str__(self):
        return '{try}'


class Catch(FlowControl):
    _attr_names = ['var']

    def __repr__(self):
        return 'Catch(var={})'.format(repr(self.var))

    def __str__(self):
        return '{{catch: var {}}}'.format(_str_format(self.var))


class Switch(FlowControl):
    _attr_names = ['cond']

    def __repr__(self):
        return 'Switch(cond={})'.format(repr(self.cond))

    def __str__(self):
        return '{{switch stmt: {}}}'.format(_str_format(self.cond))


class Case(FlowControl):
    _attr_names = ['cond']

    def __repr__(self):
        return 'Case(cond={})'.format(repr(self.cond))

    def __str__(self):
        return '{{case: {}}}'.format(_str_format(self.cond))


class Otherwise(FlowControl):
    def __repr__(self):
        return 'Otherwise()'

    def __str__(self):
        return '{otherwise}'


class If(FlowControl):
    _attr_names = ['cond']

    def __repr__(self):
        return 'While(cond={})'.format(repr(self.cond))

    def __str__(self):
        return '{{while stmt: {}}}'.format(_str_format(self.cond))


class Elseif(FlowControl):
    _attr_names = ['cond']

    def __repr__(self):
        return 'Elseif(cond={})'.format(repr(self.cond))

    def __str__(self):
        return '{{elseif stmt: {}}}'.format(_str_format(self.cond))


class Else(FlowControl):
    def __repr__(self):
        return 'Else()'

    def __str__(self):
        return '{else}'


class While(FlowControl):
    _attr_names = ['cond']

    def __repr__(self):
        return 'While(cond={})'.format(repr(self.cond))

    def __str__(self):
        return '{{while stmt: {}}}'.format(_str_format(self.cond))


class For(FlowControl):
    _attr_names = ['var', 'expr']

    def __repr__(self):
        return 'For(var={}, expr={})'.format(repr(self.var), repr(self.expr))

    def __str__(self):
        return '{{for stmt: var {} in {}}}'.format(_str_format(self.var),
                                                   _str_format(self.expr))


class End(FlowControl):
    def __repr__(self):
        return 'End()'

    def __str__(self):
        return '{end}'


class Branch(FlowControl):
    __attr_names = ['kind']

    def __str__(self):
        if self.kind == 'break':
            return '{break}'
        elif self.kind == 'continue':
            return '{continue}'
        elif self.kind == 'return':
            return '{return}'


# Commands.
# .........................................................................

class Command(MatlabNode):
    pass


class ShellCommand(Command):
    _attr_names = ['command']

    def __repr__(self):
        return 'ShellCommand(command={})'.format(repr(self.command))

    def __str__(self):
        return '{{shell command: {}}}'.format(_str_format(self.command))


class MatlabCommand(Command):
    _attr_names = ['command', 'args']

    def __repr__(self):
        return 'MatlabCommand(command={}, args={})'.format(repr(self.command),
                                                           repr(self.args))

    def __str__(self):
        return '{{command: name {} args {}}}'.format(_str_format(self.command),
                                                     _str_format(self.args))


# Comments.
# .........................................................................

class Comment(MatlabNode):
    _attr_names = ['content']

    def __repr__(self):
        return 'Comment(content={})'.format(repr(self.content))

    def __str__(self):
        return '{{comment: {}}}'.format(self.content)



# Visitor.
# .........................................................................

class MatlabNodeVisitor(object):
    def visit(self, node):
        if isinstance(node, list):
            return [self.visit(item) for item in node]
        else:
            methname = 'visit_' + type(node).__name__
            meth = getattr(self, methname, None)
            if meth is None:
                meth = self.default_visit
            return meth(node)

    def default_visit(self, node):
        return node


# General helpers.
# .........................................................................

def _str_format(thing, no_parens=False):
    if isinstance(thing, list):
        formatted = ' '.join([_str_format(item) for item in thing])
        if no_parens:
            return formatted
        else:
            return '( ' + formatted + ' )'
    else:
        return str(thing)


def _str_format_args(thing):
    if isinstance(thing, list):
        return '( ' + ', '.join([_str_format(item) for item in thing]) + ' )'
    else:
        return str(thing)


def _str_format_subscripts(subscripts):
    return ', '.join([_str_format(thing) for thing in subscripts])


def _str_format_rowlist(rows):
    last = len(rows) - 1
    i = 1
    text = ''
    for row in rows:
        text += '{{row {}: {}}}'.format(i, _str_format_subscripts(row))
        if i <= last:
            text += '; '
        i += 1
    return text


def _repr_format(*args):
    return args[0].format(*[repr(a) for a in args[1:]])
