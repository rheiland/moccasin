function xdot = case00035(time,x)
%  synopsis:
%     xdot = case00035 (time, x)
%     x0 = case00035
%
%  case00035 can be used with odeN functions as follows:
%
%  x0 = case00035;
%  [t,x] = ode23s(@case00035, [0 100], case00035);
%  plot (t,x);
%
%  where 100 is the end time
%
%  When case00035 is used without any arguments it returns a vector of
%  the initial concentrations of the 4 floating species.
%  Otherwise case00035 should be called with two arguments:
%  time and x.  time is the current time. x is the vector of the
%  concentrations of the 4 floating species.
%  When these parameters are supplied case00035 returns a vector of 
%  the rates of change of the concentrations of the 4 floating species.
%
%  the following table shows the mapping between the vector
%  index of a floating species and the species name.
%  
%  NOTE for compartmental models
%  matlab translator generates code that when simulated in matlab, 
%  produces results which have the units of species amounts. Users 
%  should divide the results for each species with the volume of the
%  compartment it resides in, in order to obtain concentrations.
%  
%  Indx      Name
%  x(1)        S1
%  x(2)        S2
%  x(3)        S3
%  x(4)        S4

xdot = zeros(4, 1);

% List of Compartments 
vol__compartment = 1;		%compartment

% Global Parameters 
g_p1 = 750;		% k1
g_p2 = 250;		% k2

% Local Parameters

if (nargin == 0)

    % set initial conditions
   xdot(1) = 0.001;		% S1 = S1 [Amount]
   xdot(2) = 0.001;		% S2 = S2 [Amount]
   xdot(3) = 0.002;		% S3 = S3 [Amount]
   xdot(4) = 0.001;		% S4 = S4 [Amount]

else

    % calculate rates of change
   R0 = vol__compartment*g_p1*(x(1))*(x(2));
   R1 = vol__compartment*g_p2*(x(3))*(x(4));

   xdot = [
      - R0 + R1
      - R0 + R1
      + R0 - R1
      + R0 - R1
   ];
end;


function z = pow (x, y) 
    z = x^y; 


function z = sqr (x) 
    z = x*x; 


function z = piecewise(varargin) 
		numArgs = nargin; 
		result = 0; 
		foundResult = 0; 
		for k=1:2: numArgs-1 
			if varargin{k+1} == 1 
				result = varargin{k}; 
				foundResult = 1; 
				break; 
			end 
		end 
		if foundResult == 0 
			result = varargin{numArgs}; 
		end 
		z = result; 


function z = gt(a,b) 
   if a > b 
   	  z = 1; 
   else 
      z = 0; 
   end 


function z = lt(a,b) 
   if a < b 
   	  z = 1; 
   else 
      z = 0; 
   end 


function z = geq(a,b) 
   if a >= b 
   	  z = 1; 
   else 
      z = 0; 
   end 


function z = leq(a,b) 
   if a <= b 
   	  z = 1; 
   else 
      z = 0; 
   end 


function z = neq(a,b) 
   if a ~= b 
   	  z = 1; 
   else 
      z = 0; 
   end 


function z = and(varargin) 
		result = 1;		 
		for k=1:nargin 
		   if varargin{k} ~= 1 
		      result = 0; 
		      break; 
		   end 
		end 
		z = result; 


function z = or(varargin) 
		result = 0;		 
		for k=1:nargin 
		   if varargin{k} ~= 0 
		      result = 1; 
		      break; 
		   end 
		end 
		z = result; 


function z = xor(varargin) 
		foundZero = 0; 
		foundOne = 0; 
		for k = 1:nargin 
			if varargin{k} == 0 
			   foundZero = 1; 
			else 
			   foundOne = 1; 
			end 
		end 
		if foundZero && foundOne 
			z = 1; 
		else 
		  z = 0; 
		end 
		 


function z = not(a) 
   if a == 1 
   	  z = 0; 
   else 
      z = 1; 
   end 


function z = root(a,b) 
	z = a^(1/b); 
 



