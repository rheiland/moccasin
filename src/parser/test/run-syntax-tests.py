#!/usr/bin/env python

import glob, sys
from pyparsing import ParseException
sys.path.append('..')
sys.path.append('../../utilities')
from matlab_parser import parse_string

for f in glob.glob("syntax-test-cases/valid*.m"):
    print '===== ' + f + ' ' + '='*30
    file = open(f, 'r')
    contents = file.read()
    print contents.rstrip()
    print '----- output ' + '-'*30
    try:
        parse_string(contents)
    except ParseException as err:
        print("error: {0}".format(err))
    print ''