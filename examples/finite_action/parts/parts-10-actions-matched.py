from z3 import *
from examples.game import Game

class ProductionSystemGame(Game):
    def __init__(self):
        super().__init__()
        self.actions = {
            'box': 'Int'
        }
        self.observable_states = {
            'size': 'Int',
            'weight_o': 'Int',
            'loc': 'Int'
        }
        self.latent_states = {
            'type': 'Int',
            'weight': 'Int',
        }
        self.states = {**self.observable_states, **self.latent_states}

    def initial(self, s):
        return And(
            s['type'] == 0,
            s['weight'] == 0,
            s['size'] == 0,
            s['weight_o'] == 0,
            s['loc'] == 0
        )

    def safety(self, s):
        return Not(s['loc'] == 4)

    def enable_action(self, a):
        return Or(a['box'] == 0, a['box'] == 1)

    def transition_env(self, s, s_p, a):
        # Helper for preserving variables
        def preserve(s, s_p, vars_to_preserve):
            return And(*[s_p[var] == s[var] for var in vars_to_preserve])

        def BiImplies(expr1, expr2):
            return And(Implies(expr1, expr2), Implies(expr2, expr1))

        # φ0: Initial box generation
        phi_0 = And(
            s['loc'] == 0,
            s_p['loc'] == 1,
            preserve(s, s_p, ['size', 'weight_o']),
            Or(
                And(s_p['type'] == 0, s_p['weight'] >= 1, s_p['weight'] <= 5),
                And(s_p['type'] == 1, s_p['weight'] >= 4, s_p['weight'] <= 10)
            )
        )

        # φ1: Size determination
        phi_1 = And(
            s['loc'] == 1,
            s_p['loc'] == 2,
            preserve(s, s_p, ['type', 'weight', 'weight_o']),
            Or(
                And(s_p['size'] == 1,
                    Or(And(s['type'] == 0, s['weight'] <= 2),
                       And(s['type'] == 1, s['weight'] <= 7))),
                And(s_p['size'] == 2,
                    Or(And(s['type'] == 0, s['weight'] > 2),
                       And(s['type'] == 1, s['weight'] > 7)))
            )
        )

        # φ2: Weight observation
        phi_2 = And(
            s['loc'] == 2,
            s_p['loc'] == 3,
            s_p['size'] == 0,
            preserve(s, s_p, ['type', 'weight']),
            BiImplies(s_p['weight_o'] < 3, s['weight'] < 3),
            BiImplies(And(s_p['weight_o'] >= 3, s_p['weight_o'] < 6), And(s['weight'] >= 3, s['weight'] < 6))
        )

        # φ3': Correct box type
        phi_3_prime = And(
            s['loc'] == 3,
            s['type'] == a['box'],
            s_p['loc'] == 0,
            s_p['type'] == 0,
            s_p['weight'] == 0,
            s_p['size'] == 0,
            s_p['weight_o'] == 0
        )

        # φ3'': Wrong box type
        phi_3_double_prime = And(
            s['loc'] == 3,
            s['type'] != a['box'],
            s_p['loc'] == 4,
            preserve(s, s_p, ['type', 'weight', 'size', 'weight_o'])
        )

        # φ4: Error state
        phi_4 = And(
            s['loc'] == 4,
            preserve(s, s_p, ['loc', 'type', 'weight', 'size', 'weight_o'])
        )

        # Complete environment transition
        T_forall = Or(phi_0, phi_1, phi_2, phi_3_prime, phi_3_double_prime, phi_4)

        return T_forall


class ProductionSystemScaleGame(Game):
    def __init__(self, scale=9):
        super().__init__()
        self.actions = {
            'box': 'Int'
        }
        self.observable_states = {
            'size': 'Int',
            'weight_o': 'Int',
            'loc': 'Int'
        }
        self.latent_states = {
            'type': 'Int',
            'weight': 'Int',
        }
        self.states = {**self.observable_states, **self.latent_states}
        self.scale = scale

    def initial(self, s):
        return And(
            s['type'] == 0,
            s['weight'] == 0,
            s['size'] == 0,
            s['weight_o'] == 0,
            s['loc'] == 0
        )

    def safety(self, s):
        return Not(s['loc'] == 4)

    def enable_action(self, a):
        return And(a['box'] >= 0, a['box'] <= self.scale)

    def transition_env(self, s, s_p, a):
        # Helper for preserving variables
        def preserve(s, s_p, vars_to_preserve):
            return And(*[s_p[var] == s[var] for var in vars_to_preserve])

        def BiImplies(expr1, expr2):
            return And(Implies(expr1, expr2), Implies(expr2, expr1))

        # φ0: Initial box generation
        phi_0 = And(
            s['loc'] == 0,
            s_p['loc'] == 1,
            preserve(s, s_p, ['size', 'weight_o']),
            Or(
                And(s_p['type'] == 0, s_p['weight'] >= 1, s_p['weight'] <= 5),
                And(s_p['type'] == 1, s_p['weight'] >= 4, s_p['weight'] <= 10)
            )
        )

        # φ1: Size determination
        phi_1 = And(
            s['loc'] == 1,
            s_p['loc'] == 2,
            preserve(s, s_p, ['type', 'weight', 'weight_o']),
            Or(
                And(s_p['size'] == 1,
                    Or(And(s['type'] == 0, s['weight'] <= 2),
                       And(s['type'] == 1, s['weight'] <= 7))),
                And(s_p['size'] == 2,
                    Or(And(s['type'] == 0, s['weight'] > 2),
                       And(s['type'] == 1, s['weight'] > 7)))
            )
        )

        # φ2: Weight observation
        phi_2 = And(
            s['loc'] == 2,
            s_p['loc'] == 3,
            s_p['size'] == 0,
            preserve(s, s_p, ['type', 'weight']),
            BiImplies(s_p['weight_o'] < 3, s['weight'] < 3),
            BiImplies(And(s_p['weight_o'] >= 3, s_p['weight_o'] < 6), And(s['weight'] >= 3, s['weight'] < 6))
        )

        # φ3': Correct box type
        phi_3_prime = And(
            s['loc'] == 3,
            s['type'] == a['box'],
            s_p['loc'] == 0,
            s_p['type'] == 0,
            s_p['weight'] == 0,
            s_p['size'] == 0,
            s_p['weight_o'] == 0
        )

        # φ3'': Wrong box type
        phi_3_double_prime = And(
            s['loc'] == 3,
            s['type'] != a['box'],
            s_p['loc'] == 4,
            preserve(s, s_p, ['type', 'weight', 'size', 'weight_o'])
        )

        # φ4: Error state
        phi_4 = And(
            s['loc'] == 4,
            preserve(s, s_p, ['loc', 'type', 'weight', 'size', 'weight_o'])
        )

        # Complete environment transition
        T_forall = Or(phi_0, phi_1, phi_2, phi_3_prime, phi_3_double_prime, phi_4)

        return T_forall
