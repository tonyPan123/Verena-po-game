from z3 import *
from solver.memory import Memory
from common.util import *

class BeliefsMap(): 
    def __init__(self, formula):
        m_0 = Int(f'm{0}_org')
        memory_vars = [m_0]
        memory_constraints = [m_0 == 0]
        
        # Store memory variables in Memory class
        self.memory = Memory(memory_vars)

        # Create the disjunct
        disjunct = And(formula, *memory_constraints)
        
        # Update formula to include memory constraints
        self.formula = disjunct

        # Store disjuncts separately
        self.disjuncts = [disjunct]
        
        self.m_0 = 0

    def get_formula(self):
        return self.formula
    
    def get_memory(self):
        return self.memory
    
    def get_disjuncts(self):
        """Return list of all disjuncts"""
        return self.disjuncts
    
    def rewrite_memory_vars(self, suffix):
        """
        Rewrite all memory variables mi_org to mi_{suffix}
        
        Args:
            suffix: String to replace 'org' with in memory variable names
            
        Returns:
            Tuple of (new_formula, new_memory) with renamed variables
        """
        old_vars = self.memory.get_variables()
        new_vars = []
        substitutions = []
        
        # Create new memory variables with suffix replacing 'org'
        for old_var in old_vars:
            old_name = old_var.decl().name()
            
            # Replace _org with _{suffix}
            if old_name.endswith('_org'):
                base_name = old_name[:-4]  # Remove '_org'
                new_name = f"{base_name}_{suffix}"
            else:
                # If no _org suffix, just append _{suffix}
                new_name = f"{old_name}_{suffix}"
        
            # Create new variable with same type
            if isinstance(old_var, ArithRef):
                if is_int(old_var):
                    new_var = Int(new_name)
                elif is_real(old_var):
                    new_var = Real(new_name)
                else:
                    new_var = Int(new_name)
            elif isinstance(old_var, BoolRef):
                new_var = Bool(new_name)
            else:
                new_var = Int(new_name)
            
            new_vars.append(new_var)
            substitutions.append((old_var, new_var))
        
        # Substitute in formula
        new_formula = substitute(self.formula, substitutions)
        new_memory = Memory(new_vars)
        
        return (new_formula, new_memory)


    def rewrite_memory_vars_local(self, formula, old_vars, suffix):
        """Return the formula with each old_vars variable renamed using the suffix."""
        substitutions = []
        
        # Create new memory variables with suffix
        for old_var in old_vars:
            old_name = old_var.decl().name()
            new_name = f"{old_name}_{suffix}"
            
            # Create new variable with same type
            if isinstance(old_var, ArithRef):
                if is_int(old_var):
                    new_var = Int(new_name)
                elif is_real(old_var):
                    new_var = Real(new_name)
                else:
                    new_var = Int(new_name)
            elif isinstance(old_var, BoolRef):
                new_var = Bool(new_name)
            else:
                new_var = Int(new_name)
            
            substitutions.append((old_var, new_var))
        
        # Substitute in formula
        new_formula = substitute(formula, substitutions)
        
        return new_formula

    def merge_initial(self, new_formula, observables, states): 
        self.m_0 += 1
        m_0 = Real(f'm_{0}')
        memory_vars = [m_0]
        memory_constraints = [m_0 == self.m_0]

        # Create memory variable m_i for each observable
        for i, obs in enumerate(observables):
            index = i + 1
            if isinstance(obs, ArithRef):
                # For integer/real variables
                if is_int(obs):
                    m_i = Int(f'm_{index}')
                elif is_real(obs):
                    m_i = Real(f'm_{index}')
                else:
                    m_i = Int(f'm_{index}')  # default to Int
            elif isinstance(obs, BoolRef):
                # For boolean variables
                m_i = Bool(f'm_{index}')
            else:
                # Default case
                m_i = Int(f'm_{index}')

            memory_vars.append(m_i)
            # Add constraint: m_i == observable_i
            memory_constraints.append(m_i == obs)
            
        # Store memory variables in Memory class
        if len(self.memory.get_variables()) < len(memory_vars):
            self.memory = Memory(memory_vars)
        
        # Create new disjunct
        new_disjunct = And(new_formula, *memory_constraints)
        
        # Add to disjuncts list
        self.disjuncts.append(new_disjunct)
        
        # Update formula to include memory constraints
        self.formula = Or(self.formula, new_disjunct)

        initial_feasible = quantifier_eliminate(Exists(states, new_disjunct))
        self.initial_feasible = self.rewrite_memory_vars_local(initial_feasible, memory_vars, "org")

    def get_initial_feasible(self):
        return self.initial_feasible

    def merge_old(self, new_formula, observables): 
        self.m_0 += 1
        m_0 = Real(f'm_{0}')
        memory_vars = [m_0]
        memory_constraints = [m_0 == self.m_0]

        # Create memory variable m_i for each observable
        for i, obs in enumerate(observables):
            index = i + 1
            if isinstance(obs, ArithRef):
                # For integer/real variables
                if is_int(obs):
                    m_i = Int(f'm_{index}')
                elif is_real(obs):
                    m_i = Real(f'm_{index}')
                else:
                    m_i = Int(f'm_{index}')  # default to Int
            elif isinstance(obs, BoolRef):
                # For boolean variables
                m_i = Bool(f'm_{index}')
            else:
                # Default case
                m_i = Int(f'm_{index}')

            memory_vars.append(m_i)
            new_formula = substitute(new_formula, (obs, m_i))
            
        # Store memory variables in Memory class
        if len(self.memory.get_variables()) < len(memory_vars):
            self.memory = Memory(memory_vars)
        
        # Create new disjunct
        new_disjunct = And(new_formula, *memory_constraints)
        
        # Add to disjuncts list
        self.disjuncts.append(new_disjunct)
        
        # Update formula to include memory constraints
        self.formula = Or(self.formula, new_disjunct)

    # Assume memory_var and latent_var both contains subscript org
    def merge(self, formula, extra_memory_vars): 
        self.m_0 += 1
        m_0 = Int(f'm{0}_org')
        memory_constraints = [m_0 == self.m_0]

        # Add _org suffix to extra memory variable names
        memory_vars_with_org = [m_0]
        substitutions = []
        
        for extra_var in extra_memory_vars:
            old_name = extra_var.decl().name()
            new_name = f"{old_name}_org"
            
            # Create new variable with same type and _org suffix
            if isinstance(extra_var, ArithRef):
                if is_int(extra_var):
                    new_var = Int(new_name)
                elif is_real(extra_var):
                    new_var = Real(new_name)
                else:
                    new_var = Int(new_name)
            elif isinstance(extra_var, BoolRef):
                new_var = Bool(new_name)
            else:
                new_var = Int(new_name)
            
            memory_vars_with_org.append(new_var)
            substitutions.append((extra_var, new_var))
        
        # Substitute extra_memory_vars with their _org versions in formula
        formula = substitute(formula, substitutions)
        
        # Successive mining rounds can use different memory variables, even
        # when their lists have the same length. Keep the union so every
        # accumulated disjunct is renamed and quantified during export.
        memory_vars = self.memory.get_variables().copy()
        for variable in memory_vars_with_org:
            if not any(variable.eq(existing) for existing in memory_vars):
                memory_vars.append(variable)
        self.memory = Memory(memory_vars)

        # Create new disjunct
        new_disjunct = And(formula, *memory_constraints)
        
        # Add to disjuncts list
        self.disjuncts.append(new_disjunct)
        
        # Update formula
        self.formula = Or(self.formula, new_disjunct)
