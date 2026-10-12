from z3 import *

class Observations(): 
    def toString(self):
        return (f"Observations:\n"
                f"    Formula: {self.formula}\n")

    # TODO: add rel_obs and abs_obs
    def __init__(self, formula):
        # The formula that represent the observations
        self.formula = formula
        
        # The variable list that represent relative observation
        #self.rel_obs = rel_obs

        # The variable list that represent absolute observation
        #self.abs_obs = abs_obs

    def get_feasible_obs(self):
        return self.formula