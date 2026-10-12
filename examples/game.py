from abc import ABC, abstractmethod
from z3 import *

class Game(ABC):
    def __init__(self):
        self.states = {}
        self.actions = {}
        self.observable_states = {}
        self.latent_states = {}

    @abstractmethod
    def initial(self, s):
        pass

    @abstractmethod
    def safety(self, s):
        pass

    @abstractmethod
    def enable_action(self, a): 
        pass

    @abstractmethod
    def transition_env(self, s, s_p):
        pass

    def observable_states(self):
        return self.observable_states

    def latent_states(self):
        return self.latent_states


    def make_state(self, key, value, index): 
        if value == 'Int':
            return Int(f'{key}_{index}')
        elif value == 'Real':
            return Real(f'{key}_{index}')
        elif value == 'Bool':
            return Bool(f'{key}_{index}')
        else:
            raise RuntimeError("Unsupported type")

    def make_observable_states(self, index): 
        obs_states = {}
        for key, value in self.observable_states.items():
            obs_states[key] = self.make_state(key, value, index)
        return obs_states

    def make_latent_states(self, index): 
        latent_states = {}
        for key, value in self.latent_states.items():
            latent_states[key] = self.make_state(key, value, index)
        return latent_states
    
    def make_states(self, index): 
        return {**self.make_observable_states(index), **self.make_latent_states(index)}

    def make_actions(self, index):
        actions = {}
        for key, value in self.actions.items():
            actions[key] = self.make_state(key, value, index)
        return actions
    
    def substitute_states(self, formula, src, target): 
        src_state = self.make_states(src)
        target_state = self.make_states(target)
        for key in src_state.keys():   
            formula = substitute(formula, (src_state[key], target_state[key]))
        return formula

    def substitute_actions(self, formula, src, target): 
        src_action = self.make_actions(src)
        target_action = self.make_actions(target)
        for key in src_action.keys():   
            formula = substitute(formula, (src_action[key], target_action[key]))
        return formula
    
    def add_observable_constraints(self, src, target):
        formula = BoolVal(True)
        pre = self.make_observable_states(src)
        post = self.make_observable_states(target)
        for key, value in self.observable_states.items():
            formula = And(formula, pre[key] == post[key])
        return formula

    
    def substitute_states_inc(self, formula, from_idx, to_idx):
        assert(from_idx <= to_idx)
        start_index = to_idx
        while start_index >= from_idx: 
            formula = self.substitute_states(formula, start_index, start_index + 1)
            start_index = start_index - 1
        return formula
    
    def substitute_states_dec(self, formula, from_idx, to_idx):
        assert(from_idx <= to_idx)
        start_index = from_idx
        while start_index <= to_idx: 
            formula = self.substitute_states(formula, start_index, start_index - 1)
            start_index = start_index + 1
        return formula
    
    def test_gg(self, rel_inv, attr):
        s = self.make_states(0)
        s_p = self.make_states(1)
        a = self.make_actions(0)
        pre = And(self.safety(s), s['x'] == 4, s['yn'] == 1, s['ys'] == 1, rel_inv)
        #pre = And(self.safety(s), s['x'] == 4, rel_inv)
        solver = Solver()
        solver.add(pre)
        solver.check()
        #print(solver.model())

        con_action = a['move'] == 3

        env_model = self.transition_env(s, s_p, a)

        post = Not(And(self.safety(s_p), attr))

        formula = Implies(And(pre, con_action, env_model), post)

        env_control_2 = list(self.make_latent_states(0).values()) 
        env_control_2 = env_control_2 + list(s_p.values())

        con_control = list(a.values())
        solver = Solver()
        solver.add(And(pre, con_action, env_model, post))
        solver.check()
        print(solver.model())
        return ForAll(env_control_2, And(env_model, post))

