from z3 import *
from common.util import quantifier_eliminate
from solver.observations import *

class Policy():    
    def toString(self):
        return (f"Policy:\n"
                f"  Formula: {self.formula}\n")

    def __init__(self, formula):
        self.formula = formula

    def get_formula(self):
        return self.formula
    
    def merge(self, other): 
        self.formula = And(self.formula, other.get_formula())