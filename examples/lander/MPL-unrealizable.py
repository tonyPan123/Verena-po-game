"""MPL game with alternating environment and controller steps.

Benchmark parameters are listed in artifact/benchmarks/lander.json.
"""
from z3 import And, Or, Implies, simplify
from examples.game import Game


class MPLPaperGame(Game):
    def __init__(self, exponential=False, max_error=0, initial_altitude=39):
        super().__init__()
        if max_error != 0:
            raise ValueError('max_error must be 0 for the MPL benchmark')
        self.exponential = exponential
        self.max_error = max_error
        self.ground = -1 if exponential else 0
        self.start = 4 if exponential else 8000
        if initial_altitude is not None:
            if type(initial_altitude) is not int or not self.ground < initial_altitude <= self.start:
                raise ValueError('initial_altitude must be an airborne integer within the original altitude range')
            self.start = initial_altitude
        # Exponential altitude/radar ranks already range over integers. Keep
        # their domains as bounds so mining can generalize altitude intervals.
        numeric = 'Int'
        self.actions = {'shutdown': 'Real'}
        self.observable_states = {'phase': 'Real', 'engine_on': 'Real',
                                  'radar': numeric, 'touchdown_1': 'Real',
                                  'touchdown_2': 'Real'}
        self.latent_states = {'altitude': numeric, 'ground_age': 'Real',
                             'transient_on_ground': 'Real'}
        # A single mode per sensor: -1 healthy, 0 stuck low, 1 stuck high.
        for i in (1, 2):
            self.latent_states.update({f'fault_{i}': 'Real', f'error_run_{i}': 'Real'})
        self.states = {**self.observable_states, **self.latent_states}

    @staticmethod
    def enum(value, values):
        return Or(*[value == v for v in values])

    def _normalize(self, formula):
        return simplify(formula) if self.exponential else formula

    def domain(self, s):
        finite = [self.enum(s[k], (0, 1)) for k in
                  ('phase', 'engine_on', 'transient_on_ground', 'touchdown_1',
                   'touchdown_2')]
        finite += [self.enum(s[f'fault_{i}'], (-1, 0, 1)) for i in (1, 2)]
        finite += [self.enum(s[f'error_run_{i}'], range(self.max_error+1)) for i in (1, 2)]
        altitude = (And(s['altitude'] >= -1, s['altitude'] <= 4) if self.exponential else
                    And(s['altitude'] >= 0, s['altitude'] <= 8000))
        radar = (And(s['radar'] >= -1, s['radar'] <= 5) if self.exponential else
                 And(s['radar'] >= -38, s['radar'] <= 8038))
        return And(*finite, altitude, radar, self.enum(s['ground_age'], (0, 1, 2)),
                   Or(s['fault_1'] == -1, s['fault_2'] == -1))

    def initial(self, s):
        return self._normalize(And(self.domain(s), s['phase'] == 0, s['engine_on'] == 1,
                   s['altitude'] == self.start, s['radar'] == self.start,
                   s['touchdown_1'] == 0, s['touchdown_2'] == 0,
                   s['error_run_1'] == 0, s['error_run_2'] == 0,
                   s['ground_age'] == 0, s['transient_on_ground'] == 0))

    def safety(self, s):
        # Check safety at phase 0, after the controller step.
        invariant = And(Implies(s['altitude'] > self.ground, s['engine_on'] == 1),
                        Implies(s['transient_on_ground'] == 0, s['ground_age'] < 2))
        return self._normalize(And(self.domain(s), Implies(s['phase'] == 0, invariant)))

    def enable_action(self, a):
        return self.enum(a['shutdown'], (0, 1))

    def transition_env(self, s, sp, a):
        # Phase 0: automatic environment step; action deliberately ignored.
        # Phase 1: controller observes the new readings and chooses shutdown.
        same = lambda except_keys: And(*[sp[k] == s[k] for k in self.states if k not in except_keys])
        stopped = And(s['engine_on'] == 0, same(set()))
        control = And(s['engine_on'] == 1, s['phase'] == 1, sp['phase'] == 0,
                      sp['engine_on'] == 1-a['shutdown'], same({'phase', 'engine_on'}))
        if self.exponential:
            # At ranks 3 and 4, descent is at most one rank per environment step.
            descent = And(sp['altitude'] >= -1, sp['altitude'] <= s['altitude'],
                          Implies(s['altitude'] >= 3,
                                  sp['altitude'] >= s['altitude']-1))
            radar = Or(And(sp['altitude'] >= 3, sp['radar'] >= sp['altitude']-1, sp['radar'] <= sp['altitude']+1),
                       And(sp['altitude'] == 2, sp['radar'] >= -1, sp['radar'] <= 3),
                       And(sp['altitude'] < 2, sp['radar'] >= -1, sp['radar'] <= 2))
            deployment = sp['altitude'] == 4
        else:
            descent = And(sp['altitude'] >= 0, sp['altitude'] <= s['altitude'], sp['altitude'] >= s['altitude']-39)
            radar = And(sp['radar'] >= sp['altitude']-38, sp['radar'] <= sp['altitude']+38)
            deployment = And(sp['altitude'] >= 1400, sp['altitude'] <= 1600)
        landed = sp['altitude'] == self.ground
        faults = []
        for i in (1, 2):
            run, next_run = s[f'error_run_{i}'], sp[f'error_run_{i}']
            fault, reading = s[f'fault_{i}'], sp[f'touchdown_{i}']
            faults += [sp[f'fault_{i}'] == fault,
                       Or(next_run == 0, And(run < self.max_error, next_run == run+1)),
                       Or(And(fault == 0, reading == 0), And(fault == 1, reading == 1),
                          And(fault == -1, Or(deployment, next_run > 0,
                              And(landed, reading == 1), And(sp['altitude'] > self.ground, reading == 0))))]
        transient = Or(s['transient_on_ground'] == 1,
                       And(landed, Or(sp['error_run_1'] > 0, sp['error_run_2'] > 0)))
        flag = Or(And(transient, sp['transient_on_ground'] == 1),
                  And(s['transient_on_ground'] == 0,
                      Or(sp['altitude'] > self.ground, And(sp['error_run_1'] == 0, sp['error_run_2'] == 0)),
                      sp['transient_on_ground'] == 0))
        timer = Or(And(s['altitude'] > self.ground, sp['ground_age'] == s['ground_age']),
                   And(s['altitude'] == self.ground, s['ground_age'] < 2, sp['ground_age'] == s['ground_age']+1),
                   And(s['altitude'] == self.ground, s['ground_age'] == 2, sp['ground_age'] == 2))
        environment = And(s['engine_on'] == 1, s['phase'] == 0, sp['phase'] == 1,
                          sp['engine_on'] == 1, self.domain(sp), descent, radar, *faults, flag, timer)
        return self._normalize(Or(stopped, control, environment))
