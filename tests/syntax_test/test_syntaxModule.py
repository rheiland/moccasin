#!/usr/bin/env python

import pytest
import sys
import glob
from pyparsing import ParseResults
sys.path.append('moccasin/')
from matlab_parser import *

#Generates (multiple) parametrized calls to a test function
def pytest_generate_tests(metafunc):
    # called once per each test function
    funcarglist = metafunc.cls.params[metafunc.function.__name__]
    argnames = list(funcarglist[0])
    metafunc.parametrize(argnames, [[funcargs[name] for name in argnames]
            for funcargs in funcarglist])

#Parses the file and prints interpreted result(output is captured)                       
def build_model(path):
    file = open(path,'r')
    contents = file.read()
    parser = MatlabGrammar()
    try:
        results = parser.parse_string(contents, fail_soft=True)
        file.close()
        parser.print_parse_results(results)
    except Exception as e:
        print(e)
   
#reads file containing expected parsed model and returns it as string
def read_parsed (path):
    file = open(path,'r')
    contents = file.read()
    file.close()
    return contents

# Constructs the params dictionary for test function parametrization
def obtain_params():
    matlab_models=glob.glob("tests/syntax_test/syntax-test-cases/*.m")
    parsed_models=glob.glob("tests/syntax_test/syntax-test-cases/*.txt")
    pairs=list()
    for i in range(len(matlab_models)):
        pairs.append((dict(model= matlab_models[i],parsed=parsed_models[i])))
    parameters={'test_syntaxCases':pairs}
    return parameters

class TestClass:
    # a map specifying multiple argument sets for a test method
    params = obtain_params()
    
    def test_syntaxCases(self,capsys,model,parsed):
        build_model(model)
	out,err=capsys.readouterr()        
        assert out.strip()== read_parsed(parsed).strip()        
