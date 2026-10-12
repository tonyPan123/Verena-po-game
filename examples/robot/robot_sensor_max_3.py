from z3 import *
from examples.game import Game

class RobotSensorGame(Game):
    def __init__(self, continuous_vertical=True, max_distance=3):
        super().__init__()
        self.continuous_vertical = continuous_vertical
        if max_distance is not None and max_distance < 0:
            raise ValueError("max_distance must be nonnegative")
        self.max_distance = max_distance
        self.actions = {
            'direction': 'Real',
            'distance': 'Real'
        }
        self.observable_states = {
            'x': 'Real',
            'ys': 'Real',
            'yn': 'Real'
        }
        self.latent_states = {
            'y': 'Real',
            'steps': 'Real',
            'err': 'Bool',
            'sense': 'Bool'
        }
        self.states = {**self.observable_states, **self.latent_states}

    # Define the initial state
    def initial(self, s):
        return And(
            s['x'] == 4,
            s['y'] == 3,
            s['steps'] == 0,
            Not(s['err']),
            s['ys'] == 3,
            s['yn'] == 3,
            s['sense']
        )

    def safety(self, s):
        #return Not(Or(
            #s['steps'] < 0,
        #    s['err'],
        #    And(s['steps'] > 2, s['x'] < 6),
        #    s['x'] >= 9,
        #    s['x'] <= -1,
        #    s['y'] >= 4,
        #    s['y'] <= -4
        #))
        return And(
            Not(s['err']),
            Or(s['steps'] <= 2, s['x'] >= 6),
            s['x'] < 9,
            s['x'] > -1,
            s['y'] < 4,
            s['y'] > -4
        )

    def enable_action(self, a):
        return And(
            Or(a['direction'] == 1, a['direction'] == 2,
               a['direction'] == 3, a['direction'] == 4),
            a['distance'] >= 0,
            True if self.max_distance is None else a['distance'] <= self.max_distance,
        )

    # Define the transition relation for the environment
    def transition_env(self, s, s_p, a):
        step = a['distance'] if self.continuous_vertical else 1
        upper_step = step + RealVal('0.5')
        # φ_N
        phi_N = And(
            a['direction'] == 1,
            s_p['y'] >= s['y'] + step, s_p['y'] <= s['y'] + upper_step,
            s_p['x'] == s['x'],
            Or(
                And(Not(s['sense']), s_p['ys'] == s['y'] + step, s_p['yn'] == s['y'] + upper_step, s_p['sense']),
                And(s['sense'], s_p['ys'] == s_p['y'], s_p['yn'] == s_p['y'], Not(s_p['sense']))
            )
        )

        # φ_S
        phi_S = And(
            a['direction'] == 2,
            s_p['y'] >= s['y'] - upper_step, s_p['y'] <= s['y'] - step,
            s_p['x'] == s['x'],
            Or(
                And(Not(s['sense']), s_p['ys'] == s['y'] - upper_step, s_p['yn'] == s['y'] - step, s_p['sense']),
                And(s['sense'], s_p['ys'] == s_p['y'], s_p['yn'] == s_p['y'], Not(s_p['sense']))
            )
        )

        # φ_E
        phi_E = And(
            a['direction'] == 3,
            s_p['x'] == s['x'] + a['distance'], s_p['y'] == s['y'],
            s_p['ys'] == s['ys'], s_p['yn'] == s['yn'],
            s_p['sense'] == s['sense']
        )

        # φ_W
        phi_W = And(
            a['direction'] == 4,
            s_p['x'] == s['x'] - a['distance'], s_p['y'] == s['y'],
            s_p['ys'] == s['ys'], s_p['yn'] == s['yn'],
            s_p['sense'] == s['sense']
        )

        # Define phi_bad helper
        def phi_bad(s, s_p):
            return Or(
                And(
                    Or(And(s['x'] < 5, s_p['x'] >= 5),
                        And(s['x'] > 5, s_p['x'] <= 5)),
                    Or(s['y'] <= 0, s['y'] >= 2)
                ),
                And(s['x'] > 5, s_p['x'] <= 5)
            )

        # Transition formula T_∀
        T_forall = And(
            Or(phi_N, phi_S, phi_E, phi_W),
            s_p['steps'] == s['steps'] + 1,
            Or(
                And(phi_bad(s, s_p), s_p['err']),
                And(Not(phi_bad(s, s_p)), s_p['err'] == s['err'])
            )
        )
        return T_forall


class RobotSensorDiscretizeGame(Game):
    def __init__(self, max_distance=5):
        super().__init__()
        self.max_distance = max_distance
        self.actions = {
            'direction': 'Real',
            'distance': 'Real'
        }
        self.observable_states = {
            'x': 'Real',
            'ys': 'Real',
            'yn': 'Real'
        }
        self.latent_states = {
            'y': 'Real',
            'steps': 'Real',
            'err': 'Bool',
            'sense': 'Bool'
        }
        self.states = {**self.observable_states, **self.latent_states}

    # Define the initial state
    def initial(self, s):
        return And(
            s['x'] == 4,
            s['y'] == 3,
            s['steps'] == 0,
            Not(s['err']),
            s['ys'] == 3,
            s['yn'] == 3,
            s['sense']
        )

    def safety(self, s):
        return And(
            Not(s['err']),
            Or(s['steps'] <= 2, s['x'] >= 6),
            s['x'] < 9,
            s['x'] > -1,
            s['y'] < 4,
            s['y'] > -4
        )

    def enable_action(self, a):
        # Create Or constraint for distance values from 0 to max_distance
        #distance_constraint = Or([a['distance'] == i for i in range(4, self.max_distance + 2)])
        #direction_constraint = Or([a['direction'] == i for i in range(5, self.max_distance + 1)])
        #distance_constraint = Or([a['distance'] == i for i in range(4, self.max_distance)])
        return And(
            Or(a['direction'] == 1, a['direction'] == 2, a['direction'] == 3, a['direction'] == 4),
            And(a['distance'] >= 0, a['distance'] <= self.max_distance),
            #Or(a['distance'] == 0, distance_constraint)
        )

    # Define the transition relation for the environment
    def transition_env(self, s, s_p, a):
        # φ_N
        phi_N = And(
            a['direction'] == 1,
            s_p['y'] >= s['y'] + 1, s_p['y'] <= s['y'] + 1.5,
            s_p['x'] == s['x'],
            Or(
                And(Not(s['sense']), s_p['ys'] == s['y'] + 1, s_p['yn'] == s['y'] + 1.5, s_p['sense']),
                And(s['sense'], s_p['ys'] == s_p['y'], s_p['yn'] == s_p['y'], Not(s_p['sense']))
            )
        )

        # φ_S
        phi_S = And(
            a['direction'] == 2,
            s_p['y'] >= s['y'] - 1.5, s_p['y'] <= s['y'] - 1,
            s_p['x'] == s['x'],
            Or(
                And(Not(s['sense']), s_p['ys'] == s['y'] - 1.5, s_p['yn'] == s['y'] - 1, s_p['sense']),
                And(s['sense'], s_p['ys'] == s_p['y'], s_p['yn'] == s_p['y'], Not(s_p['sense']))
            )
        )

        # φ_E
        phi_E = And(
            a['direction'] == 3,
            s_p['x'] == s['x'] + a['distance'], s_p['y'] == s['y'],
            s_p['ys'] == s['ys'], s_p['yn'] == s['yn'],
            s_p['sense'] == s['sense']
        )

        # φ_W
        phi_W = And(
            a['direction'] == 4,
            s_p['x'] == s['x'] - a['distance'], s_p['y'] == s['y'],
            s_p['ys'] == s['ys'], s_p['yn'] == s['yn'],
            s_p['sense'] == s['sense']
        )

        phi_extra = And(
            a['direction'] > 4,
            s_p['x'] == s['x'],
            s_p['y'] == s['y'],
            s_p['ys'] == s['ys'],
            s_p['yn'] == s['yn'],
            s_p['sense'] == s['sense']
        )

        # Define phi_bad helper
        def phi_bad(s, s_p):
            return Or(
                And(
                    Or(And(s['x'] < 5, s_p['x'] >= 5),
                        And(s['x'] > 5, s_p['x'] <= 5)),
                    Or(s['y'] <= 0, s['y'] >= 2)
                ),
                And(s['x'] > 5, s_p['x'] <= 5)
            )

        # Transition formula T_∀
        T_forall = And(
            Or(phi_N, phi_S, phi_E, phi_W, phi_extra),
            s_p['steps'] == s['steps'] + 1,
            Or(
                And(phi_bad(s, s_p), s_p['err']),
                And(Not(phi_bad(s, s_p)), s_p['err'] == s['err'])
            )
        )
        return T_forall
