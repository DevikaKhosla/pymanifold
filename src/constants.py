# May want to make it a text file so its easier
class FluidProperties():

    PROPERTIES = {"default": [False, False, False, "none"],
                  "water": [999.87, 18200, 0.001, "none"],
                  "mineraloil": [800, 10000000000, 0.0003051, "none"],
                  "polyacrylamide": [1100, 14.28, 0.003, "none"],
                  "ep_cross_test_sample": [999.87, 18200, 0.001, "ep_cross_test_analyte"]}

    # properties specific to samples for ep_cross (contain multiple analytes, which can vary in properties)
    ANALYTE_PROPERTIES = {"default": [False, False, False, False],
                          "none": [False, False, False, False],
                          "ep_cross_test_analyte": [ [0.1, 0.1, 0.1, 0.1],
                                                     [0.2, 0.2, 0.2, 0.2],
                                                     [0.05, 0.05, 0.05, 0.05],
                                                     [-1, -2, -3, -4]] }
                                                 # ep_cross_test_analyte numbers are made up

    def getDensity(self, fluid_name):
            return self.PROPERTIES[fluid_name][0]

    def getResistivity(self, fluid_name):
            return self.PROPERTIES[fluid_name][1]

    def getViscosity(self, fluid_name):
            return self.PROPERTIES[fluid_name][2]


    def getDiffusivities(self, fluid_name):
        analyte_name = self.PROPERTIES[fluid_name][3]
        return self.ANALYTE_PROPERTIES[analyte_name][0]

    def getInitialConcentrations(self, fluid_name):
        analyte_name = self.PROPERTIES[fluid_name][3]
        return self.ANALYTE_PROPERTIES[analyte_name][1]

    def getRadii(self, fluid_name):
        analyte_name = self.PROPERTIES[fluid_name][3]
        return self.ANALYTE_PROPERTIES[analyte_name][2]

    def getCharges(self, fluid_name):
        analyte_name = self.PROPERTIES[fluid_name][3]
        return self.ANALYTE_PROPERTIES[analyte_name][3]
