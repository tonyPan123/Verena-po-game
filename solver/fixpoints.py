from solver.options import SynthesisOptions
from z3 import *
import os
import time
from examples.game import *
from common.util import *
from solver.beliefs import *
from solver.observations import *
from solver.belief_map import BeliefsMap

# TODO: add absolute observations
class FixpointCalculation:
    def __init__(self, game, rel_obs, abs_obs, options=None):
        self.options = options if options is not None else SynthesisOptions()
        self.game = game
        self.rel_obs = rel_obs
        self.abs_obs = abs_obs

    def substitute_memory_suffix(self, formula, old_vars, new_vars):
        """Replace old_vars with corresponding new_vars in the formula."""
        
        # Create substitution pairs
        substitutions = list(zip(old_vars, new_vars))
        
        return substitute(formula, substitutions)

    def relative_inv(self): 
        assert(self.rel_obs >= 0)
        d = self.rel_obs + 1
        inv = True
        eliminate = []
        for i in range(d):
            s = self.game.make_states(-d + i - 1)
            s_l = self.game.make_latent_states(-d + i - 1)
            s_p = self.game.make_states(-d + i)
            a = self.game.make_actions(-d + i - 1)

            inv = And(inv, self.game.transition_env(s, s_p, a))
            eliminate += list(a.values())
            if i == 0:
                eliminate += list(s.values())
                #eliminate += list(s_l.values())
            else: 
                eliminate += list(s_l.values())
        formula = quantifier_eliminate(Exists(eliminate, inv))
        formula = self.game.substitute_states(formula, -1, "org")
        formula = BoolVal(True)
        return Beliefs(And(formula, self.game.add_observable_constraints("org", -1)), [])

    def cpre(self, inv, attr):
        s = self.game.make_states("org")
        s_p = self.game.make_states("prime")
        a = self.game.make_actions("org")

        pre = And(self.game.safety(s), inv.get_formula())

        con_action = self.game.enable_action(a)

        env_model = self.game.transition_env(s, s_p, a)
        print(inv.get_formula())
        inv_p = self.game.substitute_states_inc(inv.get_formula(), -1 * self.rel_obs - 1, -1)
        inv_p = self.game.substitute_states(inv_p, "org", "prime")

        attr_p = self.game.substitute_states_inc(attr.get_feasible_obs(), -1 * self.rel_obs - 1, -1)
        #post = And(self.game.safety(s_p), attr_p)
        post = And(self.game.safety(s_p), attr_p, inv_p)

        # TODO: Simplify the inv_p to be just observation constratins? 
        formula = Implies(pre, And(con_action, Implies(And(env_model, self.game.add_observable_constraints("prime", 0)), post)))
 
        env_control_2 = list(s.values()) 
        env_control_2 = env_control_2 + list(s_p.values()) + list(self.game.make_states(0).values())

        con_control = list(a.values())
        #print(Exists(con_control, ForAll(env_control_2, formula)))
        new_attr = simplify(And(quantifier_eliminate(Exists(con_control, ForAll(env_control_2, formula))), attr.get_feasible_obs()))
        #print(quantifier_eliminate(Exists(con_control, ForAll(env_control_2, formula))))
        #print(new_attr)
        return Observations(new_attr)

    def safety_fixpoint(self):
        rel_inv = self.relative_inv() 
        #inv = BoolVal(True)
        #if len(reach_beliefs) > 0: 
        #    inv = BoolVal(False)
        #    for belief in reach_beliefs:
        #        inv = Or(inv, Implies(belief.get_feasible_obs(), belief.get_formula()))
        #    print(inv)
        #inv = And(rel_inv.get_formula(), Implies(reach_beliefs_mask.get_feasible_obs(), reach_beliefs_mask.get_formula()))
        #inv = rel_inv.get_formula()
        depth = 0
        safe_attr = Observations(BoolVal(True))
        while True: 
            new_attr = self.cpre(rel_inv, safe_attr)
            #print("loop")
            if not self.contains_initial(new_attr.get_feasible_obs(), rel_inv):
                #print(depth)
                return (depth, new_attr)
            #print(new_attr)
            solver = Solver()
            solver.add(safe_attr.get_feasible_obs())
            solver.add(Not(new_attr.get_feasible_obs()))
            res = solver.check()
            if res == sat:
                #print(solver.model())
                safe_attr = new_attr
                depth += 1
                continue
            else:
                smt_file = self.export_cpre_baseline_to_smt(rel_inv, new_attr, f"result.smt2")
                print(f"Exported formula to {smt_file}")
                return (-1, new_attr)

    def obs_fixpoint(self, beliefs):
        rel_inv = self.relative_inv() 
        inv = BoolVal(False)
        for belief in beliefs:
            #print(belief.get_formula())
            #print(belief.get_feasible_obs())
            inv = Or(inv, belief.get_formula())
        inv = And(rel_inv.get_formula(), inv)
        belief_map = Beliefs(inv, [])
        depth = 0
        safe_attr = Observations(BoolVal(True))
        while True: 
            new_attr = self.cpre(belief_map, safe_attr)
            print("loop")
            #print(new_attr.get_feasible_obs())
            if not self.contains_initial_obs(new_attr.get_feasible_obs(), belief_map):
                #print(depth)
                return (depth, new_attr)
            solver = Solver()
            solver.add(safe_attr.get_feasible_obs())
            solver.add(Not(new_attr.get_feasible_obs()))
            res = solver.check()
            if res == sat:
                #print(solver.model())
                safe_attr = new_attr
                depth += 1
                continue
            else:
                smt_file = self.export_cpre_baseline_to_smt(belief_map, new_attr, f"result.smt2")
                print(f"Exported formula to {smt_file}")
                return (-1, new_attr)
            
    def contains_initial_obs(self, attr, beliefs):
        s = self.game.make_states("org")
        init = self.game.initial(s)
        #beliefs, memory = beliefs.rewrite_memory_vars("org")
        #formula = And(init, beliefs, attr)
        obs_constraints = self.game.add_observable_constraints("org", -1)
        #formula = And(init, attr, beliefs.get_formula())
        formula = ForAll(list(s.values()) + list(self.game.make_states(-1).values()), Implies(And(init, obs_constraints), attr))
        #print(beliefs.get_initial_feasible())
        #print(attr)
        solver = Solver()
        solver.add(formula)
        res = solver.check()
        #if res == sat: 
        #    print(solver.model())
        return res == sat

    def export_cpre_baseline_to_smt(self, inv, attr, filename="cpre_formula.smt2"):
        s = self.game.make_states("org")
        s_p = self.game.make_states("prime")
        a = self.game.make_actions("org")

        pre = And(self.game.safety(s), inv.get_formula(), attr.get_feasible_obs())

        con_action = self.game.enable_action(a)

        env_model = self.game.transition_env(s, s_p, a)

        inv_p = self.game.substitute_states_inc(inv.get_formula(), -1 * self.rel_obs - 1, -1)
        inv_p = self.game.substitute_states(inv_p, "org", "prime")

        attr_p = self.game.substitute_states_inc(attr.get_feasible_obs(), -1 * self.rel_obs - 1, -1)
        #post = And(self.game.safety(s_p), attr_p)
        post = And(self.game.safety(s_p), attr_p, inv_p)

        # TODO: Simplify the inv_p to be just observation constratins? 
        formula = Implies(pre, And(con_action, Implies(And(env_model, self.game.add_observable_constraints("prime", 0)), post)))
 
        env_control_2 = list(s.values()) 
        env_control_2 = env_control_2 + list(s_p.values()) + list(self.game.make_states(0).values())

        con_control = list(a.values())
        # TODO: There could be multiple
        vars = []
        assert (self.rel_obs >= 0)
        for i in range(0, self.rel_obs + 1):
            vars += list(self.game.make_observable_states(-i - 1).values())
        full_formula = ForAll(vars, Exists(con_control, ForAll(env_control_2, formula)))
        # Configure Z3 to simplify distinct predicates
        #set_option("pp.max_distinct", 0)  # Don't use distinct in output
    
        # Simplify to convert distinct to inequalities
        full_formula = simplify(full_formula, blast_distinct=True)
        #print(full_formula)
        solver = Solver()
        solver.add(full_formula)

        with open(filename, 'w') as f:
            f.write(solver.to_smt2())
        
        print(f"Formula exported to {filename}")
        return filename



    def cpre_memory(self, beliefs, attr):

        s = self.game.make_states("org")
        s_p = self.game.make_states("prime")
        a = self.game.make_actions("org")

        pre = beliefs.get_formula()
        pre_memory = beliefs.get_memory()
        pre = And(pre, self.game.safety(s))

        con_action = self.game.enable_action(a)
        env_model = self.game.transition_env(s, s_p, a)

        post, post_memory = beliefs.rewrite_memory_vars("prime")
        post = self.game.substitute_states(post, "org", "prime")
        post = And(post, self.game.safety(s_p))

        attr_p = self.substitute_memory_suffix(attr, pre_memory.get_variables(), post_memory.get_variables())
        attr_p = self.game.substitute_states(attr_p, "org", "prime")

        formula = Implies(pre, And(con_action, Implies(env_model, And(post, attr_p))))

        env_control_1 = list(self.game.make_observable_states("prime").values())
        env_control_2 = list(self.game.make_latent_states("org").values()) + list(self.game.make_latent_states("prime").values())

        con_control = list(a.values())
        to_eliminate = Exists(con_control, ForAll(env_control_1, Exists(post_memory.get_variables(), ForAll(env_control_2, formula))))
        new_attr = quantifier_eliminate(to_eliminate)
        
        # Use combine_cnf instead of And
        return self.combine_cnf(new_attr, attr)

    def contains_initial(self, attr, beliefs):
        s = self.game.make_states("org")
        init = self.game.initial(s)
        #beliefs, memory = beliefs.rewrite_memory_vars("org")
        #formula = And(init, beliefs, attr)

        #formula = And(init, attr, beliefs.get_formula())
        formula = ForAll(list(s.values()), Implies(init, And(attr, beliefs.get_formula())))
        #print(beliefs.get_initial_feasible())
        #print(attr)
        solver = Solver()
        solver.add(formula)
        res = solver.check()
        #if res == sat: 
        #    print(solver.model())
        return res == sat

    def fixpoint_memory(self, beliefs, safe_attr = BoolVal(True)):
        #safe_attr = BoolVal(True)

        depth = 0
        trace_start = time.perf_counter()
        def trace(phase):
            if os.environ.get("POGAME_TRACE") == "1":
                print(f"[fixed-point iteration={depth} elapsed={time.perf_counter() - trace_start:.3f}s] {phase}", flush=True)
        while True: 
            trace("cpre_memory begin")
            new_attr = self.cpre_memory(beliefs, safe_attr)
            trace("cpre_memory end; contains_initial begin")
            print("loop")
            if not self.contains_initial(new_attr, beliefs):
                trace("contains_initial: false")
                return (depth, new_attr)
            if self.options.fixpoint_simplifier == "z3-context":
                trace("contains_initial: true; attribute simplify begin")
                # The recursive simplifier starts two fresh SMT solvers per atom
                # and repeatedly rebuilds each sibling context. QE output can have
                # thousands of atoms; Z3's context simplifier preserves the formula
                # while avoiding that repeated Python/solver work.
                new_attr = Then('simplify', 'ctx-solver-simplify', 'simplify')(new_attr).as_expr()
                #print(new_attr)
                trace("attribute simplify end; convergence check begin")
            else:
                trace("contains_initial: true; recur_simplify begin")
                new_attr = recur_simplify(new_attr, BoolVal(True))
                trace("recur_simplify end; convergence check begin")
            solver = Solver()
            solver.add(safe_attr)
            solver.add(Not(new_attr))
            res = solver.check()
            trace(f"convergence check: {res}")
            if res == sat:
                #print("model:")
                #print(solver.model())
                safe_attr = new_attr
                depth += 1
                continue
            else:
                simplified_attr = safe_attr
                #recur_simplify(safe_attr, BoolVal(True))
                #print(simplified_attr)
                
                # Export the cpre_memory formula to SMT file
                smt_file = self.export_cpre_to_smt(beliefs, simplified_attr, f"result.smt2")
                print(f"Exported formula to {smt_file}")
                if self.options.export_winning_region:
                    # Preserve the discovered invariant separately from the
                    # quantified extraction query, including a checkable witness
                    # that the final two fixpoint attributes are equivalent.
                    for filename, formula in (
                        ('fixed-point.smt2', simplified_attr),
                        ('winning-support.smt2', And(beliefs.get_formula(), self.game.safety(self.game.make_states('org')), simplified_attr)),
                        ('fixed-point-check.smt2', Xor(safe_attr, new_attr)),
                    ):
                        artifact = Solver()
                        artifact.add(formula)
                        with open(filename, 'w') as output:
                            output.write(artifact.to_smt2())
                
                return (-1, simplified_attr)


    def cpre_perfect(self, attr):

        s = self.game.make_states("org")
        s_p = self.game.make_states("prime")
        a = self.game.make_actions("org")

        pre = self.game.safety(s)

        con_action = self.game.enable_action(a)

        env_model = self.game.transition_env(s, s_p, a)

        attr_p = self.substitute_memory_suffix(attr, s.values(), s_p.values())

        post = self.game.safety(s_p)

        formula = Implies(pre, And(con_action, Implies(env_model, And(post, attr_p))))

        env_control = list(s_p.values())

        con_control = list(a.values())

        new_attr = quantifier_eliminate(Exists(con_control, ForAll(env_control, formula)))
        new_attr = recur_simplify(new_attr, BoolVal(True))
        print(new_attr)
        return And(new_attr, attr)


    def fixpoint_perfect(self):
        safe_attr = BoolVal(True)

        while True: 
            new_attr = self.cpre_perfect(safe_attr)
            print("loop")
            #print(new_attr)
            solver = Solver()
            solver.add(safe_attr)
            solver.add(Not(new_attr))
            res = solver.check()
            if res == sat:
                #print(solver.model())
                safe_attr = new_attr
                continue
            else:
                return new_attr

    def export_cpre_to_smt(self, beliefs, attr, filename="cpre_formula.smt2"):
        """
        Export the cpre_memory formula to an SMT2 file
        
        Args:
            beliefs: BeliefsMap object
            attr: Attribute formula
            filename: Output filename (default: cpre_formula.smt2)
        """
        s = self.game.make_states("org")
        s_p = self.game.make_states("prime")
        a = self.game.make_actions("org")

        pre = beliefs.get_formula()
        pre_memory = beliefs.get_memory()
        pre = And(pre, self.game.safety(s))

        con_action = self.game.enable_action(a)
        env_model = self.game.transition_env(s, s_p, a)

        post, post_memory = beliefs.rewrite_memory_vars("prime")
        post = self.game.substitute_states(post, "org", "prime")
        post = And(post, self.game.safety(s_p))

        attr_p = self.substitute_memory_suffix(attr, pre_memory.get_variables(), post_memory.get_variables())
        attr_p = self.game.substitute_states(attr_p, "org", "prime")

        formula = Implies(And(pre, attr), And(con_action, Implies(env_model, And(post, attr_p))))
        #print(formula)
        env_control_1 = list(self.game.make_observable_states("prime").values())
        env_control_2 = list(self.game.make_latent_states("org").values()) + list(self.game.make_latent_states("prime").values())
        con_control = list(a.values())
        
        # Construct the full quantified formula
        full_formula = ForAll(pre_memory.get_variables() + list(self.game.make_observable_states("org").values()), Exists(con_control, ForAll(env_control_1, Exists(post_memory.get_variables(), ForAll(env_control_2, formula)))))

        # Configure Z3 to simplify distinct predicates
        #set_option("pp.max_distinct", 0)  # Don't use distinct in output
    
        # Simplify to convert distinct to inequalities
        full_formula = simplify(full_formula, blast_distinct=True)
    
        solver = Solver()
        solver.add(full_formula)
        #print(full_formula)
        
        # Write to file
        with open(filename, 'w') as f:
            f.write(solver.to_smt2())
        
        print(f"Formula exported to {filename}")
        return filename

    def eliminate_env_with_concrete_action(self, beliefs, attr, con_action_model, post_memory_model):
        """
        Take concrete values for control actions and post memory, substitute them,
        and perform quantifier elimination on env_control_2.
        
        Args:
            beliefs: BeliefsMap object
            attr: Attribute formula
            con_action_model: Dict mapping action variables to concrete values
            post_memory_model: Dict mapping post memory variables to concrete values
            
        Returns:
            Formula with env_control_2 eliminated and concrete action/memory substituted
        """
        s = self.game.make_states("org")
        s_p = self.game.make_states("prime")
        a = self.game.make_actions("org")

        pre = beliefs.get_formula()
        pre_memory = beliefs.get_memory()
        pre = And(pre, self.game.safety(s))

        con_action = self.game.enable_action(a)
        env_model = self.game.transition_env(s, s_p, a)

        post, post_memory = beliefs.rewrite_memory_vars("prime")
        post = self.game.substitute_states(post, "org", "prime")
        post = And(post, self.game.safety(s_p))

        attr_p = self.substitute_memory_suffix(attr, pre_memory.get_variables(), post_memory.get_variables())
        attr_p = self.game.substitute_states(attr_p, "org", "prime")

        formula = Implies(And(pre, attr), And(con_action, Implies(env_model, And(post, attr_p))))
        
        # Create substitution list for concrete action values
        action_substitutions = []
        for action_var, action_value in con_action_model.items():
            action_substitutions.append((action_var, action_value))
        
        # Create substitution list for concrete post memory values
        post_memory_substitutions = []
        for mem_var, mem_value in post_memory_model.items():
            post_memory_substitutions.append((mem_var, mem_value))
        
        # Substitute concrete values into formula
        formula = substitute(formula, action_substitutions)
        formula = substitute(formula, post_memory_substitutions)
        
        # Simplify after substitution
        formula = simplify(formula)
        

        env_control_1 = list(self.game.make_observable_states("prime").values())

        # Define env_control_2 (latent variables at org and prime)
        env_control_2 = list(self.game.make_latent_states("org").values()) + list(self.game.make_latent_states("prime").values())
        
        # Perform quantifier elimination on env_control_2
        formula_with_qe = quantifier_eliminate(ForAll(env_control_1 + env_control_2, formula))
        
        # Final simplification
        result = simplify(formula_with_qe)
        
        print(f"Result after QE on env_control_2:")
        print(result)
        
        return recur_simplify(result, BoolVal(True))

    def combine_cnf(self, formula1, formula2):
        """
        Combine two CNF formulas with a single outer And.
        Handles True values efficiently.
        
        Args:
            formula1: First CNF formula (or True)
            formula2: Second CNF formula (or True)
            
        Returns:
            Combined formula with single outer And, or True if both are True
        """
        # Check if either formula is True
        if is_true(formula1):
            return formula2
        if is_true(formula2):
            return formula1
        
        # Both formulas are non-True, combine them
        clauses = []
        
        # Extract clauses from formula1
        if is_and(formula1):
            clauses.extend(formula1.children())
        else:
            clauses.append(formula1)
        
        # Extract clauses from formula2
        if is_and(formula2):
            clauses.extend(formula2.children())
        else:
            clauses.append(formula2)
        
        # Return combined formula with single And
        if len(clauses) == 0:
            return BoolVal(True)
        elif len(clauses) == 1:
            return clauses[0]
        else:
            return And(*clauses)
