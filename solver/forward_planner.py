from z3 import *
from examples.game import *
from common.util import *
from solver.policy import Policy
from solver.beliefs import Beliefs
from solver.observations import Observations

class ForwardPlanner:
    def __init__(self, game, rel_obs, abs_obs):
        self.game = game
        self.rel_obs = rel_obs
        self.abs_obs = abs_obs
        
        # Initialize global state variables
        org_state = self.game.make_states("org")
        initial_beliefs = Beliefs(
            And(self.game.initial(org_state), self.game.add_observable_constraints("org", 0)), 
            [("obs", 0)], 
            list(org_state.values())
        )
        
        self.abs_beliefs = [initial_beliefs]  # List of abstract beliefs
        self.block_obs = []                    # List of blocked observations
        self.policy = []                       # List of policies
        self.round = 0                         # Current game round

    # Warning: Deprecated
    # Get available observations such that the belief is not empty
    # Assume the states are in state 0
    #def get_obs_domain(self, beliefs):
    #    to_eliminate = Exists(list(self.game.make_latent_states(0).values()), beliefs)
    #    feasible_obs = quantifier_eliminate(to_eliminate)
    #    return feasible_obs

    # Get safe actions given the beliefs and feasible observations
    def get_safe_action(self, beliefs):
        s = self.game.make_states("org")
        s_p = self.game.make_states("prime")
        a = self.game.make_actions("org")

        # Assume the beliefs lie in safe
        pre = And(beliefs.get_formula(), beliefs.get_feasible_obs())
        con_action = self.game.enable_action(a)
        env_model = self.game.transition_env(s, s_p, a)
        post = self.game.safety(s_p)
        formula = Implies(pre, And(con_action, Implies(env_model, post)))

        env_control = list(s.values()) + list(s_p.values())
        query =  ForAll(env_control, formula)

        return Policy(quantifier_eliminate(query))

    # Get actions that will not generate any observation constrained by blockobs
    def get_non_block_action(self, beliefs, blockobs):
        s = self.game.make_states("org")
        s_p = self.game.make_states("prime")
        a = self.game.make_actions("org")

        # Assume the beliefs lie in safe
        pre = And(beliefs.get_formula(), beliefs.get_feasible_obs())
        con_action = self.game.enable_action(a)
        env_model = self.game.transition_env(s, s_p, a)
        #post = Not(blockobs.get_feasible_obs())
        post = blockobs.get_feasible_obs()
        formula = Implies(pre, And(con_action, Implies(env_model, post)))

        env_control = list(s.values()) + list(s_p.values())
        query =  ForAll(env_control, formula)

        return Policy(quantifier_eliminate(query))

    # Get the policy that should be at current round
    def get_local_policy(self, beliefs, blockobs):
        safe_action = self.get_safe_action(beliefs)
        non_block_action = self.get_non_block_action(beliefs, blockobs)
        safe_action.merge(non_block_action)
        return safe_action

    # Get the next belief to be explored
    def get_succ_belief_old(self, beliefs, policy, round): 
        s = self.game.make_states(0)
        s_p = self.game.make_states(1)
        a = self.game.make_actions(0)

        pre = And(beliefs.get_formula(), beliefs.get_feasible_obs())

        con_action = policy.get_formula()

        env_model = self.game.transition_env(s, s_p, a)

        formula = And(pre, con_action, env_model)

        to_eliminate = list(a.values()) 

        # Deal with absolute_obs
        if round > self.abs_obs:
            to_eliminate = to_eliminate + list(s.values())
        else: 
            to_eliminate = to_eliminate + list(self.game.make_latent_states(0).values())
 
        # Deal with relative_obs
        to_eliminate = to_eliminate + list(self.game.make_observable_states(-1 * self.rel_obs).values())
 
        next_beliefs = quantifier_eliminate(Exists(to_eliminate, formula))

        # Substitute states for absolute_obs
        if self.abs_obs >= round:
            next_beliefs = self.game.substitute_states(next_beliefs, 0, f'+{round}')
        # Substitute states for relative_obs
        next_beliefs = self.game.substitute_states_dec(next_beliefs, -1 * self.rel_obs + 1, 1)

        return Beliefs(next_beliefs, list(self.game.make_latent_states(0).values()))
    
    # Get the next belief to be explored
    def get_succ_belief(self, beliefs, policy, round): 
        s = self.game.make_states("org")
        s_p = self.game.make_states("prime")
        a = self.game.make_actions("org")

        pre = And(beliefs.get_formula(), beliefs.get_feasible_obs())

        con_action = policy.get_formula()

        env_model = self.game.transition_env(s, s_p, a)

        formula = And(pre, con_action, env_model)

        #to_eliminate = list(a.values()) + list(self.game.make_latent_states("org").values())
        to_eliminate = list(self.game.make_latent_states("org").values())
        next_beliefs = quantifier_eliminate(Exists(to_eliminate, formula)) 
        next_beliefs = self.game.substitute_states(next_beliefs, "org", round)
        next_beliefs = self.game.substitute_actions(next_beliefs, "org", round)
        next_beliefs = self.game.substitute_states(next_beliefs, "prime", "org")
        next_beliefs = And(next_beliefs, self.game.add_observable_constraints("org", round + 1))
        # Try forgetting past observations
        abs_obs_list = beliefs.get_abs_obs().copy()
        abs_obs_list.append(("action", round))
        #abs_obs_list.append(("obs", round + 1))
        new_obs_abs_list = []
        #print(abs_obs_list)
        if True:
            for attribute, i in abs_obs_list: 
                # TODO: make abs_obs arg less trivial
                if attribute == "obs" and self.obs_forgettable(Beliefs(next_beliefs, [], list(self.game.make_states("org").values())), i): 
                    next_beliefs = quantifier_eliminate(Exists(list(self.game.make_states(i).values()), next_beliefs))
                elif attribute == "action" and self.action_forgettable(Beliefs(next_beliefs, [], list(self.game.make_states("org").values())), i): 
                    #print(Exists(list(self.game.make_actions(i).values()), next_beliefs))
                    next_beliefs = quantifier_eliminate(Exists(list(self.game.make_actions(i).values()), next_beliefs))
                    #print(next_beliefs)
                    #print(i)
                else: 
                    new_obs_abs_list.append((attribute, i))
        new_obs_abs_list.append(("obs", round + 1))
        print(new_obs_abs_list)
    
        #print(next_beliefs)
        next_beliefs = recur_simplify(next_beliefs, BoolVal(True))
        return Beliefs(next_beliefs, new_obs_abs_list, list(self.game.make_states("org").values()))

    def action_forgettable(self, beliefs, target_round): 
        subst_belief = self.game.substitute_actions(beliefs.get_formula(), target_round, "prime")
        subst_action = self.game.substitute_actions(beliefs.get_feasible_obs(), target_round, "prime")
        belief_diff = And(beliefs.get_formula(), Not(subst_belief))

        solver = Solver()
        solver.add(beliefs.get_feasible_obs())
        solver.add(subst_action)
        solver.add(belief_diff)
        return solver.check() == unsat

    def obs_forgettable(self, beliefs, target_round): 
        subst_belief = self.game.substitute_states(beliefs.get_formula(), target_round, "prime")
        subst_obs = self.game.substitute_states(beliefs.get_feasible_obs(), target_round, "prime")
        belief_diff = And(beliefs.get_formula(), Not(subst_belief))

        solver = Solver()
        solver.add(beliefs.get_feasible_obs())
        solver.add(subst_obs)
        solver.add(belief_diff)
        return solver.check() == unsat

    # Check if the policy is feasible (there exists at least one action) for all observations in obs
    def check_policy_feasible(self, policy, obs):
        a = self.game.make_actions("org")

        solver = Solver()
        solver.add(obs.get_feasible_obs())
        solver.add(Not(Exists(list(a.values()), policy.get_formula())))
        res = solver.check()
        if res == sat: 
            return False
        else: 
            return True
        
    # Given the policy and current observations, calculate the observations to be blocked    
    def get_blocked_obs(self, policy, obs): 
        a = self.game.make_actions("org")

        query = Exists(list(a.values()), policy.get_formula())

        #formula = And(obs.get_feasible_obs(), Not(quantifier_eliminate(query)))
        formula = And(obs.get_feasible_obs(), quantifier_eliminate(query))
        
        return Observations(z3.simplify(formula))



    def forward_planning(self, depth):
        """
        Continue forward planning from current round to target depth.
        Uses instance variables to maintain state between calls.
        """
        while self.round <= depth:
            print("Round is " + str(self.round))
            current_belief = self.abs_beliefs[self.round]
            
            # Get local policy that avoids blocked observations
            if self.round >= len(self.block_obs): 
                #self.block_obs.append(Observations(BoolVal(False)))
                self.block_obs.append(Observations(BoolVal(True)))

            blocked = self.block_obs[self.round] 
            local_policy = self.get_local_policy(current_belief, blocked)
            # Check if policy exists for all valid observations
            policy_exists = self.check_policy_feasible(local_policy, current_belief.get_obs())
            if policy_exists:
                # Add new policy
                self.policy.append(local_policy)
                
                # Get successor belief
                b_succ = self.get_succ_belief(current_belief, local_policy, self.round)
                self.abs_beliefs.append(b_succ)
                #print(b_succ.get_formula())
                # Advance to the next round; repeated beliefs are not merged.

                self.round += 1
                
            else:
                # No safe action found for some observations
                if self.round == 0:
                    print("Failure")
                    return []
                
                # Calculate the observations to be blocked
                block_ob = self.get_blocked_obs(local_policy, current_belief.get_obs())
                block_ob = self.game.substitute_states(block_ob.get_feasible_obs(), self.round, "prime")
                block_ob = self.game.substitute_actions(block_ob, self.round - 1, "org")
                block_ob = Observations(block_ob)
                self.block_obs[self.round - 1] = block_ob
                # Remove latest additions
                self.policy.pop()
                self.abs_beliefs.pop()
                
                self.round -= 1

        return self.abs_beliefs
    
    def reset_planning(self):
        """Reset the planner to initial state"""
        org_state = self.game.make_states("org")
        initial_beliefs = Beliefs(
            And(self.game.initial(org_state), self.game.add_observable_constraints("org", 0)), 
            [0], 
            list(org_state.values())
        )
        
        self.abs_beliefs = [initial_beliefs]
        self.block_obs = []
        self.policy = []
        self.round = 0

    # ...existing code...

    def backward_fixpoint(self, beliefs, safe_attr): 
        obs = []
        for i in range(len(beliefs)): 
            obs.append(beliefs[i].get_feasible_obs())
        
        while True: 
            for i in reversed(range(0, len(obs))):
                print(i)
                new_obs = obs[i]
                if i == len(obs) - 1:
                    attr = safe_attr.get_feasible_obs()
                    attr = self.game.substitute_states(attr, -1, i)
                    #print(attr)
                    new_obs = And(attr, new_obs)
                    # TODO: Add check for looping into previous states later
                else: 
                    blocked = Observations(self.game.substitute_states(Not(obs[i + 1]), i + 1, "prime"))
                    local_policy = self.get_local_policy(beliefs[i], blocked)    
                    block_ob = self.get_blocked_obs(local_policy, Observations(obs[i]))
                    new_obs = And(Not(block_ob.get_feasible_obs()), new_obs)

                solver = Solver()
                solver.add(obs[i])
                solver.add(Not(new_obs))
                res = solver.check()
                if res == unsat:
                    return obs[0]
                obs[i] = new_obs



