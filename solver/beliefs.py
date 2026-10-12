from z3 import *
from common.util import quantifier_eliminate
from solver.observations import *

class Beliefs():    
    def toString(self):
        return (f"Beliefs:\n"
                f"  Formula: {self.formula}\n"
                f"  {self.obs.toString()}\n"
                f"  Hidden States: {self.hidden_states}")

    def __init__(self, formula, abs_obs, *args):
        self.formula = formula
        self.abs_obs = abs_obs

        if len(args) == 1:
            self.hidden_states = args[0]
            # Calculate obs on the fly
            to_eliminate = Exists(list(args[0]), formula)
            feasible_obs = quantifier_eliminate(to_eliminate)

            self.obs = Observations(feasible_obs)
            
        else:
            self.hidden_states = None
            self.obs = None

    def get_formula(self):
        return self.formula

    def get_obs(self):
        return self.obs

    def get_feasible_obs(self):
        return self.obs.get_feasible_obs()

    def get_abs_obs(self):
        return self.abs_obs
    #def get_hidden_states(self):
    #    return self.hidden_states