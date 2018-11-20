import src.pymanifold as pymf

sch = pymf.Schematic([0, 0, 10, 10])
#       D
#       |
#   C---N---O
continuous_node = 'continuous'
dispersed_node = 'dispersed'
output_node = 'out'
junction_node = 't_j'
min_channel_length = 1
min_channel_width = 1
min_channel_height = 0.001

# Continuous and output node should have same flow rate
# syntax: sch.port(name, design[, pressure, flow_rate, density, X_pos, Y_pos])
sch.port(continuous_node, 'input', min_pressure=1) #, fluid_name='mineraloil')
sch.port(dispersed_node, 'input', min_pressure=1) #, fluid_name='water')
sch.port(output_node, 'output')

# syntax: sch.node(name, X_pos, Y_pos, kind='node')
sch.node(junction_node, 1, 0, kind='tjunc')

# syntax: sch.channel(shape, min_length, width, height, input, output)
sch.channel(junction_node, output_node, phase='output')
sch.channel(continuous_node, junction_node, phase='continuous')
sch.channel(dispersed_node, junction_node, phase='dispersed')

#  sch.solve()
model = sch.solve(show=True)
print(model)


def test_answer():
    assert model != "No solution found"
