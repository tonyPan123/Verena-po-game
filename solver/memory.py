from z3 import *

class Memory(): 
    def __init__(self, variables):
        self.variables = variables

    def get_variables(self):
        return self.variables
