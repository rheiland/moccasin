MOCCASIN
========
<img src="https://raw.githubusercontent.com/sbmlteam/moccasin/develop/dev/graphics/logo/MOCCASIN%20basic%20logo%20200%20px%20wide.png"
 alt="MOCCASIN logo" title="MOCCASIN" align="right" />

*MOCCASIN* stands for *"Model ODE Converter for Creating Awesome SBML INteroperability"*.  MOCCASIN is designed to convert certain basic forms of ODE simulation models written in MATLAB or Octave and translate them into [SBML](http://sbml.org) format.  It thereby enables researchers to convert MATLAB models into an open and widely-used format in systems biology.

[![Build Status](https://travis-ci.org/sbmlteam/moccasin.svg?branch=master)](https://travis-ci.org/sbmlteam/moccasin)

----
*Authors*:      [Michael Hucka](http://www.cds.caltech.edu/~mhucka), [Sarah Keating](http://www.ebi.ac.uk/about/people/sarah-keating), and [Harold G&oacute;mez](http://www.bu.edu/computationalimmunology/people/harold-gomez/).

*License*:      This code is licensed under the LGPL version 2.1.  Please see the file [../LICENSE.txt](https://raw.githubusercontent.com/sbmlteam/moccasin/master/LICENSE.txt) for details.

*Repository*:   [https://github.com/sbmlteam/moccasin](https://github.com/sbmlteam/moccasin)

*Developers' discussion group*: [https://groups.google.com/forum/#!forum/moccasin-dev](https://groups.google.com/forum/#!forum/moccasin-dev)

*Pivotal tracker*: [https://www.pivotaltracker.com/n/projects/977060](https://www.pivotaltracker.com/n/projects/977060)


Background
----------

Computation modeling has become a crucial aspect of biological research, and [SBML](http://sbml.org) (the Systems Biology Markup Language) has become the de facto standard open format for exchanging models between software tools in systems biology. [MATLAB](http://www.mathworks.com) and [Octave](http://www.gnu.org/software/octave/) are popular numerical computing environments used by modelers in biology, but while toolboxes for using SBML exist, many researchers either have legacy models or do not learn about the toolboxes before starting their work and then find it discouragingly difficult to export their MATLAB/Octave models to SBML.

The goal of this project is to develop software that uses a combination of heuristics and user assistance to help researchers export models written as ordinary MATLAB and Octave scripts. MOCCASIN (*"Model ODE Converter for Creating Awesome SBML INteroperability"*) helps researchers take ODE (ordinary different equation) models written in MATLAB and Octave and export them as SBML files.  Although its scope is limited to MATLAB written with certain assumptions, and general conversion of MATLAB models is impossible, MOCCASIN nevertheless *can* translate some common forms of models into SBML.

MOCCASIN is written in Python and does _not_ require MATLAB to run.  It requires [libSBML](http://sbml.org/Software/libSBML) and a number of common Python libraries to run, and is compatible with Python 2.7 and 3.3.

How it works
------------

MOCCASIN uses an algorithm developed by Fages, Gay and Soliman described in the paper titled [_Inferring reaction systems from ordinary differential equations_](http://www.sciencedirect.com/science/article/pii/S0304397514006197).  A free technical report explaining the algorithm is [available from INRIA](https://hal.inria.fr/hal-01103692).  To parse MATLAB and produce input to the reaction-inference algorithm, MOCCASIN uses a custom MATLAB parser written using [PyParsing](https://pyparsing.wikispaces.com) and a variety of post-processing operations to interpret the MATLAB contents.

Currently, MOCCASIN is limited to MATLAB inputs in which a model is contained in a single file.  The file must set up a system of differential equations as a function defined in the file, and make a call to one of the MATLAB `odeNN` family of solvers (e.g., `ode45`, `ode15s`, etc.).  The following is a simple but complete example:

```
# Various parameter settings.  The specifics here are unimportant; this
# is just an example of a real input file.
#
tspan  = [0 300];
xinit  = [0; 0];
a      = 0.01 * 60;
b      = 0.0058 * 60;
c      = 0.006 * 60;
d      = 0.000192 * 60;

# A call to a MATLAB ODE solver
#
[t, x] = ode45(@f, tspan, xinit);

# A function that defines the ODEs of the model.
#
function dx = f(t, x)
  dx = [a - b * x(1); c * x(1) - d * x(2)];
end
```

You can view the SBML output for this example [in a separate file](docs/project/examples/example.xml).  MOCCASIN assumes that the second parameter in the ODE function definition determines the variables that should identify the SBML species; thus, the output generated by MOCCASIN will have SBML species named `x_1` and `x_2` by default.  (The use of suffixes is necessary because plain SBML does not support arrays or vectors.)  The output will also not capture any information about the particular ODE solver or the start/stop/configuration parameters used in the file, because that kind of information is not meant to be stored in SBML files anyway.  (A future verion of MOCCASIN will hopefully translate the additional run information into [SED-ML](http://sed-ml.org) format.)


Installation
------------

Before installing MOCCASIN, you need to separately install the following software that MOCCASIN depends upon:

* [libSBML](http://sbml.org/Software/libSBML/Downloading_libSBML#If_you_use_Python), which in turn depends on the following packages:
  * `python-dev`
  * `libxml2-dev`
  * `libz-dev`
  * `libbz2-dev`

Once that is done, you can download or clone the MOCCASIN source code base and then run

```
python setup.py
```

Using MOCCASIN
--------------

You can use MOCCASIN either via the command line or via the GUI interface.  To start the MOCCASIN GUI, execute the Python command `moccasin/interfaces/Moccasin_GUI.py` in the source directory.  A screenshot of the GUI in action is shown below.

<img src="https://raw.githubusercontent.com/sbmlteam/moccasin/develop/docs/project/examples/screenshot-01.jpg"
 alt="MOCCASIN GUI" title="MOCCASIN GUI" align="center" />


Getting Help
------------

MOCCASIN is under active development by a distributed team.  If you have any questions, please feel free to post or email on the developer's discussion group  ([https://groups.google.com/forum/#!forum/moccasin-dev](https://groups.google.com/forum/#!forum/moccasin-dev)) or contact the main developers directly.


Contributing
------------

A lot remains to be done on MOCCASIN in many areas, from improving the interpretation of MATLAB to adding support for SED-ML.  We would be happy to receive your help and participation if you are interested.  Please feel free to contact the developers.


Funding acknowledgments
-----------------------

This work is made possible thanks in part to funding from the Icahn School of Medicine at Mount Sinai, provided as part of the NIH-funded project *Modeling Immunity for Biodefense* (Principal Investigator: [Stuart Sealfon](http://www.mountsinai.org/profiles/stuart-c-sealfon)).


Copyright and license
---------------------

Copyright (C) 2014-2015 jointly by the California Institute of Technology (Pasadena, California, USA), the Icahn School of Medicine at Mount Sinai (New York, New York, USA), and Boston University (Boston, Massachusetts, USA).

This library is free software; you can redistribute it and/or modify it under the terms of the GNU Lesser General Public License as published by the Free Software Foundation; either version 2.1 of the License, or any later version.

This software is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY, WITHOUT EVEN THE IMPLIED WARRANTY OF MERCHANTABILITY OR FITNESS FOR A PARTICULAR PURPOSE.  The software and documentation provided hereunder is on an "as is" basis, and the California Institute of Technology has no obligations to provide maintenance, support, updates, enhancements or modifications.  In no event shall the California Institute of Technology be liable to any party for direct, indirect, special, incidental or consequential damages, including lost profits, arising out of the use of this software and its documentation, even if the California Institute of Technology has been advised of the possibility of such damage.  See the GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with this library in the file named "COPYING.txt" included with the software distribution.
