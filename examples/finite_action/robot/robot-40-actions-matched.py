from z3 import *
from examples.game import Game

class RobotGame(Game):
    def __init__(self):
        super().__init__()
        self.actions = {
            'dx': 'Real',
            'dy': 'Real'
        }
        self.observable_states = {
            'step': 'Real'
        }
        self.latent_states = {
            'x': 'Real',
            'y': 'Real'
        }
        self.states = {**self.observable_states, **self.latent_states}

    # Define the initial state
    # Init ≡ (x == 0) ∧ (y == 0) ∧ (step == 0)
    def initial(self, s):
        return And(
            s['x'] == 0,
            s['y'] == 0,
            s['step'] == 0
        )

    # Safe ≡ (x >= 2 → 2 <= y <= 3) ∧ (step >= 3 → x == 4)
    def safety(self, s):
        return And(
            Implies(s['x'] >= 2, And(s['y'] >= 2, s['y'] <= 3)),
            Implies(s['step'] >= 2, s['x'] == 4)
        )

    # Action constraint: dx == 0 ∨ dy == 0
    def enable_action(self, a):
        return Or(a['dx'] == 0, a['dy'] == 0)

    # Define the transition relation for the environment
    # M ≡ (step' == step + 1)
    #     ∧ (dx == 0 ∨ dy == 0)
    #     ∧ (x' == x + dx)
    #     ∧ (y + dy - 1/2 <= y' <= y + dy + 1/2)
    def transition_env(self, s, s_p, a):
        T_forall = And(
            s_p['step'] == s['step'] + 1,
            s_p['x'] == s['x'] + a['dx'],
            Or(
                And(a['dy'] == 0, s_p['y'] == s['y']),
                And(Not(a['dy'] == 0), s_p['y'] >= s['y'] + a['dy'] - 0.5,
                s_p['y'] <= s['y'] + a['dy'] + 0.5)
            )
        )
        return T_forall


"""Finite action menus for the original robot_game.RobotGame model."""
from z3 import And, Or



class RobotFiniteGame(RobotGame):
    def __init__(self, max_distance=19):
        if not isinstance(max_distance, int) or max_distance < 1:
            raise ValueError('max_distance must be a positive integer')
        super().__init__()
        self.max_distance = max_distance

    def menu(self):
        # 2.5 is exact in binary and needed to land robustly in y in [2, 3].
        return [{'dx': 0, 'dy': 0}, {'dx': 0, 'dy': 2.5}] + [
            {'dx': sign * distance, 'dy': 0}
            for distance in range(1, self.max_distance + 1)
            for sign in (-1, 1)]

    def enable_action(self, a):
        return Or(*[And(*[a[k] == v for k, v in move.items()])
                    for move in self.menu()])
