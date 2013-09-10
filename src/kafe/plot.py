'''
.. module:: plot
   :platform: Unix
   :synopsis: A submodule for plotting `Dataset`s with ``matplotib``.
.. moduleauthor:: Daniel Savoiu <danielsavoiu@gmail.com>
'''

import matplotlib as mpl
mpl.use('Qt4AGG')    # use the Qt backend for mpl

import matplotlib.pyplot as plt
from numeric_tools import * # includes importing numpy as np
from function_tools import *
from constants import *
from fit import round_to_significance
import re # some regular expression stuff
from string import split, join, lower

def label_to_latex(label):
    '''
    Generates a simple LaTeX-formatted label from a plain-text label.
    This treats isolated characters and words beginning with a backslash
    as mathematical expressions and surround them with $ signs accordingly.

    **label** : string
        Plain-text string to convert to LaTeX.
    '''

    tokens = split(label)
    for token_id, token in tokens.enumerate():
        if len(token) == 1 or token[0]=='\\':
            if lower(token[-1]) not in "abcdefghijklmnopqrstuvwxyz":
                tokens[token_id] = '$%s$%s' % (token[:-1],token[-1]) # surround isolated chars with $ (omit last)
            else: 
                tokens[token_id] = '$%s$' % (token,) # surround isolated chars with $
    return join(tokens)

def pad_span(span, pad_coeff=1, additional_pad=None):
    '''
    Enlarges the interval `span` (list of two floats) symmetrically around
    its center to length `pad_coeff`. Optionally, an `additional_pad` argument
    can be specified. The returned span is then additionally enlarged by that amount. 

    `additional_pad` can also be a list of two floats which specifies an asymmetric
    amount by which to enlarge the span. Note that in this case, positive entries in
    `additional_pad` will enlarge the span (move the interval end away from the
    interval's center) and negative amounts will shorten it (move the interval end
    towards the interval's center).
    '''

    try:
        len(span)
    except:
        raise TypeError, "Span passed to pad_span must be an iterable type (got %s)" % type(span)

    if len(span) != 2:
        raise IndexError, "Span passed to pad_span must be an iterable of length 2 (got %d)" % (len(span),)

    if additional_pad is None:
        additional_pad = [0, 0]
    else:
        try:
            # check if the additional_pad argument value is iterable (list or array)
            # by trying to get its iterator.
            iterator = iter(additional_pad)
        except TypeError:
            # if this fails, then this object is not iterable
            additional_pad = [additional_pad, additional_pad]   # turn into list of identical elements
        else:
            if len(additional_pad) != 2:
                raise IndexError, "Additional pad passed to pad_span is not an iterable of length 2 (got %d)" % (len(additional_pad),)

    width = span[1] - span[0]   # store the interval width in an explicit variable

    if width == 0:
        return list(span)  # Zero - width intervals cannot be padded

    return list( (0.5 * (span[0] + span[1] - width * pad_coeff) - additional_pad[0], 0.5 * (span[0] + span[1] + width * pad_coeff) + additional_pad[1]) )    

class PlotStyle:
    '''
    Class for specifying a style for a specific plot. This object stores a progression of marker and line types and
    colors, as well as preferences relating to point size and label size. These can be overriden
    by overwriting the instance variables directly. A series of `get_...` methods are provided which
    go through these lists cyclically.
    '''

    def __init__(self):
        '''
        Construct a default plot style.
        '''

        # Define a progression of matplotlib marker and line styles, as well as colors
        self.markers = ['o','^','s','D','v','h','*','+','x']
        self.lines = ['-','--','-.',':']
        self.markercolors = ['r','b','g','c','m','k']
        self.linecolors = ['r','b','g','c','m','k']

        # Define a progression of point sizes
        self.pointsizes = [7]

        # Set other style properties
        self.labelsize = 12     # make labels large
        self.grid = True        # use a grid per default
        self.usetex = True      # tell matplotlib to use TeX

        self.axis_label_styles = ('italic', 'italic')       # Default axis label styles
        self.axis_label_coords = ( (.5, -.1), (-.12, .5) )  # default offset for axes
        self.axis_label_pad = (7, 7)                        # padding for axis labels

        # Set legend parameters
        self.legendparams_kw = {
          'ncol': 1,
          #'fancybox': True,
          'shadow': True,
          'numpoints': 1,
          'bbox_to_anchor': (1.05, 1.),
          'borderaxespad' : 0.,
          'pad':0.05
          }

        # Default keyword arguments to pass to rc('font',...)
        self.rcfont_kw = {'family':'serif', 'serif':['CMU Classical Serif'], 'monospace':['CMU Typewriter Text']}
        #self.rcfont_kw = {'family':'serif', 'serif':['URW Palladio L Italic'], 'monospace':['CMU Typewriter Text']}
        self.rcparams_kw = {
          'axes.labelsize': 20,
          'text.fontsize': 14,
          'legend.fontsize': 18,
          'xtick.labelsize': 24,
          'ytick.labelsize': 24,
          'text.usetex': True,
          'axes.unicode_minus': True,
          #'legend.loc': 'best'
          'legend.loc': 'upper left',
          'figure.figsize': (12, 6)
          }

    def get_marker(self, idm):
        '''Get a specific marker type. This runs cyclically through the defined defaults.'''
        return self.markers[idm % len(self.markers)]

    def get_line(self, idm):
        '''Get a specific line type. This runs cyclically through the defined defaults.'''
        return self.lines[idm % len(self.lines)]

    def get_markercolor(self, idm):
        '''Get a specific marker color. This runs cyclically through the defined defaults.'''
        return self.markercolors[idm % len(self.markercolors)]

    def get_linecolor(self, idm):
        '''Get a specific line color. This runs cyclically through the defined defaults.'''
        return self.linecolors[idm % len(self.linecolors)]

    def get_pointsize(self, idm):
        '''Get a specific point size. This runs cyclically through the defined defaults.'''
        return self.pointsizes[idm % len(self.pointsizes)]

class Plot:

    def __init__(self, *fits, **kwargs):
        '''
        Constuctor for the Plot object. This constuctor accepts a series of `Fit` objects as positional
        arguments. Some keyword arguments can be provided to override the defaults. A list of these keyword
        arguments will be provided in the future...
        '''

        #: list of `Fit`s to plot
        self.fits = list(fits)          # store the child Fit objects in an instance variable

        #: plot style
        self.plot_style = PlotStyle()   # set the default style as the current plot style

        plt.rcParams.update(self.plot_style.rcparams_kw)
        plt.rc('font', **self.plot_style.rcfont_kw)

        self.plot_range = {'x': None, 'y': None}    #: plot range

        self.show_legend = kwargs.get('show_legend', True) #: whether to show the plot legend (``True``) or not (``False``)

        if len(fits)==1:
            #: axis labels
            self.axis_labels = map(label_to_latex, self.fits[0].dataset.axis_labels) # inherit axis labels from Fit's Dataset

            # set unit in brackets (if available)
            for label_id, _ in enumerate(self.axis_labels):
                unit = self.fits[0].dataset.axis_units[label_id]
                if unit != '':
                    self.axis_labels[label_id] += " [\\textrm{%s}]" % (unit,)
        else:
            self.axis_labels = ('$x$', '$y$') # set default axis names

        self.init_plots()               # initialize the plots

    def init_plots(self):
        '''
        Initialize the plots for each fit.
        '''

        self.figure = plt.figure()

        self.axes = self.figure.add_subplot(121)
        #self.axes = self.figure.add_axes([.07, .15, .6, .8])

        self.figure.subplots_adjust(wspace=.2,     # default .2
                            hspace=.2,     # default .2
                            top=.92,        # default .9
                            bottom=.12,    # default .1
                            left=.11,      # default .125
                            right=.8)     # default .9

        box = self.axes.get_position() 
        self.axes.set_position([box.x0, box.y0, box.width * 1.5, box.height])

        self.compute_plot_range()

    def plot_all(self, show_info_for='all', show_data_for='all'):
        '''
        Plot every `Fit` object to its figure.
        '''
        for p_id, _ in enumerate(self.fits):
            if show_data_for != 'all':
                try:
                    iter(show_data_for)
                except:
                    show_data_for=(show_data_for,) # wrap value in tuple

                if p_id in show_data_for:
                    self.plot(p_id, show_data=True)
                else:
                    self.plot(p_id, show_data=False)
            else:
                self.plot(p_id, show_data=True)

        if self.show_legend:
            self.draw_legend()

        self.draw_fit_parameters_box(show_info_for)

    def draw_legend(self):
        '''Draw the plot legend to the canvas'''
        # show plot legend
        self.legend = self.axes.legend(**self.plot_style.legendparams_kw)
        self.legend.draggable()

    def draw_fit_parameters_box(self, plot_spec=0):        
        '''Draw the parameter box to the canvas

        *plot_spec* : int, list of ints, string or None (optional, default: 0)
            Specify the plot id of the plot for which to draw the parameters. Passing 0 will only draw the
            parameter box for the first plot, and so on. Passing a list of ints will only draw the parameters
            for plot ids inside the list. Passing ``'all'`` will print parameters for all plots. Passing
            ``None`` will return immediately doing nothing.
        '''
        if plot_spec is None:
            return

        self.figure.canvas.draw()

        # get the offset to subtract for each axes transformation
        offset = self.axes.transAxes.transform((0,0))

        # get the legend bounding box and extract some dimension info
        legend_bbox = self.legend.legendPatch.get_bbox().inverse_transformed(self.axes.transAxes) 

        # size of the legend box. Use this to create the fit parameters text box below it.
        legend_size_px = self.axes.transAxes.transform((legend_bbox.width, legend_bbox.height)) - offset 
        legend_size = (legend_bbox.width, legend_bbox.height)

        # fit parameters box size
        textbox_size = (legend_size[0], legend_size[1] - 0.05)
        textbox_size_px = self.axes.transAxes.transform(textbox_size) - offset

        # pad text in fit parameters box by this amount
        pad_amount = self.plot_style.legendparams_kw['pad']
        pad_amount_px = (self.axes.transAxes.transform((self.plot_style.legendparams_kw['pad'],0)) - offset)[0]

        text_content = "\\textbf{Fit Parameters}\n" # allow localized text (German)?

        try:
            fit = self.fits[plot_spec]  # try to find the specified plot
        except:
            if plot_spec == "all":   # if not found, check for keyword 'all'
                fits_with_parameter_box = self.fits # go through all fits
            else:
                try:
                    fits_with_parameter_box = []
                    for p_id in plot_spec:
                        fits_with_parameter_box.append(self.fits[p_id])
                except:
                    raise Exception, "Cannot parse plot specification %r." % (plot_spec,)
        else:
            fits_with_parameter_box = [fit]

        for fit in fits_with_parameter_box:
            text_content += "~\n" + fit.function_label + ':\n'
            for idx, _ in enumerate(fit.parameter_names):
                parname = fit.latex_parameter_names[idx]
                parval = fit.get_parameter_values(rounding=True)[idx]
                parerrs = fit.get_parameter_errors(rounding=True)[idx]
                text_content += ('$%s=%g\pm%g$\n' % (parname, parval, parerrs))

        # replace scientific notation with power of ten
        text_content = re.sub(r'(-?\d*\.?\d+?)0*e\+?(-?[0-9]*[1-9]?)', r'\1\\times10^{\2}', text_content)

        self.textbox = self.axes.text(legend_bbox.xmin+pad_amount/2, 0.00+pad_amount/2,
                       text_content[:-1],
                       transform=self.axes.transAxes,
                       fontsize=self.plot_style.rcparams_kw['legend.fontsize'],
                       verticalalignment='bottom',
                       horizontalalignment='left',
                       bbox={'facecolor':'white',
                             'width':textbox_size_px[0],
                             #'height': textbox_size_px[1],
                             'pad': pad_amount_px}
                             #'pad': 22}
                       )

        self.figure.canvas.draw()

    def compute_plot_range(self, include_error_bars=True):
        '''
        Compute the span of all child datasets and sets the plot range to that
        '''

        self.plot_range = {'x': None, 'y': None}    # default plot range None (undefined)

        for current_fit in self.fits:
            xspan = current_fit.dataset.get_data_span('x', include_error_bars)  # initialize plot x span
            xspan = pad_span(xspan, G_PADDING_FACTOR_X)     # pad the x span by a pre-determined factor
            self.extend_span('x', xspan)

            yspan = current_fit.dataset.get_data_span('y', include_error_bars)  # initialize plot y span
            yspan = pad_span(yspan, G_PADDING_FACTOR_Y)     # pad the y span by a pre-determined factor
            self.extend_span('y', yspan)

    def extend_span(self, axis, new_span):
        '''
        Expand the span of the current plot.

        This method extends the current plot span to include `new_span`
        '''

        # make sure the axis specification is valid
        if axis not in ('x','y'):
            raise SyntaxError, "Unknown axis `%s'" % (axis,) 

        if self.plot_range[axis] is not None:
            self.plot_range[axis][0] = min(self.plot_range[axis][0], new_span[0]) # move the minimum down, if necessary
            self.plot_range[axis][1] = max(self.plot_range[axis][1], new_span[1]) # move the maximum up, if necessary
        else:
            self.plot_range[axis] = new_span  # if plot range in None (undefined), take the new values directly

    def plot(self, p_id, show_data=True):
        '''
        Plot the `Fit` object with the number `p_id` to its figure.
        '''

        current_fit    = self.fits[p_id]

        # set the current style
        # for the data points
        _pdata_kw = {'marker':self.plot_style.get_marker(p_id),
                     'linestyle':'None',
                     'markerfacecolor':self.plot_style.get_markercolor(p_id),
                     'markeredgecolor':self.plot_style.get_markercolor(p_id),
                     'color':self.plot_style.get_markercolor(p_id),
                     'label':current_fit.dataset.data_label,
                     'ms':self.plot_style.get_pointsize(p_id),
                     'capsize':0,
                     'zorder':1}

        # for the fit function 
        _fdata_kw = {'marker':'None',
                     'linestyle':self.plot_style.get_line(p_id),
                     'color':self.plot_style.get_linecolor(p_id),
                     'label':current_fit.function_label,
                     'zorder':2}

        # current error bar data defaults to None
        error_bar_data = {'x':None, 'y':None}

        # set current error bar data
        for axis in ('x', 'y'):
            # only set error bar data if errors are explicitly given,
            # either in form of a user-defined covariance matrix
            # or error lists
            if current_fit.dataset.has_errors(axis):
                error_bar_data[axis] = extract_statistical_errors(current_fit.dataset.get_cov_mat(axis)) # use the covmat's diagonal for the error bars

        # compute the function data
        ############################

        fxdata = np.linspace(self.plot_range['x'][0], self.plot_range['x'][1], G_PLOT_POINTS)                     # sample a fixed number of evenly-spaced points within the x span
        fydata = np.asarray(map(current_fit.get_current_fit_function(), fxdata))    # apply the current fit function to every point in fxdata => fydata

        # compute the confidence band around the function
        ##################################################

        confidence_band_data = np.zeros(G_PLOT_POINTS) # initialize conficence band data with zero

        # go through each data point and calculate the confidence interval
        for i, fval in enumerate(fxdata):            
            # calculate the outer product of the gradient of f (with respect to the parameters) with itself
            derivative_spacing = 0.01 * np.sqrt(min(np.diag(current_fit.get_error_matrix())))    # use 1/100th of the smallest parameter error as spacing for df/dp
            par_deriv_outer_prod = outer_product(current_fit.fit_function.derive_by_parameters(fval, derivative_spacing, current_fit.current_parameter_values))
            tmp_sum = np.sum(par_deriv_outer_prod * np.asarray(current_fit.get_error_matrix()))
            confidence_band_data[i] = np.sqrt(tmp_sum)

        # store upper and lower confidence bands

        lower_cb = fydata - confidence_band_data
        upper_cb = fydata + confidence_band_data

        # Do the actual plotting
        #########################

        # set some properties inherited from plot_style
        self.axes.grid(self.plot_style.grid)
        self.axes.set_xlabel(self.axis_labels[0], style=self.plot_style.axis_label_styles[0])
        self.axes.set_ylabel(self.axis_labels[1], style=self.plot_style.axis_label_styles[1])

        self.axes.xaxis.set_label_coords(*self.plot_style.axis_label_coords[0])
        self.axes.yaxis.set_label_coords(*self.plot_style.axis_label_coords[1])

        self.axes.tick_params(axis='x', pad=self.plot_style.axis_label_pad[0])
        self.axes.tick_params(axis='y', pad=self.plot_style.axis_label_pad[1])

        # plot data points, unless otherwise specified by the caller
        if show_data:
            pplot = self.axes.errorbar(current_fit.dataset.get_data('x'),
                                       current_fit.dataset.get_data('y'),
                                       yerr=error_bar_data['y'], 
                                       xerr=error_bar_data['x'], **_pdata_kw)

        # shade confidence band
        cband = self.axes.fill_between(fxdata, lower_cb, upper_cb, alpha='0.1', color=_fdata_kw['color'])

        # plot fit function
        fplot = self.axes.plot(fxdata, fydata, **_fdata_kw)

        # set the plot range
        self.axes.set_xlim(self.plot_range['x'])
        self.axes.set_ylim(self.plot_range['y'])

        # draw everything so positions are known
        plt.draw()

    def show(self):
        '''
        Show the `Plot` in a matplotlib interactive window.
        '''

        plt.show(self.axes)

    def save(self, output_file):
        '''
        Save the `Plot` to a file.
        '''

        plt.savefig(output_file)

if __name__ == '__main__':
    from dataset import Dataset, build_dataset
    from fit import Fit

    def linear_2par2(x, slope=1, x_offset=0):

        return slope * (x - x_offset)

    def exp_2par(x, damping=0.01, shift=6, y_intercept=0):

        return np.exp(damping * x + shift) + y_intercept - np.exp(shift)  

    myXData  = np.asarray([0., .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.])
    myYData  = np.asarray([0.227216,    -0.159875,    0.0924984,    -0.299377,    0.307159,    1.15718,    0.701532,    0.661879,    0.536548,    0.874998,    1.02603])
    myYData2 = np.asarray([-0.254749307136, -0.0983575484803, -0.108455145055, -0.317740870797, 0.112078239069, 0.238810848121, 0.285778651146, 0.498801157207, 0.220837168526, 0.587468379781, 0.517299353294])

    myXData  = np.linspace(0,100,40)

    def tmp(x):
        return exp_2par(x, 0.03, 6.5)

    tstFloat = .1
    myFits = []
    for slope in xrange(1,2):
        myYData  = np.asarray(map(lambda x: linear_2par2(x, slope, 0), myXData))
        myYData += np.random.normal(loc=0.0, scale=tstFloat, size=len(myYData)) 
        myDataset = build_dataset(xdata=myXData, 
                        ydata=myYData,
                        yrelstat=tstFloat)
        #myDataset.axis_labels=['\lambda', 'U']
        #myDataset.axis_units=['nm', 'V']
        myFits.append(Fit(myDataset, linear_2par2, function_label='Linear fit for example data'))
        myFits[-1].do_fit()

    myPlot = Plot(*myFits)

    myPlot.plot_all()
    myPlot.show()
