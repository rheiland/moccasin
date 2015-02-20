#!/usr/bin/env python
#
# @file    converter.py
# @brief   MATLAB converter
# @author  Michael Hucka
#
# <!---------------------------------------------------------------------------
# This software is part of MOCCASIN, the Model ODE Converter for Creating
# Awesome SBML INteroperability. Visit https://github.com/sbmlteam/moccasin/.
#
# Copyright (C) 2014 jointly by the following organizations:
#     1. California Institute of Technology, Pasadena, CA, USA
#     2. Mount Sinai School of Medicine, New York, NY, USA
#
# This is free software; you can redistribute it and/or modify it under the
# terms of the GNU Lesser General Public License as published by the Free
# Software Foundation.  A copy of the license agreement is provided in the
# file named "COPYING.txt" included with this software distribution and also
# available online at https://github.com/sbmlteam/moccasin/.
# ------------------------------------------------------------------------- -->

from __future__ import print_function
import glob
import sys
import pdb
import re
import getopt
import six
import itertools
from pyparsing import ParseException, ParseResults
from evaluate_formula import NumericStringParser
from libsbml import *

sys.path.append('..')
from matlab_parser import MatlabGrammar, Scope


# -----------------------------------------------------------------------------
# Globals.
# -----------------------------------------------------------------------------

anon_counter = 0


# -----------------------------------------------------------------------------
# Parsing-related stuff.
# -----------------------------------------------------------------------------

def get_function_scope(mparse):
    # If the outermost scope contains no assignments but does contain a single
    # function, it means the whole file is a function definition.  We want to
    # get at the scope object for the parse results of that function.
    if mparse and mparse.scope:
        scope = mparse.scope
        if len(scope.functions) == 1 and len(scope.assignments) == 0:
            return six.next(six.itervalues(scope.functions))
        else:
            return scope
    else:
        return None


def get_all_assignments(scope):
    # Loop through the variables and create a dictionary to return.
    assignments = {}
    for var, rhs in scope.assignments.items():
        assignments[var] = rhs
    for fname, fscope in scope.functions.items():
        assignments.update(get_all_assignments(fscope))
    return assignments


def get_all_function_calls(scope):
    calls = {}
    for fname, arglist in scope.calls.items():
        calls[fname] = arglist
    for fname, fscope in scope.functions.items():
        calls.update(get_all_function_calls(fscope))
    return calls


def name_is_structured(name):
    return ('[' in name or '(' in name or '{' in name)


def name_mentioned_in_rhs(name, mparse):
    for item in mparse:
        if len(item) > 1:
            # It's an expression.  Look inside each piece recursively.
            if name_mentioned_in_rhs(name, item):
                return True
            else:
                continue
        if len(item) == 1:
            if 'array or function' in item:
                item = item['array or function']
                if name_mentioned_in_rhs(name, item['argument list']):
                    return True
            elif 'identifier' in item:
                if name == item['identifier']:
                    return True
    return False


def get_lhs_for_rhs(name, scope):
    for lhs, rhs in scope.assignments.items():
        if name_mentioned_in_rhs(name, rhs):
            return lhs
    return None

def get_assignment_rule(name, scope):
    for lhs, rhs in scope.assignments.items():
        if lhs == name:
            return rhs
    return None

def get_function_declaration(name, scope):
    if scope and name in scope.functions:
        return scope.functions[name]
    return None


def terminal_value(pr):
    if 'identifier' in pr:
        return pr['identifier']
    elif 'number' in pr:
        return float(pr['number'])
    return None


def matrix_dimensions(matrix):
    if len(matrix['row list']) == 1:
        return 1
    elif len(matrix['row list'][0]['subscript list']) == 1:
        return 1
    else:
        return 2


def is_row_vector(matrix):
    return (len(matrix['row list']) == 1
            and len(matrix['row list'][0]['subscript list']) >= 1)


def vector_length(matrix):
    if is_row_vector(matrix):
        return len(matrix['row list'][0]['subscript list'])
    else:
        return len(matrix['row list'])


def mloop(matrix, func):
    # Calls function 'func' on a row or column of values from the matrix.
    # Note: the argument 'i' is 0-based, not 1-based like Matlab vectors.
    # FIXME: this only handles 1-D row or column vectors.
    row_vector = is_row_vector(matrix)
    row_length = vector_length(matrix)
    base = matrix['row list']
    for i in range(0, row_length):
        if row_vector:
            entry = base[0]['subscript list'][i]
        else:
            entry = base[i]['subscript list'][0]
        func(i, entry)


def inferred_type(name, scope, recursive=False):
    if name in scope.types:
        return scope.types[name]
    elif recursive and hasattr(scope, 'parent') and scope.parent:
        return inferred_type(name, scope.parent, True)
    else:
        return None


def num_underscores(scope):
    # Look if any variables use underscores in their name.  Count the longest
    # sequence of underscores found.  Recursively looks in subscopes too.
    longest = 0
    for name in scope.assignments:
        if '_' in name:
            this_longest = len(max(re.findall('(_+)', name), key=len))
            longest = max(longest, this_longest)
    if scope.functions:
        for subscope in six.itervalues(scope.functions):
            longest = max(num_underscores(subscope), longest)
    return longest


def rename(base, tail='', num_underscores=1):
    return ''.join([base, '_'*num_underscores, tail])


def parse_handle(func, scope, underscores):
    # @(args)...stuff...
    # Cases:
    #  body is a function call => return the function name
    #  body is a variable that holds another function handle => chase it
    #  body is a matrix
    if 'function handle' in func:
        func = func['function handle']
    if 'name' in func:                   # Case: @foo
        return func['name']['identifier']
    elif 'function definition' in func:  # Case: @(args)body
        body = func['function definition']
        if 'array or function' in body:
            inside = body['array or function']
            if 'name' in inside:
                return inside['name']['identifier']
            else:
                # This shouldn't happen; 'array or function' always has a name.
                return None
        elif 'array' in body:
            # Body is an array.  In our domain of ODE and similar models, it
            # means it's the equivalent of a function body.  Approach: create
            # a new fake function, store it, and return its name.
            name = create_array_function(func, scope, underscores)
            return name
    else:
        return None


def create_array_function(func, scope, underscores):
    if 'function handle' in func:
        func = func['function handle']
    if 'array' not in func['function definition']:
        return None             # We shouldn't be here in the first place.
    func_name = new_anon_name()
    params = [p['identifier'] for p in func['argument list']]
    output_var = func_name + '_'*underscores + 'out'
    newscope = Scope(func_name, scope, None, params, [output_var])
    newscope.assignments[output_var] = func['function definition']
    newscope.types[output_var] = 'variable'
    for var in params:
        newscope.types[var] = 'variable'
    scope.functions[func_name] = newscope
    return func_name


def new_anon_name():
    global anon_counter
    anon_counter += 1
    return 'anon{:03d}'.format(anon_counter)

# -----------------------------------------------------------------------------
# XPP specific stuff
# Later this should really get incorporated with the equivalent sbml
# functions with a flag to say which is being used
#
# but for now I'm going with a completely separate approach
# -----------------------------------------------------------------------------
def create_xpp_compartment(xpp_variables, id, size):
    compartment = dict({'SBML_type': 'Compartment',
                        'id': id,
                        'value': size,
                        'constant': True,
                        'init_assign': '',
                        'rate_rule': ''})
    xpp_variables.append(compartment)
    return xpp_variables

def create_xpp_parameter(xpp_variables, id, value, constant=True,
                         rate_rule='', init_assign=''):
    parameter = dict({'SBML_type': 'Parameter',
                      'id': id,
                      'value': value,
                      'constant': constant,
                      'init_assign': init_assign,
                      'rate_rule': rate_rule})
    xpp_variables.append(parameter)
    return xpp_variables

def create_xpp_species(xpp_variables, id, value, rate_rule='', init_assign=''):
    species = dict({'SBML_type': 'Species',
                    'id': id,
                    'value': value,
                    'constant': False,
                    'init_assign': init_assign,
                    'rate_rule': rate_rule})
    xpp_variables.append(species)
    return xpp_variables

# def create_xpp_initial_assignment(model, id, ast):
#     ia = model.createInitialAssignment()
#     check(ia,               'create initial assignment')
#     check(ia.setMath(ast),  'set initial assignment formula')
#     check(ia.setSymbol(id), 'set initial assignment symbol')
#     return ia


def add_xpp_raterule(model, id, ast):
    for i in range(0,len(model)):
        if model[i]['id'] == id:
            model[i]['rate_rule'] = ast
            break

    return



def make_xpp_indexed(var, index, content, species, model, underscores, scope):
    name = rename(var, str(index + 1), underscores)
    if 'number' in content:
        value = terminal_value(content)
        if species:
            model = create_xpp_species(model, name, value)
        else:
            model = create_xpp_parameter(model, name, value, False)
    else:
        translator = lambda pr: munge_reference(pr, scope, underscores)
        formula = MatlabGrammar.make_formula(content, atrans=translator)
        if species:
            model = create_xpp_species(model, name, 0, formula)
        else:
            model = create_xpp_parameter(model, name, 0, False, formula)


def make_xpp_raterule(assigned_var, dep_var, index, content, model, underscores, scope):
    # Currently, this assumes there's only one math expression per row or
    # column, meaning, one subscript value per row or column.

    translator = lambda pr: munge_reference(pr, scope, underscores)
    string_formula = MatlabGrammar.make_formula(content, atrans=translator)
    if not string_formula:
        fail('Failed to parse the formula for row {}'.format(index + 1))

    # We need to rewrite matrix references "x(n)" to the form "x_n", and
    # rename the variable to the name used for the results assignment
    # in the call to the ode* function.
    xnameregexp = dep_var + '_'*underscores + r'(\d+)'
    newnametransform = assigned_var + '_'*underscores + r'\1'
    formula = re.sub(xnameregexp, newnametransform, string_formula)

    # Finally, write the rate rule.
    rule_var = assigned_var + '_'*underscores + str(index + 1)
    add_xpp_raterule(model, rule_var, formula)



# -----------------------------------------------------------------------------
# SBML-specific stuff.
# -----------------------------------------------------------------------------

def check(value, message):
    """If 'value' is None, prints an error message constructed using
    'message' and then exits with status code 1.  If 'value' is an integer,
    it assumes it is a libSBML return status code.  If the code value is
    LIBSBML_OPERATION_SUCCESS, returns without further action; if it is not,
    prints an error message constructed using 'message' along with text from
    libSBML explaining the meaning of the code, and exits with status code 1.
    """
    if value is None:
        print('LibSBML returned a null value trying to ' + message + '.')
        print('Exiting.')
        sys.exit(1)
    elif type(value) is int:
        if value == LIBSBML_OPERATION_SUCCESS:
            return
        else:
            print('Error encountered trying to ' + message + '.')
            print('LibSBML returned error code ' + str(value) + ': "'
                  + OperationReturnValue_toString(value).strip() + '"')
            print('Exiting.')
            sys.exit(1)
    else:
        return


def create_sbml_document():
    # Create model structure
    try:
        return SBMLDocument(3, 1)
    except ValueError:
        print('Could not create SBMLDocumention object')
        sys.exit(1)


def create_sbml_model(document):
    model = document.createModel()
    check(model, 'create model')
    return model


def create_sbml_compartment(model, id, size):
    c = model.createCompartment()
    check(c,                         'create compartment')
    check(c.setId(id),               'set compartment id')
    check(c.setConstant(True),       'set compartment "constant"')
    check(c.setSize(size),           'set compartment "size"')
    check(c.setSpatialDimensions(3), 'set compartment dimensions')
    return c


def create_sbml_species(model, id, value):
    comp = model.getCompartment(0)
    s = model.createSpecies()
    check(s,                                 'create species')
    check(s.setId(id),                       'set species id')
    check(s.setCompartment(comp.getId()),    'set species compartment')
    check(s.setConstant(False),              'set species "constant"')
    check(s.setInitialConcentration(value),  'set species initial concentration')
    check(s.setBoundaryCondition(False),     'set species "boundaryCondition"')
    check(s.setHasOnlySubstanceUnits(False), 'set species "hasOnlySubstanceUnits"')
    return s


def create_sbml_parameter(model, id, value):
    p = model.createParameter()
    check(p,                   'create parameter')
    check(p.setId(id),         'set parameter id')
    check(p.setConstant(True), 'set parameter "constant"')
    check(p.setValue(value),   'set parameter value')
    return p


def create_sbml_initial_assignment(model, id, ast):
    ia = model.createInitialAssignment()
    check(ia,               'create initial assignment')
    check(ia.setMath(ast),  'set initial assignment formula')
    check(ia.setSymbol(id), 'set initial assignment symbol')
    return ia


def create_sbml_raterule(model, id, ast):
    rr = model.createRateRule()
    check(rr,                  'create raterule')
    check(rr.setVariable(id),  'set raterule variable')
    check(rr.setMath(ast),     'set raterule formula')
    return rr


def make_indexed(var, index, content, species, model, underscores, scope):
    name = rename(var, str(index + 1), underscores)
    if 'number' in content:
        value = terminal_value(content)
        if species:
            item = create_sbml_species(model, name, value)
        else:
            item = create_sbml_parameter(model, name, value)
        item.setConstant(False)
    else:
        if species:
            item = create_sbml_species(model, name, 0)
        else:
            item = create_sbml_parameter(model, name, 0)
        item.setConstant(False)
        translator = lambda pr: munge_reference(pr, scope, underscores)
        formula = MatlabGrammar.make_formula(content, atrans=translator)
        ast = parseL3Formula(formula)
        create_sbml_initial_assignment(model, name, ast)


def make_raterule(assigned_var, dep_var, index, content, model, underscores, scope):
    # Currently, this assumes there's only one math expression per row or
    # column, meaning, one subscript value per row or column.

    translator = lambda pr: munge_reference(pr, scope, underscores)
    string_formula = MatlabGrammar.make_formula(content, atrans=translator)
    if not string_formula:
        fail('Failed to parse the formula for row {}'.format(index + 1))

    # We need to rewrite matrix references "x(n)" to the form "x_n", and
    # rename the variable to the name used for the results assignment
    # in the call to the ode* function.
    xnameregexp = dep_var + '_'*underscores + r'(\d+)'
    newnametransform = assigned_var + '_'*underscores + r'\1'
    formula = re.sub(xnameregexp, newnametransform, string_formula)

    # Finally, write the rate rule.
    rule_var = assigned_var + '_'*underscores + str(index + 1)
    ast = parseL3Formula(formula)
    create_sbml_raterule(model, rule_var, ast)


# -----------------------------------------------------------------------------
# Translation code.
# -----------------------------------------------------------------------------
#
# Principles for the SBML "RateRule"-based version of the converter
# . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
#
# Matlab's ode* functions handle the following general problem:
#
#     Given a set of differential equations (with X denoting a vector),
#         dX/dt = f(t, X)
#     with initial values X(t_0) = xinit,
#     find the values of the variables X at different times t.
#
# The function defining the differential equations is given as "f" in a call
# to an ode* function such as ode45.  We assume the user provides a Matlab
# file such as the following (and here, the specific formula in the function
# "f" is just an example -- our code does not depend on the details of the
# function, and this is merely a realistic example from a real use case):
#
#     tspan  = [0 300];
#     xinit  = [0; 0];
#     a      = 0.01 * 60;
#     b      = 0.0058 * 60;
#     c      = 0.006 * 60;
#     d      = 0.000192 * 60;
#
#     [t, x] = ode45(@f, tspan, xinit);
#
#     function dx = f(t, x)
#       dx = [a - b * x(1); c * x(1) - d * x(2)];
#     end
#
# In the above, the function "f" passed to Matlab's ode45 is the function "f"
# in the general problem statement.  The body of "f" defines a vector of
# formulas for dx/dt for each variable x. The values of x at different times
# t is what the ode45 function computes.
#
# In create_raterule_model() below, we translate this directly into an SBML
# format that uses "rate rules" to directly encode the dx/dt expressions.
# This uses the name of the variable in the LHS matrix used in the assignment
# of the call to ode45 as the name of the independent variable.  So in other
# words, in the sample above, "x" will be the basis of the species or parameter
# names and the rate rules generated because that's what is used in [t, x] =...

def create_raterule_model(mparse, use_species=True):
    # This assumes there's only one call to an ode* function in the file.  We
    # start by finding that call (wherever it is -- whether it's at the top
    # level, or inside some other function), then inspecting the call, and
    # saving the name of the function handle passed to it as an argument.  We
    # also save the name of the 3rd argument (a vector of initial conditions).

    # Gather some preliminary info.
    working_scope = get_function_scope(mparse)
    underscores = num_underscores(working_scope) + 1

    # Look for a call to a MATLAB ode* function.
    ode_function = None
    call_arglist = None
    calls = get_all_function_calls(working_scope)
    for name, arglist in calls.items():
        if isinstance(name, str) and name.startswith('ode'):
            # Found the invocation of an ode function.
            call_arglist = arglist
            ode_function = name
            break

    if not ode_function:
        fail('Could not locate a call to a Matlab function in the file.')

    # Quick summary of pieces we'll gather.  Assume a file like this:
    #   xzero = [num1 num2 ...]                 --> "xzero" is init_cond_var
    #   [t, y] = ode45(@odefunc, tspan, xzero)  --> "y" is assigned_var
    #   function dy = odefunc(t, x)             --> "x" is dependent_var
    #       dy = [row1; row2; ...]              --> "dy" is output_var
    #   end                                     --> "odefunc" is handle_name

    # Identify the variables to which the output of the ode call is assigned.
    # It'll be a matrix of the form [t, y].  We want the name of the 2nd
    # variable.  Since it has to be a name, we can extract it using a regexp.
    # This will be the name of the independent variable for the ODE's.
    call_lhs = get_lhs_for_rhs(ode_function, working_scope)
    assigned_var = re.sub(r'\[[^\]]+,([^\]]+)\]', r'\1', call_lhs)

    # Matlab ode functions take a handle as 1st arg & initial cond. var as 3rd.
    # If the first arg is not a handle but a variable, we look up the variable
    # value if we can, to see if *that* is the handle.  If not, we give up.
    init_cond_var = call_arglist[2]['identifier']
    handle_name = None
    if 'function handle' in call_arglist[0]:
        # Case: ode45(@foo, time, xinit, ...) or ode45(@(args)..., time, xinit)
        function_data = call_arglist[0]['function handle']
        handle_name = parse_handle(function_data, working_scope, underscores)
    elif 'identifier' in call_arglist[0]:
        # Case: ode45(somevar, trange, xinit, ...)
        # Look up the value of somevar and see if that's a function handle.
        function_var = call_arglist[0]['identifier']
        if function_var in working_scope.assignments:
            value = working_scope.assignments[function_var]
            if 'function handle' in value:
                handle_name = parse_handle(value, working_scope, underscores)
            else:
                # Variable value is not a function handle.
                pass
        else:
            # We don't know the value of somevar.
            fail('{} is unknown'.format(function_var))

    if not handle_name:
        fail('Could not determine ODE function from call to {}'.format(ode_function))

    # If we get this far, let's start generating some SBML.

    document = create_sbml_document()
    model = create_sbml_model(document)
    compartment = create_sbml_compartment(model, 'comp1', 1)

    # Now locate our scope object for the function definition.  It'll be
    # defined either at the top level (if this file is a script) or inside
    # the scope of the file's overall function (if the file is a function).
    function_scope = get_function_declaration(handle_name, working_scope)
    if not function_scope:
        fail('Cannot locate definition for function {}'.format(handle_name))

    # The function form will have to be f(t, y), because that's what Matlab
    # requires.  We want to find out the name of the parameter 'y' in the
    # actual definition, so that we can locate this variable inside the
    # formula within the function.  We don't know what the user will call it,
    # so we have to use the position of the argument in the function def.
    dependent_var = function_scope.parameters[1]

    # Find the assignment to the initial condition variable, then create
    # either parameters or species (depending on the run-time selection) for
    # each entry.  The initial value of the parameter/species will be the
    # value in the matrix.
    init_cond = working_scope.assignments[init_cond_var]
    if 'array' not in init_cond.keys():
        fail('Failed to parse the assignment of the initial value matrix')
    mloop(init_cond['array'],
          lambda idx, item: make_indexed(assigned_var, idx, item, use_species,
                                         model, underscores, function_scope))

    # Now, look inside the function definition and find the assignment to the
    # function's output variable. (It corresponds to assigned_var, but inside
    # the function.)  This defines the formula for the ODE.  We expect this
    # to be a vector.  We take it apart, using each row as an ODE definition,
    # and use this to create SBML "rate rules" for the output variables.
    output_var = function_scope.returns[0]
    var_def = function_scope.assignments[output_var]
    if 'array' not in var_def:
        fail('Failed to parse the body of the function {}'.format(handle_name))
    mloop(var_def['array'],
          lambda idx, item: make_raterule(assigned_var, dependent_var, idx, item,
                                          model, underscores, function_scope))

    # Create remaining parameters.  This breaks up matrix assignments by
    # looking up the value assigned to the variable; if it's a matrix value,
    # then the variable is turned into parameters named foo_1, foo_2, etc.
    # Also, we have to decide what to do about duplicate variable names
    # showing up inside the function body and outside.  The approach here is
    # to have variables inside the function shadow ones outside, but we
    # should really check if something more complicated is going on in the
    # Matlab code.  The shadowing is done by virtue of the fact that the
    # creation of the dict() object for the next for-loop uses the sum of
    # the working scope and function scope dictionaries, with the function
    # scope taken second (which means its values are the final ones).

    skip_vars = [init_cond_var, output_var, assigned_var, call_arglist[1]['identifier']]
    all_vars = dict(itertools.chain(working_scope.assignments.items(),
                                    function_scope.assignments.items()))
    for var, rhs in all_vars.items():
        if var in skip_vars:
            continue
        # FIXME currently doesn't handle matrices on LHS.
        if name_is_structured(var):
            continue
        if 'number' in rhs:
            create_sbml_parameter(model, var, terminal_value(rhs))
        elif 'array' in rhs:
            mloop(rhs['array'],
                  lambda idx, item: make_indexed(var, idx, item, False, model,
                                                 underscores, function_scope))
        elif 'function handle' in rhs:
            # Skip function handles. If any was used in the ode* call, it will
            # have been dealt with earlier.
            continue
        elif 'array' not in rhs:
            translator = lambda pr: munge_reference(pr, function_scope, underscores)
            formula = MatlabGrammar.make_formula(rhs, atrans=translator)
            ast = parseL3Formula(formula)
            if ast is not None:
                create_sbml_parameter(model, var, 0)
                create_sbml_initial_assignment(model, var, ast)

    # Write the Model
    return writeSBMLToString(document)


# FIXME only handles 1-D matrices.
# FIXME grungy part for looking up identifier -- clean up & handle more depth

def munge_reference(pr, scope, underscores):
    matrix = pr['array']
    name = matrix['name']['identifier']
    if inferred_type(name, scope) != 'variable':
        return MatlabGrammar.make_key(pr)
    # Base name starts with one less underscore because the loop process
    # adds one in front of each number.
    constructed = name + '_'*(underscores - 1)
    for i in range(0, len(matrix['subscript list'])):
        element = matrix['subscript list'][i]
        i += 1
        if 'number' in element:
            constructed += '_' + str(element['number'])
        elif 'identifier' in element:
            # The subscript is not a number.  If it's a simple variable and
            # we've seen its value, we can handle it by looking up its value.
            assignments = get_all_assignments(scope)
            var_name = element['identifier']
            if var_name not in assignments:
                raise ValueError('Unable to handle matrix "' + name + '"')
            assigned_value = assignments[var_name]
            if 'number' in assigned_value:
                constructed += '_' + str(assigned_value['number'])
            else:
                raise ValueError('Unable to handle matrix "' + name + '"')
    return constructed


# -----------------------------------------------------------------------------
# Translation code.
# -----------------------------------------------------------------------------
#
# Principles for the XPP-based version of the converter
# . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
#
# Matlab's ode* functions handle the following general problem:
#
# Given a set of differential equations (with X denoting a vector),
#         dX/dt = f(t, X)
#     with initial values X(t_0) = xinit,
#     find the values of the variables X at different times t.
#
# The function defining the differential equations is given as "f" in a call
# to an ode* function such as ode45.  We assume the user provides a Matlab
# file such as the following (and here, the specific formula in the function
# "f" is just an example -- our code does not depend on the details of the
# function, and this is merely a realistic example from a real use case):
#
#     tspan  = [0 300];
#     xinit  = [0; 0];
#     a      = 0.01 * 60;
#     b      = 0.0058 * 60;
#     c      = 0.006 * 60;
#     d      = 0.000192 * 60;
#
#     [t, x] = ode45(@f, tspan, xinit);
#
#     function dx = f(t, x)
#       dx = [a - b * x(1); c * x(1) - d * x(2)];
#     end
#
# In the above, the function "f" passed to Matlab's ode45 is the function "f"
# in the general problem statement.  The body of "f" defines a vector of
# formulas for dx/dt for each variable x. The values of x at different times
# t is what the ode45 function computes.
#
# In create_xpp_elements() below, we translate this directly into an XPP
# format that uses "rate rules" to directly encode the dx/dt expressions.
# This uses the name of the variable in the LHS matrix used in the assignment
# of the call to ode45 as the name of the independent variable.  So in other
# words, in the sample above, "x" will be the basis of the species or parameter
# names and the rate rules generated because that's what is used in [t, x] =...

def substitute_vars(rhs, scope):
    for i in range(0, len(rhs)):
        var = MatlabGrammar.make_formula(rhs[i], False, False)
        lhs = get_assignment_rule(var, scope)
        if lhs is not None:
            rhs[i] = lhs
            return rhs
    return None


def create_xpp_elements(mparse, use_species=True):
    # This assumes there's only one call to an ode* function in the file.  We
    # start by finding that call (wherever it is -- whether it's at the top
    # level, or inside some other function), then inspecting the call, and
    # saving the name of the function handle passed to it as an argument.  We
    # also save the name of the 3rd argument (a vector of initial conditions).

    formula_parser = NumericStringParser()
    # Gather some preliminary info.
    working_scope = get_function_scope(mparse)
    underscores = num_underscores(working_scope) + 1

    # Look for a call to a MATLAB ode* function.
    ode_function = None
    call_arglist = None
    calls = get_all_function_calls(working_scope)
    for name, arglist in calls.items():
        if isinstance(name, str) and name.startswith('ode'):
            # Found the invocation of an ode function.
            call_arglist = arglist
            ode_function = name
            break

    if not ode_function:
        fail('Could not locate a call to a Matlab function in the file.')

    # Quick summary of pieces we'll gather.  Assume a file like this:
    #   xzero = [num1 num2 ...]                 --> "xzero" is init_cond_var
    #   [t, y] = ode45(@odefunc, tspan, xzero)  --> "y" is assigned_var
    #   function dy = odefunc(t, x)             --> "x" is dependent_var
    #       dy = [row1; row2; ...]              --> "dy" is output_var
    #   end                                     --> "odefunc" is handle_name

    # Identify the variables to which the output of the ode call is assigned.
    # It'll be a matrix of the form [t, y].  We want the name of the 2nd
    # variable.  Since it has to be a name, we can extract it using a regexp.
    # This will be the name of the independent variable for the ODE's.
    call_lhs = get_lhs_for_rhs(ode_function, working_scope)
    assigned_var = re.sub(r'\[[^\]]+,([^\]]+)\]', r'\1', call_lhs)

    # Matlab ode functions take a handle as 1st arg & initial cond. var as 3rd.
    # If the first arg is not a handle but a variable, we look up the variable
    # value if we can, to see if *that* is the handle.  If not, we give up.
    init_cond_var = call_arglist[2]['identifier']
    handle_name = None
    if 'function handle' in call_arglist[0]:
        # Case: ode45(@foo, time, xinit, ...) or ode45(@(args)..., time, xinit)
        function_data = call_arglist[0]['function handle']
        handle_name = parse_handle(function_data, working_scope, underscores)
    elif 'identifier' in call_arglist[0]:
        # Case: ode45(somevar, trange, xinit, ...)
        # Look up the value of somevar and see if that's a function handle.
        function_var = call_arglist[0]['identifier']
        if function_var in working_scope.assignments:
            value = working_scope.assignments[function_var]
            if 'function handle' in value:
                handle_name = parse_handle(value, working_scope, underscores)
            else:
                # Variable value is not a function handle.
                pass
        else:
            # We don't know the value of somevar.
            fail('{} is unknown'.format(function_var))

    if not handle_name:
        fail('Could not determine ODE function from call to {}'.format(
            ode_function))

    # If we get this far, let's start generating some constructs for XPP.

    xpp_variables = []
    xpp_variables = create_xpp_compartment(xpp_variables, 'comp1', 1)

    # Now locate our scope object for the function definition.  It'll be
    # defined either at the top level (if this file is a script) or inside
    # the scope of the file's overall function (if the file is a function).
    function_scope = get_function_declaration(handle_name, working_scope)
    if not function_scope:
        fail('Cannot locate definition for function {}'.format(handle_name))

    # The function form will have to be f(t, y), because that's what Matlab
    # requires.  We want to find out the name of the parameter 'y' in the
    # actual definition, so that we can locate this variable inside the
    # formula within the function.  We don't know what the user will call it,
    # so we have to use the position of the argument in the function def.
    dependent_var = function_scope.parameters[1]

    # Find the assignment to the initial condition variable, then create
    # either parameters or species (depending on the run-time selection) for
    # each entry.  The initial value of the parameter/species will be the
    # value in the matrix.
    init_cond = working_scope.assignments[init_cond_var]
    if 'array' not in init_cond.keys():
        fail('Failed to parse the assignment of the initial value matrix')
    mloop(init_cond['array'],
          lambda idx, item: make_xpp_indexed(assigned_var, idx, item, use_species,
                                         xpp_variables, underscores, function_scope))

    # Now, look inside the function definition and find the assignment to the
    # function's output variable. (It corresponds to assigned_var, but inside
    # the function.)  This defines the formula for the ODE.  We expect this
    # to be a vector.  We take it apart, using each row as an ODE definition,
    # and use this to create SBML "rate rules" for the output variables.
    output_var = function_scope.returns[0]
    var_def = function_scope.assignments[output_var]
    if 'array' not in var_def:
        fail('Failed to parse the body of the function {}'.format(handle_name))
    mloop(var_def['array'],
          lambda idx, item: make_xpp_raterule(assigned_var, dependent_var, idx,
                                          item,
                                          xpp_variables, underscores, function_scope))

    # Create remaining parameters.  This breaks up matrix assignments by
    # looking up the value assigned to the variable; if it's a matrix value,
    # then the variable is turned into parameters named foo_1, foo_2, etc.
    # Also, we have to decide what to do about duplicate variable names
    # showing up inside the function body and outside.  The approach here is
    # to have variables inside the function shadow ones outside, but we
    # should really check if something more complicated is going on in the
    # Matlab code.  The shadowing is done by virtue of the fact that the
    # creation of the dict() object for the next for-loop uses the sum of
    # the working scope and function scope dictionaries, with the function
    # scope taken second (which means its values are the final ones).

    skip_vars = [init_cond_var, output_var, assigned_var,
                 call_arglist[1]['identifier']]
    for var, rhs in dict(working_scope.assignments.items()
            + function_scope.assignments.items()).items():
        if var in skip_vars:
            continue
        # FIXME currently doesn't handle matrices on LHS.
        if name_is_structured(var):
            continue
        if 'number' in rhs:
            create_xpp_parameter(xpp_variables, var, terminal_value(rhs))
        elif 'array' in rhs:
            mloop(rhs['array'],
                  lambda idx, item: make_xpp_indexed(var, idx, item, False, xpp_variables,
                                                 underscores, function_scope))
        elif 'function handle' in rhs:
            # Skip function handles. If any was used in the ode* call, it will
            # have been dealt with earlier.
            continue
        elif 'array' not in rhs:
            translator = lambda pr: munge_reference(pr, function_scope,
                                                    underscores)
            rhs = substitute_vars(rhs, working_scope)
            formula = MatlabGrammar.make_formula(rhs, atrans=translator)
            if formula is not None or formula != '':
                result = formula_parser.eval(formula)
                create_xpp_parameter(xpp_variables, var, result, True, '', '')
                # create_xpp_initial_assignment(xpp_variables, var, formula)

    # Write the Model
#    return writeSBMLToString(document)
    return xpp_variables


def create_xpp_file(parse_results, use_species):
    print('in create xpp')
    xpp_elements = create_xpp_elements(parse_results)

    # create the lines of the file that will be the output
    lines = '#\n# This file is generated by MOCCASIN\n#\n\n'

    print(lines)
    num_objects = len(xpp_elements)

    # output functions for sbml
    #
    # dont need these for BioCham
    #
    # lines += '# some function definitions that are allowed in SBML'
    # lines += ' are not valid in xpp\nceil(x)=flr(1+x)\n\n'
    # lines += '@delay=50\n\n'

    # output compartments
    #
    # BioCham creates it's own dummy compartment
    # so dont do this
    #
    # for i in range(0,num_objects):
    #     if xpp_elements[i]['SBML_type'] == 'Compartment':
    #         id = xpp_elements[i]['id']
    #         value = xpp_elements[i]['value']
    #         lines += ('# Compartment id = {}, constant\n'.format(id))
    #         lines += ('par {}={}\n\n'.format(id, value))

    # output constant parameters
    for i in range(0, num_objects):
        element = xpp_elements[i]
        if element['SBML_type'] == 'Parameter':
            if element['constant'] is True:
                id = element['id']
                value = element['value']
                lines += ('# Parameter id = {}, constant\n'.format(id))
                # this does not seem to work
                # FIX ME
                if element['init_assign'] != '':
                    lines += ('par {}={}\n\n'.format(id, element['init_assign']))
                else:
                    lines += ('par {}={}\n\n'.format(id, value))
            elif element['rate_rule'] == '':
                id = element['id']
                value = element['value']
                lines += ('# Parameter id = {}, '
                          'non-constant but no rule supplied\n'.format(id))
                lines += ('par {}={}\n\n'.format(id, value))

    # output odes
    for i in range(0, num_objects):
        element = xpp_elements[i]
        if element['SBML_type'] == 'Parameter':
            if element['constant'] is False and element['rate_rule'] != '':
                id = element['id']
                value = element['value']
                formula = element['rate_rule']
                lines += ('# rateRule : variable = {}\n'.format(id))
                lines += ('init {}={}\n'.format(id, value))
                lines +=('d{}/dt={}\n\n'.format(id, formula))
        elif element['SBML_type'] == 'Species':
            id = element['id']
            value = element['value']
            formula = element['rate_rule']
            lines += ('# rateRule : variable = {}\n'.format(id))
            lines += ('init {}={}\n'.format(id, value))
            lines +=('d{}/dt={}\n\n'.format(id, formula))

    #output the sbml equivalent of variables
    for i in range(0, num_objects):
        element = xpp_elements[i]
        if element['SBML_type'] == 'Parameter':
            if element['constant'] is False and element['rate_rule'] != '':
                id = element['id']
                sbml = element['SBML_type']
                lines += ('# {}:   id = {}, defined by rule\n\n'
                          .format(sbml, id))
        elif element['SBML_type'] == 'Species':
            id = element['id']
            sbml = element['SBML_type']
            lines += ('# {}:   id = {}, defined by rule\n\n'.format(sbml, id))

    # output xpp specific code
    #
    # dont need this for BioCham
    #
    # lines += '@ meth=cvode, tol=1e-6, atol=1e-8\n'
    # lines += '# @ maxstor=1e6\n'
    # lines += '@ bound=40000, total=200\n'
    # lines += 'done\n\n'

    return lines


# -----------------------------------------------------------------------------
# Driver
# -----------------------------------------------------------------------------

def get_filename_and_options(argv):
    try:
        options, path = getopt.getopt(argv[1:], "dpqx")
    except:
        raise SystemExit(main.__doc__)
    if len(path) != 1 or len(options) > 2:
        raise SystemExit(main.__doc__)
    debug       = any(['-d' in y for y in options])
    quiet       = any(['-q' in y for y in options])
    print_parse = any(['-x' in y for y in options])
    use_species = not any(['-p' in y for y in options])
    return path[0], debug, quiet, print_parse, use_species


def main(argv):
    '''Usage: converter.py [options] FILENAME.m
Available options:
 -d   Drop into pdb before starting to parse the MATLAB input
 -h   Print this help message and quit
 -p   Turn variables into parameters (default: make them species)
 -q   Be quiet; just produce SBML, nothing else
 -x   Print extra debugging info about the interpreted MATLAB
'''
    path, debug, quiet, print_parse, use_species = get_filename_and_options(argv)

    file = open(path, 'r')
    file_contents = file.read()
    file.close()

    if not quiet:
        print('----- file ' + path + ' ' + '-'*30)
        print(file_contents)

    if debug:
        pdb.set_trace()

    try:
        parser = MatlabGrammar()
        parse_results = parser.parse_string(file_contents)
    except ParseException as err:
        print("error: {0}".format(err))

    if print_parse and not quiet:
        print('')
        print('----- interpreted output ' + '-'*50)
        parser.print_parse_results(parse_results)

    if not quiet:
        print('')
        print('----- SBML output ' + '-'*50)

    sbml = create_raterule_model(parse_results, use_species)
    print(sbml)


def fail(msg):
    raise SystemExit(msg)


if __name__ == '__main__':
    main(sys.argv)
