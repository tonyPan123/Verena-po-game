from solver.options import SynthesisOptions
from z3 import *
from examples import game
from examples.game import *
from common.util import *
import time
from solver.policy import Policy
from solver.beliefs import Beliefs
from solver.belief_map import BeliefsMap
from solver.forward_planner import ForwardPlanner
from solver.fixpoints import FixpointCalculation
from solver.template_miner import TemplateMiner
from solver.observations import Observations
import subprocess, time
import json
from pathlib import Path

class Synthesizer:

    def __init__(self, game, options=None):
        self.options = options if options is not None else SynthesisOptions()
        self.game = game

    def syn_strategy(self): 
        # Initialize the forward planner and fixpoint calculator
        planner = ForwardPlanner(game, 0, -1)
        fixpoint_calculator = FixpointCalculation(game, 0, -1, options=self.options)

        depth = 0

        safe_attr = fixpoint_calculator.safety_fixpoint()
        while True:
            beliefs = planner.forward_planning(depth)
            initial = planner.backward_fixpoint(beliefs, safe_attr)

            solver = Solver()
            solver.add(beliefs[0].get_feasible_obs())
            solver.add(Not(initial))
            if solver.check() == unsat:
                return "Good"

            depth += 1

    def syn_strategy_with_observation(self, game, rel_obs, abs_obs):
        # Initialize the forward planner and fixpoint calculator
        planner = ForwardPlanner(game, rel_obs, abs_obs)
        fixpoint_calculator = FixpointCalculation(game, rel_obs, abs_obs, options=self.options)
        
        depth = 0

        while True:
            beliefs = planner.forward_planning(depth)

            mask = BoolVal(False)
            for b in beliefs:
                mask = Or(mask, b.get_formula())
            belief = Beliefs(mask, list(game.make_latent_states(0).values()))
            safe_attr = fixpoint_calculator.safety_fixpoint(belief)

            if self.force_init_reach_attr(safe_attr, beliefs):
                return safe_attr

            depth += 1

    def force_init_reach_attr(self, safe_attr, beliefs):
        s = Solver()
        #s.add(safe_attr.get_feasible_obs())
        init = beliefs[0].get_feasible_obs()
        s.add(And(init, Not(safe_attr.get_feasible_obs())))
        if s.check() == unsat:
            return True
        else:
            return False
        
    def syn_strategy_with_memory(self, game):
        s = game.make_states(0)
        observables = game.make_observable_states(0).values()
        #observables = game.make_states(0).values()
        #belief_map = BeliefsMap(game.safety(s), observables)
        belief_map = BeliefsMap(game.safety(s), observables)
        belief_map.merge_initial(game.initial(s), observables, list(s.values()))
        solver = FixpointCalculation(game, 0, -1, options=self.options)
        planner = ForwardPlanner(game, 0, -1)

        last_depth = 0
        while True:
            depth = solver.fixpoint_memory(belief_map)
            print(depth)
            if depth == -1: 
                return "Good"
            beliefs = planner.forward_planning(depth - 1)

            for i in range(last_depth + 1, depth + 1):
                abs_obs_list = beliefs[i].get_abs_obs().copy()
                observables = []
                #abs_obs_list.reverse()
                for attribute, index in abs_obs_list:
                    if attribute == 'obs':
                        observables.extend(game.make_observable_states(index).values())
                    elif attribute == 'action':
                        observables.extend(game.make_actions(index).values())
                    else: 
                        raise Exception("Unknown attribute type")
                formula = beliefs[i].get_formula()
                #print(formula)
                formula = game.substitute_states(formula, "org", 0)
                formula = recur_simplify(formula, BoolVal(True))
                print(formula)
                print(observables)
                belief_map.merge(formula, observables)

            last_depth = depth

    def syn_strategy_with_template_mining(self, planning_depth = 0, is_real = True, generalization_threshold = 5, bad_threshold = 1, contain_safety = True, aggressive_point_memory = False):
        game = self.game
        s = game.make_states("org")
        initial = quantifier_eliminate(Exists(list(game.make_observable_states("org").values()), 
                                            game.initial(s))
                                        )
        
        total_time_start = time.time()
        total_forward_planning_time = 0
        total_template_mining_time = 0
        total_fixpoint_time = 0
        beliefs = []  # Initialize to store beliefs from forward planning
        
        while True:
            belief_map = BeliefsMap(initial)

            #miner = TemplateMiner(game, False, 5, 0)
            miner = TemplateMiner(game, is_real, generalization_threshold, bad_threshold, aggressive_point_memory, options=self.options)

            if contain_safety:
                mining_start = time.time()
                safe = game.safety(s)
                safe_belief = Beliefs(safe, -1, list(game.make_latent_states("org").values()))
                templates, mem_vars = miner.mine_all([safe_belief])
                mining_time = time.time() - mining_start
                total_template_mining_time += mining_time
                print(f"Safety template mining time: {mining_time:.4f} seconds")
                for level in sorted(templates.keys()):
                    print(f"Level {level} templates:")
                    for t in templates[level]:
                        print(f"  {t}")
                        belief_map.merge(t, mem_vars[1:])
            if planning_depth >= 0:
                planning_start = time.time()
                planner = ForwardPlanner(game, 0, -1)
                assert planning_depth >= 0
                beliefs = planner.forward_planning(planning_depth)
                planning_time = time.time() - planning_start
                total_forward_planning_time += planning_time
                print(f"Forward planning time (depth {planning_depth}): {planning_time:.4f} seconds")
                #print(len(beliefs))
                #for belief in beliefs:
                #    print(belief.get_formula())

                if beliefs == []:
                    total_time = time.time() - total_time_start
                    print("Planning failed")
                    print(f"\n=== Failure Summary ===")
                    print(f"Failed at planning depth: {planning_depth+1}")
                    print(f"Total forward planning time: {total_forward_planning_time:.4f} seconds")
                    print(f"Total template mining time: {total_template_mining_time:.4f} seconds")
                    print(f"Total fixpoint calculation time: {total_fixpoint_time:.4f} seconds")
                    print(f"Total execution time: {total_time:.4f} seconds")
                    # Calculate transition function formula size
                    s = game.make_states("org")
                    s_p = game.make_states("prime")
                    a = game.make_actions("org")
                    transition_formula = game.transition_env(s, s_p, a)
                    transition_formula_size = calculate_formula_size(transition_formula) + calculate_formula_size(game.enable_action(a))
                    print("\n=== Transition Function Statistics ===")
                    print(f"Transition formula size (AST nodes): {transition_formula_size}")
                    return "unrealizable"
                mining_start = time.time()
                templates, mem_vars = miner.mine_all(beliefs[1:2 + planning_depth])
                mining_time = time.time() - mining_start
                total_template_mining_time += mining_time
                #print(f"Belief template mining time: {mining_time:.4f} seconds")
                for level in sorted(templates.keys()):
                    print(f"Level {level} templates:")
                    for t in templates[level]:
                        print(f"  {t}")
                        belief_map.merge(t, mem_vars[1:])
            print()
            print()
            print()
            print(belief_map.get_formula())
            if self.options.export_winning_region:
                # Keep the learned support even if the following fixpoint times out.
                # These files let reviewers compare discovery with a known support.
                snapshot = Solver()
                snapshot.add(belief_map.get_formula())
                Path(f'template-support-depth-{planning_depth}.smt2').write_text(snapshot.to_smt2())
                Path(f'template-memory-depth-{planning_depth}.json').write_text(json.dumps([
                    {'name': str(v), 'sort': str(v.sort())}
                    for v in belief_map.get_memory().get_variables()
                ], indent=2) + '\n')
            fixpoint_start = time.time()
            solver = FixpointCalculation(game, 0, -1, options=self.options)
            fixpoint, attr = solver.fixpoint_memory(belief_map)
            fixpoint_time = time.time() - fixpoint_start
            total_fixpoint_time += fixpoint_time
            print(f"Fixpoint calculation time: {fixpoint_time:.4f} seconds")
            print(fixpoint)
            if fixpoint == -1:
                total_time = time.time() - total_time_start
                
                # Analyze belief map statistics
                num_templates = belief_map.m_0 + 1
                num_memory_vars = len(belief_map.get_memory().get_variables())
                formula_size = calculate_formula_size(belief_map.get_formula())
                
                # Calculate transition function formula size
                s = game.make_states("org")
                s_p = game.make_states("prime")
                a = game.make_actions("org")
                transition_formula = game.transition_env(s, s_p, a)
                transition_formula_size = calculate_formula_size(transition_formula) + calculate_formula_size(game.enable_action(a))
                
                # Calculate formula sizes for all beliefs from forward planning
                belief_formula_sizes = []
                total_belief_formula_size = 0
                if beliefs:
                    for i, belief in enumerate(beliefs):
                        #print(belief.get_formula())
                        belief_size = calculate_formula_size(belief.get_formula())
                        belief_formula_sizes.append(belief_size)
                        total_belief_formula_size += belief_size
                
                print("\n=== Timing Summary ===")
                print(f"Planning depth reached: {planning_depth+1}")
                print(f"Total forward planning time: {total_forward_planning_time:.4f} seconds")
                print(f"Total template mining time: {total_template_mining_time:.4f} seconds")
                print(f"Total fixpoint calculation time: {total_fixpoint_time:.4f} seconds")
                print(f"Total execution time: {total_time:.4f} seconds")
                
                print("\n=== Belief Map Statistics ===")
                print(f"Number of templates: {num_templates}")
                print(f"Number of memory variables: {num_memory_vars}")
                print(f"Formula size (AST nodes): {formula_size}")
                
                print("\n=== Transition Function Statistics ===")
                print(f"Transition formula size (AST nodes): {transition_formula_size}")
                
                print("\n=== Forward Planning Beliefs Statistics ===")
                print(f"Number of beliefs: {len(beliefs)}")
                if belief_formula_sizes:
                    for i, size in enumerate(belief_formula_sizes):
                        print(f"Belief {i} formula size: {size}")
                    print(f"Total belief formula size: {total_belief_formula_size}")
                    if len(beliefs) > 0:
                        print(f"Average belief formula size: {total_belief_formula_size / len(beliefs):.2f}")
                return "realizable"
            planning_depth = planning_depth + 1
            #return

    def syn_strategy_with_template(self,templates, mem_vars, initial_attr = BoolVal(True), simulated_depth = 1):
        game = self.game
        s = game.make_states("org")
        initial = quantifier_eliminate(Exists(list(game.make_observable_states("org").values()), 
                                            game.initial(s))
                                        )
        belief_map = BeliefsMap(initial)

        beliefs = []

        planning_start = time.time()
        if simulated_depth >= 0:
            planner = ForwardPlanner(game, 0, -1)
            beliefs = planner.forward_planning(simulated_depth)
        planning_time = time.time() - planning_start
        
        mining_start = time.time()
        if simulated_depth >= 0:
            #miner = TemplateMiner(game, is_real, generalization_threshold, bad_threshold)
            miner = TemplateMiner(game, True, 5, 1, options=self.options)
            miner.mine_all(beliefs[1:2 + simulated_depth])
            #miner.mine_all(beliefs[1:2])
        mining_time = time.time() - mining_start

        for template in templates:
            belief_map.merge(template, mem_vars)

        print(belief_map.get_formula())
        
        fixpoint_start = time.time()
        solver = FixpointCalculation(game, 0, -1, options=self.options)
        fixpoint, attr = solver.fixpoint_memory(belief_map, initial_attr)
        fixpoint_time = time.time() - fixpoint_start
        
        print(fixpoint)
        #print(attr)
        
        print(f"\n=== Timing Summary ===")
        print(f"Forward planning time: {planning_time:.4f} seconds")
        print(f"Template mining time: {mining_time:.4f} seconds")
        print(f"Fixpoint calculation time: {fixpoint_time:.4f} seconds")
        print(f"Total execution time: {planning_time + mining_time + fixpoint_time:.4f} seconds")

        # Analyze belief map statistics
        num_templates = belief_map.m_0 + 1
        num_memory_vars = len(belief_map.get_memory().get_variables())
        formula_size = calculate_formula_size(belief_map.get_formula())
        print("\n=== Belief Map Statistics ===")
        print(f"Number of templates: {num_templates}")
        print(f"Number of memory variables: {num_memory_vars}")
        print(f"Formula size (AST nodes): {formula_size}")   

        # Calculate transition function formula size
        s = game.make_states("org")
        s_p = game.make_states("prime")
        a = game.make_actions("org")
        transition_formula = game.transition_env(s, s_p, a)
        transition_formula_size = calculate_formula_size(transition_formula) + calculate_formula_size(game.enable_action(a))
        print("\n=== Transition Function Statistics ===")
        print(f"Transition formula size (AST nodes): {transition_formula_size}")


        total_belief_formula_size = 0
        if beliefs:
            for i, belief in enumerate(beliefs):
                #print(belief.get_formula())
                belief_size = calculate_formula_size(belief.get_formula())
                #belief_formula_sizes.append(belief_size)
                total_belief_formula_size += belief_size
        print("\n=== Forward Planning Beliefs Statistics ===")
        print(f"Beliefs Size: {total_belief_formula_size }")
        return "realizable" if fixpoint == -1 else "inconclusive"


    def backward_only_baseline(self, game):
        solver = FixpointCalculation(game, 0, -1, options=self.options)
        depth, attr = solver.safety_fixpoint()
        if depth == -1: 
            return "Good"
        return "Bad"

    def fix_memory_baseline(self, game, rel_obs, strategy_extractor=None):
        total_time = 0
        planning_depth = 0
        planner = ForwardPlanner(game, 0, -1)
        while True: 
            total_time_start = time.time()
            beliefs = planner.forward_planning(planning_depth)
            if beliefs == []: 
                total_time += (time.time() - total_time_start)
                print(f"Counter-example finding takes {total_time:.4f}")
                return "Bad"

            # Construct Obs Abstraction
            new_beliefs = []
            for i, belief in enumerate(beliefs): 
                next_belief = belief.get_formula()
                for id, abs_index in belief.get_abs_obs(): 
                    if id == "action":
                        next_belief = quantifier_eliminate(Exists(list(self.game.make_actions(abs_index).values()), next_belief))
                    elif abs_index < (i - rel_obs):
                        next_belief = quantifier_eliminate(Exists(list(self.game.make_states(abs_index).values()), next_belief))
                # Substitution happening here
                for j in range(i - rel_obs, i + 1): 
                    #print(i, j, j - (i + 1))
                    next_belief = game.substitute_states(next_belief, j, j - (i + 1))
                #print(next_belief)
                new_beliefs.append(Beliefs(next_belief, [], list(self.game.make_states("org").values())))

            solver = FixpointCalculation(game, rel_obs, -1, options=self.options)
            depth, attr = solver.obs_fixpoint(new_beliefs)
            total_time += (time.time() - total_time_start)
            print(depth)
            if depth == -1: 
                print(f"Invariant finding takes {total_time:.4f}")
                start = time.perf_counter()
                winner = (strategy_extractor("result.smt2") if strategy_extractor
                          else self._baseline_strategy_winner("result.smt2"))
                duration_s = time.perf_counter() - start
                print(f"Strategy extraction takes {duration_s:.4f}")
                return "Good" if winner == "sat" else "Inconclusive"
            planning_depth = planning_depth + 1


    def forward_planning_baseline(self, game, is_real = True, strategy_extractor=None):
        planning_depth = 0
        s = game.make_states("org")
        initial = quantifier_eliminate(Exists(list(game.make_observable_states("org").values()), 
                                            game.initial(s))
                                        )
        belief_map = BeliefsMap(initial)
        planner = ForwardPlanner(game, 0, -1)
        miner = TemplateMiner(game, is_real, options=self.options)
        solver = FixpointCalculation(game, 0, -1, options=self.options)
        start = time.time()
        beliefs = []
        while True:
            beliefs = planner.forward_planning(planning_depth)
            if beliefs == []: 
                total_time = (time.time() - start)
                print(f"Counterexample takes {total_time:.4f}")
                return "Bad"

            templates, mem_vars = miner.mine_all(beliefs[1:2 + planning_depth])
            for level in sorted(templates.keys()):
                print(f"Level {level} templates:")
                for t in templates[level]:
                    print(f"  {t}")
                    belief_map.merge(t, mem_vars[1:])

            smt_file = solver.export_cpre_to_smt(belief_map, BoolVal(True), f"result.smt2")

            winner = (strategy_extractor(smt_file) if strategy_extractor
                      else self._baseline_strategy_winner(smt_file))
            if winner == "sat":
                total_time = time.time() - start
                print(f"Total running takes {total_time:.4f}")
                return "Good"
            planning_depth = planning_depth + 1


    @staticmethod
    def _baseline_strategy_winner(filename):
        """Legacy CLI adapter; artifact runners supply a recording extractor."""
        result = subprocess.run(["./simsat.native", "-synth", filename],
                                capture_output=True, text=True, check=True)
        print(result.stdout)
        if "Sat player wins" in result.stdout:
            return "sat"
        if "Unsat player wins" in result.stdout:
            return "unsat"
        return "unknown"
