from __future__ import print_function
from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand
from codecs import open
from os import path
import re
import sys 
import moccasin

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'requirements.txt')) as f:
    reqs = f.read().rstrip().encode("utf-8").splitlines()

class PyTest(TestCommand):
    user_options = [('pytest-args=', 'a', "Arguments to pass to py.test")]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.pytest_args = []

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        #import here, cause outside the eggs aren't loaded
        import pytest
        errno = pytest.main(self.pytest_args)
        sys.exit(errno)

setup(
    name='moccasin',
    version=moccasin.__version__,
    url='https://github.com/sbmlteam/moccasin/',
    license='GNU Lesser General Public License',
    author='Michael Hucka, Sarah Keating, and Harold Gomez',
    tests_require=['pytest'],
    #add pytest-cov but place before pytest or it will fail
    install_requires=reqs,
    cmdclass={'test': PyTest},
    author_email='email@sbml.com',
    description='User-assisted converter that can take MATLAB or Octave ODE-based models in biology and translate them into SBML format',
    packages=find_packages(exclude='test'),
##  package_data={'moccasin': ['docs/*.txt','COPYING.txt']},
    include_package_data=True,
    platforms='any',
    test_suite='tests',
    classifiers = [
        'Programming Language :: Python',
        'Development Status :: 4 - Beta',
        'Natural Language :: English',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Lesser General Public License',
        'Operating System :: OS Independent'
        ],
## scripts = ['command-line-interface.py'],
)
