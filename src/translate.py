import math
import networkx as nx
from src import algorithms
from dreal.symbolic import Variable, logical_and


def translate_chip(dg, name, dim):
    """Create SMT expressions for bounding the nodes to be within constraints
    of the overall chip such as its area provided

    :param name: Name of the node to be constrained
    :returns: None -- no issues with translating the chip constraints
    """
    exprs = []
    exprs.append(algorithms.retrieve(dg, name, 'x') >= dim[0])
    exprs.append(algorithms.retrieve(dg, name, 'y') >= dim[1])
    exprs.append(algorithms.retrieve(dg, name, 'x') <= dim[2])
    exprs.append(algorithms.retrieve(dg, name, 'y') <= dim[3])
    return exprs


def translate_node(dg, name):
    """Create SMT expressions for bounding the parameters of an node
    to be within the constraints defined by the user

    :param name: Name of the node to be constrained
    :returns: None -- no issues with translating the port parameters to SMT
    """
    exprs = []
    # Pressure at a node is the sum of the pressures flowing into it
    output_pressures = []
    for node_name in dg.pred[name]:
        # This returns the nodes with channels that flowing into this node
        # pressure calculated based on P=QR
        # Could modify equation based on
        # https://www.dolomite-microfluidics.com/wp-content/uploads/
        # Droplet_Junction_Chip_characterisation_-_application_note.pdf
        output_pressures.append(algorithms.channel_output_pressure(dg, (node_name, name)))
    if len(dg.pred[name]) == 1:
        exprs.append(algorithms.retrieve(dg, name, 'pressure') == output_pressures[0])
    elif len(dg.pred[name]) > 1:
        output_pressure_formulas = [a + b for a, b in
                                    zip(output_pressures,
                                        output_pressures[1:])]
        exprs.append(algorithms.retrieve(dg, name, 'pressure') ==
                     logical_and(*output_pressure_formulas))

    if algorithms.retrieve(dg, name, 'min_x'):
        exprs.append(algorithms.retrieve(dg, name, 'x') ==
                     algorithms.retrieve(dg, name, 'min_x'))
    else:
        exprs.append(algorithms.retrieve(dg, name, 'x') >= 0)
    if algorithms.retrieve(dg, name, 'min_y'):
        exprs.append(algorithms.retrieve(dg, name, 'y') ==
                     algorithms.retrieve(dg, name, 'min_y'))
    else:
        exprs.append(algorithms.retrieve(dg, name, 'y') >= 0)
    # If parameters are provided by the user, then set the
    # their Variable equal to that value, otherwise make it greater than 0
    if algorithms.retrieve(dg, name, 'min_pressure'):
        # If min_pressure has a value then a user defined value was provided
        # and this variable is set equal to this value, else simply set its
        # value to be >0, same for viscosity, pressure, flow_rate, X, Y and density
        exprs.append(algorithms.retrieve(dg, name, 'pressure') ==
                     algorithms.retrieve(dg, name, 'min_pressure'))
    else:
        exprs.append(algorithms.retrieve(dg, name, 'pressure') > 0)
    if algorithms.retrieve(dg, name, 'min_flow_rate'):
        exprs.append(algorithms.retrieve(dg, name, 'flow_rate') ==
                     algorithms.retrieve(dg, name, 'min_flow_rate'))
    else:
        exprs.append(algorithms.retrieve(dg, name, 'flow_rate') > 0)
    if algorithms.retrieve(dg, name, 'min_viscosity'):
        exprs.append(algorithms.retrieve(dg, name, 'viscosity') ==
                     algorithms.retrieve(dg, name, 'min_viscosity'))
    else:
        exprs.append(algorithms.retrieve(dg, name, 'viscosity') > 0)

    if algorithms.retrieve(dg, name, 'min_density'):
        exprs.append(algorithms.retrieve(dg, name, 'density') ==
                     algorithms.retrieve(dg, name, 'min_density'))
    else:
        exprs.append(algorithms.retrieve(dg, name, 'density') > 0)

    densities = []
    for node_in in dg.pred[name]:
        densities.append(algorithms.retrieve(dg, node_in, 'density'))

    # If they are all equal, then set this node to be that density if there is a value
    # TODO: Create case for when different densities come in
    if densities and densities[1:] == densities[:-1]:
        exprs.append(algorithms.retrieve(dg, name, 'density') ==
                     algorithms.retrieve(dg, list(dg.pred[name].keys())[0], 'density'))
    # To recursively traverse, call on all successor channels
    for node_out in dg.succ[name]:
        [exprs.append(val) for val in translation_strats[
            algorithms.retrieve(dg, (name, node_out), 'kind')](dg, (name, node_out))]
    return exprs


def translate_input(dg, name):
    """Create SMT expressions for bounding the parameters of an input port
    to be within the constraints defined by the user

    :param name: Name of the port to be constrained
    :returns: None -- no issues with translating the port parameters to SMT
    """
    exprs = []
    if dg.size(name) <= 0:
        raise ValueError("Port %s must have 1 or more connections" % name)
    # Currently don't support this, and I don't think it would be the case
    # in real circuits, an input port is the beginning of the traversal
    if len(list(dg.predecessors(name))) != 0:
        raise ValueError("Cannot have channels into input port %s" % name)

    # If input is a type of node, call translate node
    [exprs.append(val) for val in translate_node(dg, name)]

    # Calculate flow rate for this port based on pressure and channels out
    # if not specified by user
    if not algorithms.retrieve(dg, name, 'min_flow_rate'):
        exprs.append(algorithms.calculate_port_flow_rate(dg, name))
    # TODO: Come up with a reasonable maximum pressure
    exprs.append((algorithms.retrieve(dg, name, 'flow_rate') < 100))

    # To recursively traverse, call on all successor channels
    #  for node_out in dg.succ[name]:
    #      [exprs.append(val) for val in translation_strats[
    #          algorithms.retrieve(dg, (name, node_out), 'kind')](dg, (name, node_out))]
    return exprs


def translate_output(dg, name):
    """Create SMT expressions for bounding the parameters of an output port
    to be within the constraints defined by the user

    :param str name: Name of the port to be constrained
    :returns: None -- no issues with translating the port parameters to SMT
    """
    exprs = []
    if dg.size(name) <= 0:
        raise ValueError("Port %s must have 1 or more connections" % name)
    # Currently don't support this, and I don't think it would be the case
    # in real circuits, an output port is considered the end of a branch
    if len(list(dg.succ[name])) != 0:
        raise ValueError("Cannot have channels out of output port %s" % name)

    # Since input is just a specialized node, call translate node
    [exprs.append(val) for val in translate_node(dg, name)]

    # Calculate flow rate for this port based on pressure and channels out
    # if not specified by user
    if not algorithms.retrieve(dg, name, 'min_flow_rate'):
        # The flow rate at this node is the sum of the flow rates of the
        # the channel coming in (I think, should be verified)
        total_flow_in = []
        for channel_in in dg.pred[name]:
            total_flow_in.append(dg.edges[(channel_in, name)]
                                 ['flow_rate'])
        if len(total_flow_in) == 1:
            exprs.append(algorithms.retrieve(dg, name, 'flow_rate') == total_flow_in[0])
        else:
            total_flow_in_formulas = [a + b for a, b in
                                      zip(total_flow_in, total_flow_in[1:])]
            exprs.append(algorithms.retrieve(dg, name, 'flow_rate') ==
                         logical_and(*total_flow_in_formulas))
    return exprs


# TODO: Refactor to use different formulas depending on the kind of the channel
def translate_channel(dg, name):
    """Create SMT expressions for a given channel (edges in NetworkX naming)
    currently only works for channels with a rectangular shape, but should
    be expanded to include circular and parabolic

    :param str name: The name of the channel to generate SMT equations for
    :returns: None -- no issues with translating channel parameters to SMT
    :raises: KeyError, if channel is not found in the list of defined edges
    """
    exprs = []
    try:
        dg.edges[name]
    except KeyError:
        raise KeyError('Channel with ports %s was not defined' % name)

    # Create expression to force length to equal distance between end nodes
    exprs.append(algorithms.pythagorean_length(dg, name))

    # Set the length determined by pythagorean theorem equal to the user
    # provided number if provided, else assert that the length be greater
    # than 0, same for width and height
    if algorithms.retrieve(dg, name, 'min_length'):
        exprs.append(algorithms.retrieve(dg, name, 'length') ==
                     algorithms.retrieve(dg, name, 'min_length'))
    else:
        exprs.append(algorithms.retrieve(dg, name, 'length') > 0)

    if algorithms.retrieve(dg, name, 'min_width'):
        exprs.append(algorithms.retrieve(dg, name, 'width') ==
                     algorithms.retrieve(dg, name, 'min_width'))
    else:
        exprs.append(algorithms.retrieve(dg, name, 'width') > 0)
    if algorithms.retrieve(dg, name, 'min_resolution'):
        exprs.append(algorithms.retrieve(dg, name, 'width') <
                     algorithms.retrieve(dg, name, 'min_resolution'))
    else:
        # Set default to be less than 0.0001m
        exprs.append(algorithms.retrieve(dg, name, 'width') < 1)

    if algorithms.retrieve(dg, name, 'min_height'):
        exprs.append(algorithms.retrieve(dg, name, 'height') ==
                     algorithms.retrieve(dg, name, 'min_height'))
    else:
        # Set default to be greater than 1um
        exprs.append(algorithms.retrieve(dg, name, 'height') > 0.000001)
    if algorithms.retrieve(dg, name, 'min_depth'):
        exprs.append(algorithms.retrieve(dg, name, 'height') <
                     algorithms.retrieve(dg, name, 'min_depth'))
    else:
        # Set default to be less than 0.001m
        exprs.append(algorithms.retrieve(dg, name, 'height') < 0.001)

    # Assert that viscosity in channel equals input node viscosity
    # Set output viscosity to equal input since this should be constant
    # This must be performed before calculating resistance
    exprs.append(algorithms.retrieve(dg, name, 'viscosity') ==
                 algorithms.retrieve(dg, algorithms.retrieve(dg, name, 'port_from'), 'viscosity'))
    exprs.append(algorithms.retrieve(dg, algorithms.retrieve(dg, name, 'port_to'), 'viscosity') ==
                 algorithms.retrieve(dg, algorithms.retrieve(dg, name, 'port_from'), 'viscosity'))

    # Pressure at end of channel is lower based on the resistance of
    # the channel as calculated by calculate_channel_resistance and
    # pressure_out = pressure_in * (flow_rate * resistance)
    resistance_list = algorithms.calculate_channel_resistance(dg, name)

    # First term is assertion that each channel's height is less than width
    # which is needed to make resistance formula valid, second is the SMT
    # equation for the resistance, then assert resistance is >0
    exprs.append(resistance_list[0])
    resistance = resistance_list[1]
    exprs.append(algorithms.retrieve(dg, name, 'resistance') == resistance)
    exprs.append(algorithms.retrieve(dg, name, 'resistance') > 0)

    # Assert flow rate equal to the flow rate coming in
    exprs.append(algorithms.retrieve(dg, name, 'flow_rate') ==
                 algorithms.retrieve(dg, algorithms.retrieve(dg, name, 'port_from'), 'flow_rate'))

    # Channels do not have pressure because it decreases across channel
    # Call translate on the output to continue traversing the channel
    [exprs.append(val) for val in translation_strats[algorithms.retrieve(dg,
        algorithms.retrieve(dg, name, 'port_to'), 'kind')]\
        (dg, algorithms.retrieve(dg, name, 'port_to'))]
    return exprs


def translate_tjunc(dg, name, crit_crossing_angle=0.5):
    """Create SMT expressions for a t-junction node that generates droplets
    Must have 2 input channels (continuous and dispersed phases) and one
    output channel where the droplets leave the node. Continuous is usually
    oil and dispersed is usually water

    :param str name: The name of the channel to generate SMT equations for
    :param crit_crossing_angle: The angle of the dispersed channel to
        the continuous must be great than this to have droplet generation
    :returns: None -- no issues with translating channel parameters to SMT
    :raises: KeyError, if channel is not found in the list of defined edges
    """
    exprs = []
    # Validate input
    if dg.size(name) != 3:
        raise ValueError("T-junction %s must have 3 connections" % name)

    # Since T-junction is just a specialized node, call translate node
    translate_node(dg, name)

    # Renaming for consistency with the other nodes
    junction_node_name = name
    # Since there should only be one output node, this can be found first
    # from the dict of successors
    try:
        output_node_name = list(dict(dg.succ[name]).keys())[0]
        output_channel_name = (junction_node_name, output_node_name)
    except KeyError as e:
        raise KeyError("T-junction must have only one output")
    # these will be found later from iterating through the dict of
    # predecessor nodes to the junction node
    continuous_node_name = ''
    continuous_channel_name = ''
    dispersed_node_name = ''
    dispersed_channel_name = ''

    # NetworkX allows for the creation of dicts that contain all of
    # the edges containing a certain attribute, in this case phase is
    # of interest
    phases = nx.get_edge_attributes(dg, 'phase')
    for pred_node, phase in phases.items():
        if phase == 'continuous':
            continuous_node_name = pred_node[0]
            continuous_channel_name = (continuous_node_name, junction_node_name)
            # assert width and height to be equal to output
            exprs.append(algorithms.retrieve(dg, continuous_channel_name, 'width') ==
                         algorithms.retrieve(dg, output_channel_name, 'width'))
            exprs.append(algorithms.retrieve(dg, continuous_channel_name, 'height') ==
                         algorithms.retrieve(dg, output_channel_name, 'height'))
        elif phase == 'dispersed':
            dispersed_node_name = pred_node[0]
            dispersed_channel_name = (dispersed_node_name, junction_node_name)
            # Assert that only the height of channel be equal
            exprs.append(algorithms.retrieve(dg, dispersed_channel_name, 'height') ==
                         algorithms.retrieve(dg, output_channel_name, 'height'))
        elif phase == 'output':
            continue
        else:
            raise ValueError("Invalid phase for T-junction: %s" % name)

    # Epsilon, sharpness of T-junc, must be greater than 0
    epsilon = Variable('epsilon')
    exprs.append(epsilon >= 0)

    # TODO: Figure out why original had this cause it doesn't seem true
    #  # Pressure at each of the 4 nodes must be equal
    #  exprs.append(Equals(junction_node['pressure'],
    #                           continuous_node['pressure']
    #                           ))
    #  exprs.append(Equals(junction_node['pressure'],
    #                           dispersed_node['pressure']
    #                           ))
    #  exprs.append(Equals(junction_node['pressure'],
    #                           output_node['pressure']
    #                           ))

    # Viscosity in continous phase equals viscosity at output
    exprs.append(algorithms.retrieve(dg, continuous_node_name, 'viscosity') ==
                 algorithms.retrieve(dg, output_node_name, 'viscosity'))

    # Flow rate into the t-junction equals the flow rate out
    exprs.append(algorithms.retrieve(dg, continuous_channel_name, 'flow_rate') +
                 algorithms.retrieve(dg, dispersed_channel_name, 'flow_rate') ==
                 algorithms.retrieve(dg, output_channel_name, 'flow_rate'))

    # Assert that continuous and output channels are in a straight line
    exprs.append(algorithms.channels_in_straight_line(dg,
                                                      continuous_node_name,
                                                      junction_node_name,
                                                      output_node_name
                                                      ))

    # Droplet volume in channel equals calculated droplet volume
    # TODO: Manifold also has a table of constraints in the Schematic and
    # sets ChannelDropletVolume equal to dropletVolumeConstraint, however
    # the constraint is void (new instance of RealTypeValue) and I think
    # could conflict with calculated value, so ignoring it for now but
    # may be necessary to add at a later point if I'm misunderstand why
    # its needed
    exprs.append(algorithms.retrieve(dg, output_channel_name, 'droplet_volume') ==
                 algorithms.calculate_droplet_volume(
                     dg,
                     algorithms.retrieve(dg, output_channel_name, 'height'),
                     algorithms.retrieve(dg, output_channel_name, 'width'),
                     algorithms.retrieve(dg, dispersed_channel_name, 'width'),
                     epsilon,
                     algorithms.retrieve(dg, dispersed_node_name, 'flow_rate'),
                     algorithms.retrieve(dg, continuous_node_name, 'flow_rate')
                     ))

    # Assert critical angle is <= calculated angle
    cosine_squared_theta_crit = math.cos(math.radians(crit_crossing_angle))**2
    # Continuous to dispersed
    exprs.append(cosine_squared_theta_crit <=
                 algorithms.cosine_law_crit_angle(dg,
                                                  continuous_node_name,
                                                  junction_node_name,
                                                  dispersed_node_name
                                                  ))
    # Continuous to output
    exprs.append(cosine_squared_theta_crit <=
                 algorithms.cosine_law_crit_angle(dg,
                                                  continuous_node_name,
                                                  junction_node_name,
                                                  output_node_name
                                                  ))
    # Output to dispersed
    exprs.append(cosine_squared_theta_crit <=
                 algorithms.cosine_law_crit_angle(dg,
                                                  output_node_name,
                                                  junction_node_name,
                                                  dispersed_node_name
                                                  ))
    # Call translate on output
    [exprs.append(val) for val in translation_strats[algorithms.retrieve(dg,
                                                                         output_node_name,
                                                                         'kind'
                                                                         )](dg, output_node_name)]
    return exprs



def translate_ep_cross(dg, name, fluid_name = 'default'):
    """Create SMT expressions for an electrophoretic cross

    :param str name: the name of the junction node in the electrophoretic cross
    :returns: None -- no issues with translating channel parameters to SMT
    :raises:
    """

    # work in progress
    # comments will be cleaned up once code is working
    exprs = []

	# Validate input
    if dg.size(name) != 4:
        raise ValueError("Electrophoretic Cross %s must have 4 connections" % name)

	# Electrophoretic Cross is a type of node, so call translate node
    translate_node(dg, name)


	# Notes:
	# anode to cathode is electrophoretic (molecules)
	# 	and electroosmotic flow (bulk), not pressure driven
    # user needs to specify which channel is for separation
        # assume the other input channel is for injection?


	# Possible things that need to have constraints/equations:
	# assert anode to cathode is straight?
	# assert that input node to waste node is straight?
	#	possibly it doesn't have to be
	# viscosity
	# flow rate
    # x_detector < channel length
    # concentration peaks are disinguishable
    # each delta t (tmax -  tmin) is > min detector sampling time


	# Because it's done in translate_tjunc
    ep_cross_node_name = name

	# figure out which nodes are for sample injection and which are for separation channel
	# assume single input node, 3 output nodes, one junction node
    # assume separation channel is specified by user

    # is the direction of the graph same as fluid flow?
    # are the cathode and anode both output nodes?
    phases = nx.get_edge_attributes(dg, 'phase')
    for edge, phase in phases.iteritems():
        # assuming only one separation channel, and only 1 tail channel
        if phase == 'separation':
            separation_channel_name = edge
            anode_node_name = edge[1]
        elif phase == 'tail':
            tail_channel_name = edge
            cathode_node_name = edge[ edge[0] == ep_cross_node_name ]  # returns whichever tuple element is NOT the ep_cross node

    # is there a better way to do this?
    node_kinds = nx.get_node_attributes(dg, 'kind')
    for node, kind in node_kinds.iteritems():
        if node not in separation_channel_name and node not in tail_channel_name:
            if kind == 'input':
                injection_channel_name = (node, ep_cross_node_name)
                injection_node_name = node  # necessary?
            elif kind == 'output':
                waste_channel_name = (ep_cross_node_name, node)
                waste_node_name = node  # necessary?


    # assert dimensions:
    # assert width and height of tail channel to be equal to separation channel
    exprs.append(algorithms.retrieve(dg, tail_channel_name, 'width') ==
                algorithms.retrieve(dg, separation_channel_name, 'width'))
    exprs.append(algorithms.retrieve(dg, tail_channel_name, 'height') ==
                algorithms.retrieve(dg, separation_channel_name, 'height'))

    # assert width and height of injection channel to be equal to waste channel
    exprs.append(algorithms.retrieve(dg, injection_channel_name, 'width') ==
                algorithms.retrieve(dg, waste_channel_name, 'width'))
    exprs.append(algorithms.retrieve(dg, injection_channel_name, 'height') ==
                algorithms.retrieve(dg, waste_channel_name, 'height'))

    # assert height of separation channel and injection channel are same
    exprs.append(algorithms.retrieve(dg, injection_channel_name, 'height') ==
                 algorithms.retrieve(dg, separation_channel_name, 'height'))


    # Assert that tail and separation channels are in a straight line?  nah

    # electric field
    E = Variable('E')
    exprs.append(E == algorithms.calculate_electric_field(dg, anode_node_name, cathode_node_name))

    # do I need a variable for each analyte? yes
    # number of analytes unknown - is it possible to make a list of variables? types

    # parameters that maybe should not be hardcoded, but are hardcoded for now:
    # pass these as arguments into the translate_ep_cross function instead?
    p = 0.5
    q = 0.9
    c = 0.4

    # assume that the analyte parameters were included in the injection port
    # need to validate that the data exists?
    D = algorithms.retrieve(dg, injection_node_name, 'analyte_diffusivities')
    C0 = algorithms.retrieve(dg, injection_node_name, 'analyte_initial_concentrations')
    q = algorithms.retrieve(dg, injection_node_name, 'analyte_charges')
    r = algorithms.retrieve(dg, injection_node_name, 'analyte_radii')
    delta = algorithms.retrieve(dg, separation_channel_name, 'min_sampling_rate')
    x_detector = algorithms.retrieve(dg, separation_channel_name, 'x_detector')

    n = len(D)
    mu = []
    v = []
    t_peak = []
    t_min = []
    C = []
    W =  algorithms.retrieve(dg, injection_channel_name, 'width')

    C_negligible = Variable('C_negligible')

    # for each analyte
    for i in range(0, n):
        # calculate mobility
        mu.append( Variable('mu_' + str(i)) )
        exprs.append( mu[i] == algorithms.calculate_mobility(dg, separation_channel_name, q[i], r[i]) )

        # calculate velocity
        v.append( Variable('v_' + str(i)) )
        exprs.append( v[i] == algorithms.calculate_charged_particle_velocity( mu[i], E) )

        # calculate t_peak, initialize variables for t_min
        t_peak.append( Variable('t_peak_' + str(i)) )
        t_min.append( Variable('t_min_' + str(i)) )
        exprs.append( t_peak[i] == x_detector/v[i] )

diff = []
    for i in range(0, n-1):

        # constrain that time difference between peaks is large enough to be detected
        exprs.append(t_peak[i] + delta < t_min[i])
        exprs.append(t_peak[i] + delta < t_min[i+1])

        # constrain t_min to be where derivative of concentration is 0
        # if two adjacent peaks are close enough in height, then can approximate Fi(tmin) = Fi+1(tmin)
        # quantify closeness of heights of peaks using the variable diff
        diff.append( Variable('diff_' + str(i)) )
        exprs.append( diff[i] == C0[i]/C0[i+1] * math.sqrt(D[i+1]*mu[i]/(D[i]*mu[i+1])) )

        # UNFINISHED:
            # expression for C_negligible
            # if/else for F(tmin)
            # actually try running it

        # F(tmin, i)/(F(tmax, i)) <= c
        exprs.append(
            (algorithms.calculate_concentration(dg, C0[i], D[i], W, v[i], x_detector, t_min[i]) +
             algorithms.calculate_concentration(dg, C0[i+1], D[i+1], W, v[i+1], x_detector, t_min[i]) +
             (n-2)*(1-q)/(n-3) * C_negligible)
             / (algorithms.calculate_concentration(dg, C0[i], D[i], W, v[i], x_detector, t_peak[i]))
             <= c
         )

        # F(tmin, i)/(F(tmax, i+1)) <= c
        exprs.append(
            (algorithms.calculate_concentration(dg, C0[i], D[i], W, v[i], x_detector, t_min[i]) +
             algorithms.calculate_concentration(dg, C0[i+1], D[i+1], W, v[i+1], x_detector, t_min[i]) +
             (n-2)*(1-q)/(n-3) * C_negligible)
             / (algorithms.calculate_concentration(dg, C0[i+1], D[i+1], W, v[i+1], x_detector, t_peak[i+1]))
             <= c
            )

    # add list parameter
    # retrieve will get list
    # for loop to handle each  variable

    # detector position is somewhere along the separation channel
    # assume x_detector ranges from 0 to length of channel
    # to get absolute position of detector, add x_detector to ep_cross_node position
    exprs.append( x_detector <= algorithms.retrieve(dg, separation_channel_name, 'length') )

    # C_negligible is the minimum concentration level
    # i.e. smallest concentration peak should be > C_negligible
    C_floor = variable('C_floor')
    C_negligible = variable('C_negligible')
    # p is a constant between 0 and 1; hard-coded for now

    exprs.append( C_floor == ( min(C0) / (sigma0 + math.sqrt(2*max(D) * x_detector / v_n)) ) )
    exprs.append( C_negligible ==  p * C_floor )



    return exprs


translation_strats = {'input': translate_input,
                      'output': translate_output,
                      'node': translate_node,
                      'channel': translate_channel,
                      'tjunc': translate_tjunc,
                      'rectangle': translate_channel,
                      'ep_cross': translate_ep_cross
                      }
