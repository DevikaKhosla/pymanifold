from pprint import pprint
import math
import networkx as nx
import matplotlib.pyplot as plt  # just for testing to show graph, may not keep
from pysmt.shortcuts import Symbol, Plus, Times, Div, Pow, Equals, Real
from pysmt.shortcuts import Minus, GE, GT, LE, LT, And, get_model, is_sat
from pysmt.typing import REAL
from pysmt.logics import QF_NRA


class Schematic():
    """Create new schematic which contains all of the connections and ports
    within a microfluidic circuit to be solved for my an SMT solver to
    determine solvability of the circuit and the range of the parameters where
    it is still solvable
    """
    # TODO schematic to JSON method following Manifold IR syntax

    def __init__(self, dim=[0, 0, 10, 10]):
        """Store the connections as a dictionary to form a graph where each
        value is a list of all nodes/ports that a node flows out to, store
        information about each of the channels in a separate dictionary
        dim - dimensions of the chip, [X_min, Y_min, X_max, X_min]
        """
        self.exprs = []
        self.dim = dim

        # Add new node types and their validation method to this dict
        # to maintain consistent checking across all methods
        self.translation_strats = {'input': self.translate_input,
                                   'output': self.translate_output,
                                   't-junction': self.translate_tjunc,
                                   'rectangle': self.translate_channel
                                   }

        # DiGraph that will contain all nodes and channels
        self.dg = nx.DiGraph()

    # TODO: All parameters for channel and ports need to have units documented
    #       depending on the formula
    def channel(self,
                port_from,
                port_to,
                min_length=-1,
                min_width=-1,
                min_height=-1,
                min_channel_length=-1,
                shape='rectangle',
                phase='None'):
        """Create new connection between two nodes/ports with attributes
        consisting of the dimensions of the channel to be used to create the
        SMT2 equation to calculate solvability of the circuit

        min_length - constaint the chanell to be at least this long
        width - width of the cross section of the channel
        height - height of the cross section of the channel
        port_from - port where fluid comes into the channel from
        port_to - port at the end of the channel where fluid exits
        shape - shape of cross section of the channel
        phase - for channels connecting to a T-junction this must be either
                continuous, dispersed or output
        """
        valid_shapes = ("rectangle")
        # Checking that arguments are valid
        if shape not in valid_shapes:
            raise ValueError("Valid channel shapes are: %s"
                             % valid_shapes)
        if port_from not in self.dg.nodes:
            raise ValueError("port_from node doesn't exist")
        elif port_to not in self.dg.nodes():
            raise ValueError("port_to node doesn't exist")

        # Add the information about that connection to another dict
        # There's extra parameters in here than in the arguments because they
        # are values calculated by later methods when creating the SMT eqns
        attributes = {'shape': shape,
                      'length': Symbol('_'.join([port_from, port_to, 'length']),
                                       REAL),
                      'min_length': min_length,
                      'width': Symbol('_'.join([port_from, port_to, 'width']),
                                      REAL),
                      'min_width': min_width,
                      'height': Symbol('_'.join([port_from, port_to, 'height']),
                                       REAL),
                      'min_height': min_height,
                      'flow_rate': Symbol('_'.join([port_from, port_to, 'flow_rate']),
                                          REAL),
                      'droplet_volume': Symbol('_'.join([port_from, port_to, 'Dvol']),
                                               REAL),
                      'viscosity': Symbol('_'.join([port_from, port_to, 'viscosity']),
                                          REAL),
                      'resistance': Symbol('_'.join([port_from, port_to, 'res']),
                                           REAL),
                      'phase': phase.lower(),
                      }

        # list of values that should all be positive numbers
        not_neg = ['min_length', 'min_width', 'min_height']
        for param in not_neg:
            try:
                if attributes[param] < -1:
                    raise ValueError("channel '%s' parameter '%s' must be >= 0"
                                     % (param))
            except TypeError as e:
                raise TypeError("channel %s parameter must be int" % param)
            except ValueError as e:
                raise ValueError(e)

        # Can't have two of the same channel
        if (port_from, port_to) in self.dg.edges:
            raise ValueError("Channel already exists between these nodes")
        # Create this edge in the graph
        self.dg.add_edge(port_from, port_to)

        for key, attr in attributes.items():
            # Store as False instead of 0 to prevent any further
            # operations from accepting this value by mistake
            if attr == 0:
                self.dg.edges[port_from, port_to][key] = False
            else:
                self.dg.edges[port_from, port_to][key] = attr
        return

    # TODO: Add ability to specify a fluid type in the node (ie. water) and
    #       have this method automatically fill in the parameters for water
    # TODO: Should X and Y be forced to be >0 for triangle area calc?
    # TODO: There are similar arguments for both port and node that could be
    #       simplified if they were inhereted from a common object
    def port(self, name, kind, min_pressure=-1, min_flow_rate=-1, x=-1, y=-1,
             density=1, min_viscosity=-1):
        """Create new port where fluids can enter or exit the circuit, any
        optional tag left empty will be converted to a variable for the SMT
        solver to solve for a give a value
        :param str name: The name of the port to use when defining channels
        :param str kind: Define if this is an 'input' or 'output' port
        :param float Density: Density of fluid in g/cm^3, default is 1(water)
        :param float min_viscosity: Viscosity of the fluid, units are Pa.s
        :param float min_pressure: Pressure of the input fluid, units are Pa
        :param float min_flow_rate - flow rate of input fluid, units are m^3/s
                                     (may want to make it smaller, um^3/s)
        :param float X: x-position of port on chip schematic
        :param float Y: y-position of port on chip schematic
        """
        # Checking that arguments are valid
        if not isinstance(name, str) or not isinstance(kind, str):
            raise TypeError("name and kind must be strings")
        if name in self.dg.nodes:
            raise ValueError("Must provide a unique name")
        if kind.lower() not in self.translation_strats.keys():
            raise ValueError("kind must be %s" % self.translation_strats.keys())

        # Ports are stored with nodes because ports are just a specific type of
        # node that has a constant flow rate
        # only accept ports of the right kind (input or output)
        attributes = {'kind': kind.lower(),
                      'viscosity': Symbol(name+'_viscosity', REAL),
                      'min_viscosity': min_viscosity,
                      'pressure': Symbol(name+'_pressure', REAL),
                      'min_pressure': min_pressure,
                      'flow_rate': Symbol(name+'_flow_rate', REAL),
                      'min_flow_rate': min_flow_rate,
                      'density': Symbol(name+'_density', REAL),
                      'min_density': density,
                      'x': Symbol(name+'_X', REAL),
                      'y': Symbol(name+'_Y', REAL),
                      'min_x': x,
                      'min_y': y
                      }

        # list of values that should all be positive numbers
        not_neg = ['min_x', 'min_y', 'min_pressure', 'min_flow_rate',
                   'min_viscosity', 'min_density']
        for param in not_neg:
            try:
                if attributes[param] < -1:
                    raise ValueError("port '%s' parameter '%s' must be >= 0" %
                                     (name, param))
            except TypeError as e:
                raise TypeError("port '%s' parameter '%s' must be int" %
                                (name, param))
            except ValueError as e:
                raise ValueError(e)

        # Create this node in the graph
        self.dg.add_node(name)
        for key, attr in attributes.items():
            if attr == -1:
                # Store as False instead of 0 to prevent any further
                # operations from accepting this value by mistake
                self.dg.nodes[name][key] = False
            else:
                self.dg.nodes[name][key] = attr

    def node(self, name, x=-1, y=-1, kind='node'):
        """Create new node where fluids merge or split, kind of node
        (T-junction, Y-junction, cross, etc.) can be specified
        if not then a basical node connecting multiple channels will be created
        """
        # Checking that arguments are valid
        if not isinstance(name, str) or not isinstance(kind, str):
            raise TypeError("name and kind must be strings")
        if name in self.dg.nodes:
            raise ValueError("Must provide a unique name")
        if kind.lower() not in self.translation_strats.keys():
            raise ValueError("kind must be %s" % self.translation_strats.keys())

        # Ports are stored with nodes because ports are just a specific type of
        # node that has a constant flow rate
        # only accept ports of the right kind (input or output)
        attributes = {'kind': kind.lower(),
                      'pressure': Symbol(name+'_pressure', REAL),
                      'flow_rate': Symbol(name+'_flow_rate', REAL),
                      'viscosity': Symbol(name+'_viscosity', REAL),
                      'density': Symbol(name+'_density', REAL),
                      'x': Symbol(name+'_X', REAL),
                      'y': Symbol(name+'_Y', REAL),
                      'min_x': x,
                      'min_y': y
                      }

        # list of values that should all be positive numbers
        not_neg = ['min_x', 'min_y']
        for param in not_neg:
            try:
                if attributes[param] < -1:
                    raise ValueError("port '%s' parameter '%s' must be >= 0" %
                                     (name, param))
            except TypeError as e:
                raise TypeError("Port '%s' parameter '%s' must be int" %
                                (name, param))
            except ValueError as e:
                raise ValueError(e)

        # Create this node in the graph
        self.dg.add_node(name)
        for key, attr in attributes.items():
            if attr == -1:
                # Store as False instead of 0 to prevent any further
                # operations from accepting this value by mistake
                self.dg.nodes[name][key] = False
            else:
                self.dg.nodes[name][key] = attr

    def translate_chip(self, name):
        """Create SMT2 expressions for bounding the chip area provided when
        initializing the schematic object
        """
        named_node = self.dg.nodes[name]
        self.exprs.append(GE(named_node['x'], Real(self.dim[0])))
        self.exprs.append(GE(named_node['y'], Real(self.dim[1])))
        self.exprs.append(LE(named_node['x'], Real(self.dim[2])))
        self.exprs.append(LE(named_node['y'], Real(self.dim[3])))

    def translate_input(self, name):
        """Generate equations to simulate a fluid input port
        """
        if len(list(self.dg.neighbors(name))) <= 0:
            raise ValueError("Port %s must have 1 or more connections" % name)

        # Since input is just a specialized node, call translate node
        self.translate_node(name)

        named_node = self.dg.nodes[name]
        # If parameters are provided by the user, then set the
        # their Symbol equal to that value, otherwise make it greater than 0
        if named_node['min_pressure']:
            # named_node['pressure'] returns variable for node for pressure
            # where 'min_pressure' returns the user defined value if provided,
            # else its 0, same is true for viscosity and x and y position
            self.exprs.append(Equals(named_node['pressure'],
                                     Real(named_node['min_pressure'])
                                     ))
        else:
            self.exprs.append(GE(named_node['pressure'], Real(0)))
        if named_node['min_flow_rate']:
            self.exprs.append(Equals(named_node['flow_rate'],
                                     Real(named_node['min_flow_rate'])
                                     ))
        else:
            self.exprs.append(GE(named_node['flow_rate'], Real(0)))
        if named_node['min_viscosity']:
            self.exprs.append(Equals(named_node['viscosity'],
                                     Real(named_node['min_viscosity'])
                                     ))
        else:
            self.exprs.append(GE(named_node['viscosity'], Real(0)))
        if named_node['density']:
            self.exprs.append(Equals(named_node['density'],
                                     Real(named_node['min_density'])
                                     ))
        else:
            self.exprs.append(GE(named_node['density'], Real(0)))

    # TODO: Find out how output and input need to be different, currently they
    #       are exactly the same, perhaps change how translation happens to
    #       have it traverse the graph, starting at inputs and calling
    #       channel and output translation methods recursively
    def translate_output(self, name):
        """Generate equations to simulate a fluid output port
        """
        if self.dg.size(name) <= 0:
            raise ValueError("Port %s must have 1 or more connections" % name)

        # Since input is just a specialized node, call translate node
        self.translate_node(name)

        named_node = self.dg.nodes[name]
        # If parameters are provided by the user, then set the
        # their Symbol equal to that value, otherwise make it greater than 0
        if named_node['min_pressure']:
            # named_node['pressure'] returns variable for node for pressure
            # where 'min_pressure' returns the user defined value if provided,
            # else its 0, same is true for viscosity and position (position_sym
            # provides the symbol in this case)
            self.exprs.append(Equals(named_node['pressure'],
                                     Real(named_node['min_pressure'])
                                     ))
        else:
            self.exprs.append(GE(named_node['pressure'], Real(0)))
        if named_node['min_flow_rate']:
            self.exprs.append(Equals(named_node['flow_rate'],
                                     Real(named_node['min_flow_rate'])
                                     ))
        else:
            self.exprs.append(GE(named_node['flow_rate'], Real(0)))
        if named_node['min_viscosity']:
            self.exprs.append(Equals(named_node['viscosity'],
                                     Real(named_node['min_viscosity'])
                                     ))
        else:
            self.exprs.append(GE(named_node['viscosity'], Real(0)))
        if named_node['density']:
            self.exprs.append(Equals(named_node['density'],
                                     Real(named_node['min_density'])
                                     ))
        else:
            self.exprs.append(GE(named_node['density'], Real(0)))

    # TODO: Refactor this to be just translate_channel and have it use the
    #       correct formula depending on the shape of the given channel
    #       Also some port parameters are calcualted here like flow rate which
    #       could be confusing to debug since one would look for port parameter
    #       issues in translate input or output, not here, making these
    #       method be called only when traversing the graph would rectify this
    def translate_channel(self, name):
        """Create SMT2 expressions for a given channel (edges in networkx naming)
        currently only works for channels with a rectangular shape, but should
        be expanded to include circular and parabolic
        name - the name of the channel to have SMT equations created for
        """
        try:
            named_channel = self.dg.edges[name]
        except KeyError:
            raise KeyError('Channel %s does not exist' % name)
        port_in_name = name[0]
        port_out_name = name[1]
        port_in = self.dg.nodes[port_in_name]
        port_out = self.dg.nodes[port_out_name]

        # Use pythagorean theorem to assert that the channel be greater than
        # the min_channel_length if no value is provided, or set the length
        # equal to the user provided number
        if named_channel['min_length']:
            self.exprs.append(GT(named_channel['length'],
                              Real(named_channel['min_length'])))
        else:
            # If values isn't provided assert that length must be greater than
            # than 0
            self.exprs.append(GT(named_channel['length'], Real(0)))

        # Create expression to force length to equal distance between end nodes
        self.exprs.append(self.pythagorean_length(name))

        # Assert that viscosity in channel equals input node viscosity
        # set output viscosity to equal input since this should be constant
        # This must be performed before calculating resistance
        self.exprs.append(Equals(named_channel['viscosity'],
                                 port_in['viscosity']))
        self.exprs.append(Equals(port_out['viscosity'],
                                 port_in['viscosity']))

        # Assert channel width, height viscosity and resistance greater
        # than 0
        self.exprs.append(GE(named_channel['width'], Real(0)))
        self.exprs.append(GE(named_channel['height'], Real(0)))

        # Assert pressure at end of channel is lower based on the resistance of
        # the channel as calculated by calculate_channel_resistance and
        # delta(P) = flow_rate * resistance
        # pressure_out = pressure_in - delta(P)
        resistance_list = self.calculate_channel_resistance(name)

        # First term is assertion that each channel's height is less than width
        # which is needed to make resistance formula valid, second is the SMT
        # equation of the resistance
        self.exprs.append(resistance_list[0])

        # Assert resistance to equal value calculated for rectangular channel
        resistance = resistance_list[1]
        self.exprs.append(Equals(named_channel['resistance'], resistance))
        self.exprs.append(GE(named_channel['resistance'], Real(0)))
        named_channel['resistance'] = resistance

        # Assert flow rate equal to calcuated value, in channel and ports
        flow_rate = self.calculate_port_flow_rate(port_in_name)
        self.exprs.append(Equals(named_channel['flow_rate'], flow_rate))
        self.exprs.append(Equals(port_in['flow_rate'],
                                 flow_rate))
        self.exprs.append(Equals(port_out['flow_rate'],
                                 flow_rate))

        # Assert pressure in output to equal calcualted value based on P=QR
        output_pressure = self.channel_output_pressure(name)
        self.exprs.append(Equals(port_out['pressure'],
                                 output_pressure))
        self.exprs.append(GE(port_out['pressure'],
                             Real(0)))
        port_out['pressure'] = output_pressure
        return

    # TODO: assert node position here and for ports
    # TODO: need way for sum of flow_in to equal flow out for input and output
    #       ports
    def translate_node(self, name):
        """Generate equations to simulate a basic node connecting two or more
        channels
        """
        # Flow rate in and out of the node must be equal
        # Assume flow rate is the same at the start and end of a channel
        named_node = self.dg.nodes[name]
        # Position x and y symbols must equal their assigned value, if not
        # assigned then set to be greater than 0
        if named_node['min_x']:
            self.exprs.append(Equals(named_node['x'], Real(named_node['min_x'])))
            self.exprs.append(Equals(named_node['y'], Real(named_node['min_y'])))
        else:
            self.exprs.append(GE(named_node['x'], Real(0)))
            self.exprs.append(GE(named_node['y'], Real(0)))
        return

    # TODO: Migrate this to work with NetworkX
    # TODO: Refactor some of these calculations so they can be reused by other
    #       translation methods
    def translate_tjunc(self, name, critCrossingAngle=0.5):
        # Validate input
        if self.dg.size(name) != 3:
            raise ValueError("T-junction %s must have 3 connections" % name)

        # Since T-junction is just a specialized node, call translate node
        self.translate_node(name)

        junction_node_name = name
        junction_node = self.dg.nodes[name]
        # Since there should only be one output node, this can be found first
        # from the dict of successors
        try:
            output_node_name = list(dict(self.dg.succ[name]).keys())[0]
            output_node = self.dg.nodes[output_node_name]
            output_channel = self.dg[name][output_node_name]
        except KeyError as e:
            raise KeyError("T-junction must have only one output")
        # these will be found later from iterating through the dict of
        # predecessor nodes to the junction node
        continuous_node = ''
        continuous_node_name = ''
        continuous_channel = ''
        dispersed_node = ''
        dispersed_node_name = ''
        dispersed_channel = ''
        # NetworkX allows for the creation of dicts that contain all of
        # the edges containing a certain attribute, in this case phase is
        # of interest
        phases = nx.get_edge_attributes(self.dg, 'phase')
        for pred_node, phase in phases.items():
            if phase == 'continuous':
                continuous_node_name = pred_node[0]
                continuous_node = self.dg.nodes[continuous_node_name]
                continuous_channel = self.dg[continuous_node_name][junction_node_name]
                # assert width and height to be equal to output
                self.exprs.append(Equals(continuous_channel['width'],
                                         output_channel['width']
                                         ))
                self.exprs.append(Equals(continuous_channel['height'],
                                         output_channel['height']
                                         ))
            elif phase == 'dispersed':
                dispersed_node_name = pred_node[0]
                dispersed_node = self.dg.nodes[dispersed_node_name]
                dispersed_channel = self.dg[dispersed_node_name][junction_node_name]
                # Assert that only the height of channel be equal
                self.exprs.append(Equals(dispersed_channel['height'],
                                         output_channel['height']
                                         ))
            elif phase == 'output':
                continue
            else:
                raise ValueError("Invalid phase for T-junction: %s" % name)

        # Epsilon, sharpness of T-junc, must be greater than 0
        epsilon = Symbol('epsilon', REAL)
        self.exprs.append(GE(epsilon, Real(0)))

        # Pressure at each of the 4 nodes must be equal
        self.exprs.append(Equals(junction_node['pressure'],
                                 continuous_node['pressure']
                                 ))
        self.exprs.append(Equals(junction_node['pressure'],
                                 dispersed_node['pressure']
                                 ))
        self.exprs.append(Equals(junction_node['pressure'],
                                 output_node['pressure']
                                 ))

        # Viscosity in continous phase equals viscosity at output
        self.exprs.append(Equals(continuous_node['viscosity'],
                                 output_node['viscosity']
                                 ))

        # Droplet volume in channel equals calculated droplet volume
        # TODO: Manifold also has a table of constraints in the Schematic and
        # sets ChannelDropletVolume equal to dropletVolumeConstraint, however
        # the constraint is void (new instance of RealTypeValue) and I think
        # could conflict with calculated value, so ignoring it for now but
        # may be necessary to add at a later point if I'm misunderstand why
        # its needed
        v_output = output_channel['droplet_volume']
        self.exprs.append(Equals(v_output,
                                 self.calculate_droplet_volume(
                                     output_channel['height'],
                                     output_channel['width'],
                                     dispersed_channel['width'],
                                     epsilon,
                                     dispersed_node['flow_rate'],
                                     continuous_node['flow_rate']
                                 )))

        # Retrieve symbols for each node
        nxC = continuous_node['x']
        nyC = continuous_node['y']
        nxO = output_node['x']
        nyO = output_node['y']
        nxJ = junction_node['x']
        nyJ = junction_node['y']
        nxD = dispersed_node['x']
        nyD = dispersed_node['y']
        # Retrieve symbols for channel lengths
        lenC = continuous_channel['length']
        lenO = output_channel['length']
        lenD = dispersed_channel['length']

        # Constrain that continuous and output ports are in a straight line by
        # setting the area of the triangle formed between those two points and
        # the center of the t-junct to be 0
        # Formula for area of a triangle given 3 points
        # x_i (y_p − y_j ) + x_p (y_j − y_i ) + x_j (y_i − y_p ) / 2
        self.exprs.append(Equals(Real(0),
                                 Div(Plus(Times(nxC,
                                                Minus(nyJ, nyO)
                                                ),
                                          Plus(Times(nxJ,
                                                     Minus(nyO, nyC)
                                                     ),
                                               Times(nxO,
                                                     Minus(nyC, nyJ)
                                                     ))),
                                     Real(2)
                                     )))

        # Assert critical angle is <= calculated angle
        cosine_squared_theta_crit = Real(math.cos(
            math.radians(critCrossingAngle))**2)
        # Continuous to dispersed
        self.exprs.append(LE(cosine_squared_theta_crit,
                             self.cosine_law_crit_angle([nxC, nyC],
                                                        [nxJ, nyJ],
                                                        [nxD, nyD]
                                                        )))
        # Continuous to output
        self.exprs.append(LE(cosine_squared_theta_crit,
                             self.cosine_law_crit_angle([nxC, nyC],
                                                        [nxJ, nyJ],
                                                        [nxO, nyO]
                                                        )))
        # Output to dispersed
        self.exprs.append(LE(cosine_squared_theta_crit,
                             self.cosine_law_crit_angle([nxO, nyO],
                                                        [nxJ, nyJ],
                                                        [nxD, nyD]
                                                        )))

    # TODO: In Manifold this has the option for worst case analysis, need to
    #       understand when this is needed and implement it if needed
    def simple_pressure_flow(self, channel_name):
        """Assert difference in pressure at the two end nodes for a channel
        equals the flow rate in the channel times the channel resistance
        More complicated calculation available through
        analytical_pressure_flow method (TBD)
        :param str channel_name: Name of the channel
        """
        channel = self.dg.edges[channel_name]
        port_from = self.dg.nodes[channel_name[0]]
        port_to = self.dg.nodes[channel_name[1]]
        p1 = port_from['pressure']
        p2 = port_to['pressure']
        Q = channel['flow_rate']
        R = channel['resistance']
        return Equals(Minus(p1, p2),
                      Times(Q, R)
                      )

    def channel_output_pressure(self, channel_name):
        """Calculate the pressure at the output of a channel using
        P_out = R * Q - P_in
        :param str channel_name: Name of the channel
        """
        channel = self.dg.edges[channel_name]
        P_in = self.dg.nodes[channel_name[0]]['pressure']
        R = channel['resistance']
        Q = channel['flow_rate']
        return Minus(P_in,
                     Times(R, Q))

    def calculate_channel_resistance(self, channel_name):
        """Calculate the droplet resistance in a channel using:
        R = (12 * mu * L) / (w * h^3 * (1 - 0.630 (h/w)) )
        This formula assumes that channel height < width, so
        the first term returned is the assertion for that
        :param str channel_name: Name of the channel
        """
        channel = self.dg.edges[channel_name]
        w = channel['width']
        h = channel['height']
        mu = channel['viscosity']
        chL = channel['length']
        return (LT(h, w),
                Div(Times(Real(12),
                          Times(mu, chL)
                          ),
                    Times(w,
                          Times(Pow(h, Real(3)),
                                Minus(Real(1),
                                      Times(Real(0.63),
                                            Div(h, w)
                                            ))))))

    # TODO: Could redesign this to just take in the name of a channel
    #       and have it get the input and output ports and length
    def pythagorean_length(self, channel_name):
        """Use Pythagorean theorem to assert that the channel length
        (hypoteneuse) squared is equal to the legs squared so channel
        length is solved for
        :param str channel_name: Name of the channel
        """
        channel = self.dg.edges[channel_name]
        port_from = self.dg.nodes[channel_name[0]]
        port_to = self.dg.nodes[channel_name[1]]
        side_a = Minus(port_from['x'], port_to['x'])
        side_b = Minus(port_from['y'], port_to['y'])
        a_squared = Pow(side_a, Real(2))
        b_squared = Pow(side_b, Real(2))
        a_squared_plus_b_squared = Plus(a_squared, b_squared)
        c_squared = Pow(channel['length'], Real(2))
        return Equals(a_squared_plus_b_squared, c_squared)

    def cosine_law_crit_angle(self, node1, node2, node3):
        """Use cosine law to find cos^2(theta) between three points
        node1---node2---node3 to assert that it is less than cos^2(thetaC)
        where thetaC is the critical crossing angle
        """
        # Lengths of channels
        aX = Minus(node1[0], node2[0])
        aY = Minus(node1[1], node2[1])
        bX = Minus(node3[0], node2[0])
        bY = Minus(node3[1], node2[1])
        # Dot products between each channel
        a_dot_b_squared = Pow(Plus(Times(aX, bX),
                                   Times(aY, bY)
                                   ),
                              Real(2)
                              )
        a_squared_b_squared = Times(Plus(Times(aX, aX),
                                         Times(aY, aY)
                                         ),
                                    Plus(Times(bX, bX),
                                         Times(bY, bY)
                                         ),
                                    )
        return Div(a_dot_b_squared, a_squared_b_squared)

    def calculate_droplet_volume(self, h, w, wIn, epsilon, qD, qC):
        """From paper DOI:10.1039/c002625e.
        h=height of channel
        w=width of continuous/output channel
        wIn=width of dispersed_channel
        epsilon=0.414*radius of rounded edge where channels join
        qD=flow rate in dispersed_channel
        qC=flow rate in continuous_channel
        """
        q_gutter = Real(0.1)
        # normalizedVFill = 3pi/8 - (pi/2)(1 - pi/4)(h/w)
        v_fill_simple = Minus(
                Times(Real((3, 8)), Real(math.pi)),
                Times(Times(
                            Div(Real(math.pi), Real(2)),
                            Minus(Real(1),
                                  Div(Real(math.pi), Real(4)))),
                      Div(h, w)))

        hw_parallel = Div(Times(h, w), Plus(h, w))

        # r_pinch = w+((wIn-(hw_parallel - eps))+sqrt(2*((wIn-hw_parallel)*(w-hw_parallel))))
        r_pinch = Plus(w,
                       Plus(Minus(
                                  wIn,
                                  Minus(hw_parallel, epsilon)),
                            Pow(Times(
                                      Real(2),
                                      Times(Minus(wIn, hw_parallel),
                                            Minus(w, hw_parallel)
                                            )),
                                Real(0.5))))
        r_fill = w
        alpha = Times(Minus(
                            Real(1),
                            Div(Real(math.pi), Real(4))
                            ),
                      Times(Pow(
                                Minus(Real(1), q_gutter),
                                Real(-1)
                                ),
                            Plus(Minus(
                                       Pow(Div(r_pinch, w), Real(2)),
                                       Pow(Div(r_fill, w), Real(2))
                                       ),
                                 Times(Div(Real(math.pi), Real(4)),
                                       Times(Minus(
                                                   Div(r_pinch, w),
                                                   Div(r_fill, w)
                                                   ),
                                             Div(h, w)
                                             )))))

        return Times(Times(h, Times(w, w)),
                     Plus(v_fill_simple, Times(alpha, Div(qD, qC))))

    def calculate_port_flow_rate(self, port_in):
        """Calculate the flow rate into a port based on the cross sectional
        area of the channel it flows into, the pressure and the density
        eqn from https://en.wikipedia.org/wiki/Hagen-Poiseuille_equation
        flow_rate = area * sqrt(2*pressure/density)
        """
        areas = []
        port_in_named = self.dg.nodes[port_in]
        for port_out in self.dg.succ[port_in]:
            areas.append(Times(self.dg[port_in][port_out]['length'],
                               self.dg[port_in][port_out]['width']
                               ))
        total_area = Plus(areas)
        return Times(total_area,
                     Pow(Div(Times(Real(2),
                                   port_in_named['pressure']
                                   ),
                             port_in_named['density']
                             ),
                         Real(0.5)
                         ))

    def translate_schematic(self):
        """Validates that each node has the correct input and output
        conditions met then translates it into pysmt syntax
        Generates SMT formulas to simulate specialized nodes like T-junctions
        and stores them in self.exprs
        """
        # The translate method names are stored in a dictionary name where
        # the key is the name of that node or port kind, also run on channels
        # (Edges) and finish by constaining nodes to be within chip area
        for name in self.dg.nodes:
            self.translation_strats[self.dg.nodes[name]['kind']](name)
        for name in self.dg.edges:
            self.translation_strats[self.dg.edges[name]['shape']](name)
        for name in self.dg.nodes:
            self.translate_chip(name)

    def invoke_backend(self, _show):
        """Combine all of the SMT expressions into one expression to sent to Z3
        solver to determine solvability
        """
        formula = And(self.exprs)
        # Prints the generated formula in full, remove serialize for shortened
        if _show:
            pprint(formula.serialize())
            #  nx.draw(self.dg)
            #  plt.show()
        # Return None if not solvable, returns a dict-like structure giving the
        # range of values for each Symbol
        model = get_model(formula, solver_name='z3', logic=QF_NRA)
        if model:
            return model
        else:
            return "No solution found"

    def solve(self, show=False):
        """Create the SMT2 equation for this schematic outlining the design
        of a microfluidic circuit and use Z3 to solve it using pysmt
        """
        self.translate_schematic()
        return self.invoke_backend(show)
