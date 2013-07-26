'''
.. module:: fit
   :platform: Unix
   :synopsis: This submodule defines a `Fit` object which performs the actual fitting given a `Dataset` and a fit function.

.. moduleauthor:: Daniel Savoiu <daniel.savoiu@ekp.kit.edu>

'''

from minuit import Minuit
from function_tools import get_function_property, outer_product, derive_by_x
from copy import copy

from numeric_tools import *                 # automatically includes numpy as np
from constants import F_SIGNIFICANCE
from math import floor, log

# The default FCN
def chi2(xdata, ydata, cov_mat, fit_function, param_values):
    r'''
    A simple :math:`\chi^2` implementation. Calculates :math:`\chi^2` according to the formula:
    
    .. math::
    
        \chi^2 = \lambda^T C^{-1} \lambda
    
    Here, :math:`\lambda` is the residual vector :math:`\lambda = \vec{y} - \vec{f}(\vec{x})` and
    :math:`C` is the covariance matrix.
    
    **xdata** : iterable
        The *x* measurement data
        
    **ydata** : iterable
        The *y* measurement data
        
    **cov_mat** : `numpy.matrix`
        The total covariance matrix
        
    **fit_function** : function
        The fit function :math:`f(x)`
        
    **param_values** : list/tuple
        The values of the parameters at which :math:`f(x)` should be evaluated.
    
    '''
    
    # since the param_values are constants, the
    # fit function is a function of only one
    # variable: `x'. To apply it elementwise using
    # Python's `map' method, make a temporary
    # function where `x' is the only variable:
    def tmp_fit_function(x):
        return fit_function(x, *param_values)

    fdata = np.asarray(map(tmp_fit_function, xdata))        # calculate f(x) for all x in xdata
    residual = ydata - fdata                                # calculate residual vector

    return residual.T.dot(cov_mat.I).dot(residual)          # return the chi^2

def round_to_significance(value, error, significance=F_SIGNIFICANCE):
    '''
    Rounds the error to the established number of significant digits, then rounds the value to the same
    order of magnitude as the error.
    
    **value** : float
        value to round to significance
        
    **error** : float
        uncertainty of the value
        
    *significance* : int (optional)
        number of significant digits of the error to consider
        
    '''
    # round error to F_SIGNIFICANCE significant digits
    significant_digits = int(-floor(log(error)/log(10))) + significance - 1
    error = round(error, significant_digits)
    value = round(value, significant_digits)
    return (value, error)
    

class Fit:
    '''
    Object representing a fit. This object references the fitted `Dataset`, the fit function and the resulting fit parameters.
    
    Necessary arguments are a `Dataset` object and a fit function (which should be fitted to the `Dataset`).
    Optionally, an external function `FCN` (whose minima should be located to find the best fit) can be specified.
    If not given, the `FCN` function defaults to :math:`\chi^2`.
    
    **dataset** : `Dataset`
        A `Dataset` object containing all information about the data
    
    **fit_function** : function
        A user-defined Python function to be fitted to the data. This function's first argument must be the 
        independent variable `x`. All other arguments *must* be named and have default values given. These
        defaults are used as a starting point for the actual minimization. For example, a simple linear function
        would be defined like:
        
        >>> def linear_2par(x, slope=1, y_intercept=0):
        ...     return slope * x + y_intercept
        
        Be aware that choosing sensible initial values for the parameters is often crucial for a succesful fit,
        particularly for functions of many parameters.

    *external_fcn* : function (optional)
        An external `FCN` (function to minimize). This function must have the following call signature:
        
        >>> FCN(xdata, ydata, cov_mat, fit_function, param_values)
        
        It should return a float. If not specified, the default :math:`\chi^2` `FCN` is used. This should
        be sufficient for most fits.

    *function_label* : :math:`\LaTeX`-formatted string (optional)
        A name/label/short description of the fit function. This appears in the legend describing the fitter curve.
        If omitted, this defaults to the function's Python name.
        
    *function_equation* : :math:`\LaTeX`-formatted string (optional)
        The fit function's equation.
    '''
    
    def __init__(self, dataset, fit_function, external_fcn=chi2, function_label=None, function_equation=None):
        '''
        Construct a fit. 
        '''
        
        # Initialize instance variables
        
        self.dataset = dataset
        
        self.fit_function = fit_function    # refer to the fit function
        self.external_fcn = external_fcn    # refer to the (external) function to me minimized
        
        self.number_of_parameters = get_function_property(self.fit_function, 'number of parameters')    # set param number
        self.current_param_values = get_function_property(self.fit_function, 'parameter defaults')      # set current params to default
        self.param_names = get_function_property(self.fit_function, 'parameter names')                  # set parameter names
        self.param_names_latex = map(lambda tmp_string: r'\verb!'+tmp_string+'!', self.param_names)     # set parameter names
        
        if function_label is not None:
            self.function_label = function_label     # get the function name from the arguments
        else:
            self.function_label = r'\verb!%s!' % ( get_function_property(self.fit_function, 'name'), )   # get the function name and wrap it in LaTeX
            
        self.function_equation = function_equation # get the function equation (if provided)
        
        if self.dataset.has_errors('y'):                                                            # check if the dataset has any y errors at all
            #self.current_cov_mat = self.dataset.get_cov_mat('y', fallback_on_singular='identity')  # set the y cov_mat as starting cov_mat for the fit (use identity matrix if singular)
            self.current_cov_mat = self.dataset.get_cov_mat('y', fallback_on_singular='report')     # set the y cov_mat as starting cov_mat for the fit (report if singular matrix)
        else:
            self.current_cov_mat = np.asmatrix( np.eye(self.dataset.get_size()) )                   # set the identity matrix as starting cov_mat for the fit
        
        self.minimizer = Minuit(self.number_of_parameters, self.call_external_fcn, self.param_names, self.current_param_values, None)   # initialize minimizer for fit
        self.minimizer.set_parameter_values(self.current_param_values)        # set Minuit's start parameters
        self.minimizer.set_parameter_errors()                                 # set Minuit's parameter errors
        
        
        # Store measurement data locally in Fit object
        self.xdata = self.dataset.get_data('x')
        self.ydata = self.dataset.get_data('y')
        
    
    def call_external_fcn(self, *param_values):
        '''
        Wrapper for the external `FCN`. Since the actual fit process depends on finding the right parameter
        values and keeping everything else constant, we can use the `Dataset` object to pass known, fixed
        information to the external `FCN`, varying only the parameter values.
        
        **param_values** : sequence of values
            the parameter values at which `FCN` is to be evaluated

        '''
        
        return self.external_fcn(self.xdata, self.ydata, self.current_cov_mat, self.fit_function, param_values) 
        
    def get_current_fit_function(self):
        '''
        This method returns a function object corresponding to the fit function
        for the current parameter values. The returned function is a function of
        a single variable.

        returns : function
            A function of a single variable corresponding to the fit function at the
            current parameter values.
        '''
        def current_fit_function(x):
            return self.fit_function(x, *self.current_param_values)
        
        return current_fit_function
    
    def get_error_matrix(self):
        '''
        This method returns the covariance matrix of the fit parameters which is obtained
        by querying the minimizer object for this fit
        
        returns : `numpy.matrix`
            The covariance matrix of the parameters.
        '''
        return self.minimizer.get_error_matrix()
    
    def get_parameter_errors(self, rounding=False):
        '''
        Get the current parameter uncertainties from the minimizer.
        
        *rounding* : boolean
            Whether or not to round the returned values to significance.
        
        returns : tuple
            A tuple of the parameter uncertainties
        '''
        output = []
        for name, value, error in self.minimizer.get_parameter_info():
            
            if rounding:
                value, error = round_to_significance(value, error)
            output.append(error)
            
        return tuple(output)
    
    def get_parameter_values(self, rounding=False):
        '''
        Get the current parameter values from the minimizer.
        
        *rounding* : boolean
            Whether or not to round the returned values to significance.
        
        returns : tuple
            A tuple of the parameter values
        '''
        
        output = []
        for name, value, error in self.minimizer.get_parameter_info():
            
            if rounding:
                value, error = round_to_significance(value, error)
            output.append(value)
            
        return tuple(output)
    
    def do_fit(self, quiet=False, verbose=False):
        '''
        Runs the fit algorithm for this `Fit` object.
        
        First, the `Dataset` is fitted considering only uncertainties in the `y` direction.
        If the `Dataset` has no uncertainties in the `y` direction, they are assumed to be 
        equal to 1.0 for this preliminary fit, as there is no better information available.
        
        Next, the fit errors in the `x` direction (if they exist) are taken into account by
        projecting the covariance matrix for the `x` errors onto the `y` covariance matrix.
        This is done by taking the first derivative of the fit function in each point and
        "projecting" the `x` error onto the resulting tangent to the curve.
        
        This last step is repeater until the change in the error matrix caused by the projection
        becomes negligible.
        
        *quiet* : boolean
            Set to ``True`` if no output should be printed.
            
        *verbose* : boolean
            Set to ``True`` if more output should be printed.
        '''
        
        if not quiet:
            print "###########"
            print "# Dataset #"
            print "###########"
            print ''
            print self.dataset.get_formatted()
            
            print "################"
            print "# Fit function #"
            print "################"
            print ''
            print get_function_property(self.fit_function, 'name')
            print ''
            
        initial_iterations = 2 
        max_x_iterations = 12
        
        iter_nr = 0
        while iter_nr < initial_iterations:
            self.fit_one_iteration(verbose)
            iter_nr += 1
            
            
        # if the dataset has x errors, project them onto the current error matrix
        if self.dataset.has_errors('x'):
        
            iter_nr = 0
            while iter_nr < max_x_iterations:    
                old_matrix = copy(self.current_cov_mat)
                
                self.project_x_covariance_matrix()
                self.fit_one_iteration(verbose)
                
                new_matrix = self.current_cov_mat
                
                # if the matrix has not changed in this iteration
                if np.allclose(old_matrix, new_matrix, atol=1e-10, rtol=1e-8):
                    break   # interrupt iteration
                
                iter_nr += 1
        
        self.print_fit_results()
        self.print_rounded_fit_parameters()
        self.print_fit_details()
        
    def fit_one_iteration(self, verbose=False):
        '''
        Instructs the minimizer to do a minimization.
        '''
        
        
        # self.minimizer.set_print_level(-1000)
        ##print self.current_cov_mat
        
        self.minimizer.minimize()
        self.current_param_values = self.minimizer.get_parameter_values()
        
        #self.print_rounded_fit_parameters()
        
        par_cov_mat = self.get_error_matrix()
        #par_errs = np.diag(par_cov_mat)
        #print par_cov_mat
            
        
        # self.minimizer.set_print_level(0)
      
    def project_x_covariance_matrix(self):
        r'''
        Project the `x` errors from the `x` covariance matrix onto the total matrix.
        
        This is done elementwise, according to the formula:
        
        .. math ::
            
            C_{\text{tot},ij} = C_{y,ij} + C_{x,ij}  \frac{\partial f}{\partial x_i}  \frac{\partial f}{\partial x_j} 
        '''
        
        derivative_spacing = 0.01 * np.sqrt(min(np.diag(self.get_error_matrix())))    # use 1/100th of the smallest parameter error as spacing for df/dp
        proj_xcov_mat = np.asarray(self.dataset.get_cov_mat('x')) * outer_product( derive_by_x(self.fit_function, self.dataset.get_data('x'), self.current_param_values, derivative_spacing) ) 
        
        self.current_cov_mat = self.dataset.get_cov_mat('y') + np.asmatrix(proj_xcov_mat)
        
                
        ##print self.current_cov_mat
    
    def print_rounded_fit_parameters(self):
        '''prints the fit parameters'''
        
        print "########################"
        print "# Final fit parameters #"
        print "########################"
        print ''
        
        for name, value, error in self.minimizer.get_parameter_info():
            
            tmp_rounded = round_to_significance(value, error, F_SIGNIFICANCE)
            
            print "%s = %g +- %g" % (name, tmp_rounded[0], tmp_rounded[1])
        
        print ''
    
    def print_fit_details(self):
        '''prints some fit goodness details'''
        
        chi2prob = self.minimizer.get_chi2_probability(self.dataset.get_size() - self.number_of_parameters)
        if chi2prob < 0.05:
            hypothesis_status = 'rejected (CL 5%)'
        else:
            hypothesis_status = 'accepted (CL 5%)'
            
        print '###############'
        print "# Fit details #"
        print "###############"
        print ''
        print 'FCN     ', self.minimizer.get_fit_info('fcn')
        print 'FCN/ndf ', self.minimizer.get_fit_info('fcn')/(self.dataset.get_size() - self.number_of_parameters)
        print 'EdM     ', self.minimizer.get_fit_info('edm')
        print 'UP      ', self.minimizer.get_fit_info('err_def')
        print 'STA     ', self.minimizer.get_fit_info('status_code')
        print ''
        print 'chi2prob', chi2prob
        print 'H0      ', hypothesis_status
        print ''
        
        
    def print_fit_results(self):
        '''prints fit results'''
        
        print '##############'
        print '# Fit result #'
        print '##############'
        print ''
        
        par_cov_mat = self.get_error_matrix()
        par_err = extract_statistical_errors(par_cov_mat)
        par_cor_mat = cov_to_cor(par_cov_mat)
        
        
        for par_nr in range(len(self.current_param_values)):
            print '# '+self.param_names[par_nr]
            print '# value        stat. err.    ',
            if par_nr > 0:
                print 'correlations'
            else:
                print ''
            print format(self.current_param_values[par_nr], '.06e')+'  ',
            print format(par_err[par_nr], '.06e')+'  ',
            if par_nr > 0:
                for i in range(par_nr):
                    print format(par_cor_mat[par_nr, i], '.06e')+'  ',
                    
            print ''
            print ''

        
if __name__ == '__main__':
    
    from dataset import Dataset, build_dataset
    
    def linear_2par2(x, slope=1, x_offset=0):
        
        return slope * (x - x_offset)
    
    def linear_2par(x, slope=1, y_intercept=0):
        
        return slope * x + y_intercept
    
    myXData = np.asarray([0., .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.])
    myYData = np.asarray([0.227216,    -0.159875,    0.0924984,    -0.299377,    0.307159,    1.15718,    0.701532,    0.661879,    0.536548,    0.874998,    1.02603])
    tstFloat = 0.3
     
    myDataset = build_dataset(xdata=myXData, 
                              ydata=myYData,
                              xabsstat=tstFloat)
    
    myFit = Fit(myDataset, linear_2par2)
    myFit.do_fit()
    
#     myDataset = Dataset(xdata=myXData, 
#                         ydata=myYData,
#                         xabsstat=tstFloat)
#     
#     myFit = myDataset.fit(linear_2par2)
#     myFit.do_fit()
    
    myDataset2 = build_dataset(xdata=myXData, 
                               ydata=myYData,
                               xabssyst=tstFloat)
    
    myFit2 = Fit(myDataset2, linear_2par2)
    myFit2.do_fit()
    