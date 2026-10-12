from z3 import *
from examples.game import Game

class BakeryGame(Game):
    """Two-process Bakery game with a hidden scheduler.

    pc1 and both tickets are observable; pc0, sched, steps, and ask are latent.
    The controller chooses x_u and x_g.
    """

    def __init__(self):
        super().__init__()
        # System actions/outputs
        self.actions = {
            'x_u': 'Real',
            'x_g': 'Real'
        }
        # Observable states
        self.observable_states = {
            'pc1': 'Real',      # process 1 program counter (observable)
            'ticket0': 'Real',  # ticket for process 0
            'ticket1': 'Real',  # ticket for process 1
        }
        # Latent states
        self.latent_states = {
            'pc0': 'Real',      # process 0 program counter (hidden)
            'sched': 'Real',    # scheduler
            'steps': 'Real',    # step counter
            'ask': 'Real',      # ask flag
        }
        self.states = {**self.observable_states, **self.latent_states}

    def initial(self, s):
        """Initialize all state variables to zero."""
        return And(
            s['pc0'] == 0,
            s['pc1'] == 0,
            s['ticket0'] == 0,
            s['ticket1'] == 0,
            s['sched'] == 0,
            s['steps'] == 0,
            s['ask'] == 0
        )

    def safety(self, s):
        """Require mutual exclusion and either steps < 2 or ask == 0."""
        safe = And(
                Or(Not(s['pc0'] == 2,), Not(s['pc1'] == 2)),
                Or(s['steps'] < 2, s['ask'] == 0)
        )
        return safe

    def enable_action(self, a):
        """Allow x_u in {1, 2, 3} and x_g in {1, 2}."""
        return And(
            Or(a['x_u'] == 1, a['x_u'] == 2, a['x_u'] == 3),
            Or(a['x_g'] == 1, a['x_g'] == 2)
        )

    def transition_env(self, s, s_p, a):
        """Combine the scheduled process transitions and observation requests."""
        # Helper for preserving variables
        def preserve(s, s_p, vars_to_preserve):
            return And(*[s_p[var] == s[var] for var in vars_to_preserve])

        # ============ PROCESS 0 TRANSITIONS ============

        # TRANS ENV {0}: pc0 = 0 -> pc0 = 1, ticket0 = ticket1 + 1
        env_p0_trans_0 = And(
            s['sched'] == 0,
            s['pc0'] == 0,
            s_p['pc0'] == 1,
            s_p['ticket0'] == s['ticket1'] + 1,
            s_p['steps'] == s['steps'] + 1,
            s_p['ask'] == 0,
            preserve(s, s_p, ['pc1', 'ticket1'])
        )

        # TRANS ENV {0}: pc0 = 1 & (ticket1 = 0 | ticket0 < ticket1) -> pc0 = 2
        env_p0_trans_1_enter = And(
            s['sched'] == 0,
            s['pc0'] == 1,
            Or(s['ticket1'] == 0, s['ticket0'] < s['ticket1']),
            s_p['pc0'] == 2,
            s_p['steps'] == s['steps'] + 1,
            s_p['ask'] == 0,
            preserve(s, s_p, ['pc1', 'ticket1', 'ticket0'])
        )

        # TRANS ENV {0}: pc0 = 1 & ticket1 > 0 & ticket0 >= ticket1 -> stay at pc0 = 1
        env_p0_trans_1_wait = And(
            s['sched'] == 0,
            s['pc0'] == 1,
            s['ticket1'] > 0,
            s['ticket0'] >= s['ticket1'],
            s_p['pc0'] == 1,
            s_p['steps'] == s['steps'] + 1,
            s_p['ask'] == 0,
            preserve(s, s_p, ['pc1', 'ticket1', 'ticket0'])
        )

        # TRANS ENV {0}: pc0 = 2 -> pc0 = 0, ticket0 = 0 (exit critical section)
        env_p0_trans_2 = And(
            s['sched'] == 0,
            s['pc0'] == 2,
            s_p['pc0'] == 0,
            s_p['ticket0'] == 0,
            s_p['steps'] == s['steps'] + 1,
            s_p['ask'] == 0,
            preserve(s, s_p, ['pc1', 'ticket1'])
        )

        # ============ PROCESS 1 TRANSITIONS ============

        # TRANS ENV {1}: pc1 = 0 & x_u = 1 -> pc1 = 1, ticket1 = 0
        env_p1_trans_0_xu1 = And(
            s['sched'] == 1,
            s['pc1'] == 0,
            Or(And(s['ticket1'] == 0, a['x_u'] == 1),
               And(s_p['ticket1'] == s['ticket0'], a['x_u'] == 2),
               And(s_p['ticket1'] == s['ticket0'] + 1, a['x_u'] == 3)
               ),
            s_p['pc1'] == 1,
            s_p['ask'] == 0,
            preserve(s, s_p, ['pc0', 'ticket0', 'steps'])
        )


        # TRANS ENV {1}: pc1 = 1 & x_g = 0 -> t = 1, ask = 1, steps = 0 (ask system for x_g)
        env_p1_trans_1_ask = And(
            s['sched'] == 1,
            s['pc1'] == 1,
            s_p['ask'] == 1,
            s_p['steps'] == 0,
            preserve(s, s_p, [ 'pc0', 'ticket0', 'pc1', 'ticket1'])
        )

        # TRANS ENV {1}: pc1 = 1 & x_g = 1 -> pc1 = 2 (enter critical section)
        env_p1_trans_1_xg1 = And(
            s['sched'] == 1,
            s['pc1'] == 1,
            a['x_g'] == 1,
            s_p['pc1'] == 2,
            s_p['ask'] == 0,
            preserve(s, s_p, ['pc0', 'ticket0', 'steps', 'ticket1'])
        )

        # TRANS ENV {1}: pc1 = 1 & x_g = 2 -> t = 1, ask = 1 (ask again)
        env_p1_trans_1_xg2 = And(
            s['sched'] == 1,
            s['pc1'] == 1,
            a['x_g'] == 2,
            s_p['ask'] == 1,
            preserve(s, s_p, ['pc0', 'ticket0', 'steps', 'pc1', 'ticket1'])
        )

        # TRANS ENV {1}: pc0 = 2 -> pc1 = 0, ticket1 = 0, x_u = 0, x_g = 0 (reset after p0 exits)
        # Note: This seems to be when process 1 observes process 0 exiting
        env_p1_trans_reset = And(
            s['sched'] == 1,
            s['pc0'] == 2,
            s_p['pc1'] == 0,
            s_p['ticket1'] == 0,
            s_p['ask'] == 0,
            preserve(s, s_p, ['pc0', 'ticket0', 'steps',])
        )

        # ============ SCHEDULER SWITCH TRANSITIONS ============

        switch = Or(And(s['sched'] == 0, s_p['sched'] == 1),
                     And(s['sched'] == 1, s_p['sched'] == 0))

        # Combine all transitions
        T_forall = And(
            Or(
                # Process 0 transitions
                env_p0_trans_0,
                env_p0_trans_1_enter,
                env_p0_trans_1_wait,
                env_p0_trans_2,
                # Process 1 transitions
                env_p1_trans_0_xu1,
                env_p1_trans_1_ask,
                env_p1_trans_1_xg1,
                env_p1_trans_1_xg2,
                env_p1_trans_reset,
                # Scheduler switches
            ),
            switch)

        return T_forall


"""Scale the pasted Bakery ticket menu without changing its state semantics.

N+4 tagged commands: original unprimed-zero guard, equal ticket, positive
increments 1..N, enter, wait. Wrong-location commands explicitly lose.
"""
from z3 import And, Or, Not, Real, RealVal, substitute



class BakeryPastedFiniteGame(BakeryGame):
    def __init__(self, max_offset=4):
        if type(max_offset) is not int or max_offset < 1:
            raise ValueError('max_offset must be a positive integer')
        super().__init__()
        self.max_offset = max_offset
        self.actions = {'command': 'Real'}

    def menu(self):
        return [{'command': i} for i in range(self.max_offset + 4)]

    def enable_action(self, a):
        return Or(*[a['command'] == m['command'] for m in self.menu()])

    def transition_env(self, s, sp, a):
        command = a['command']
        xu, xg = Real('__pasted_xu'), Real('__pasted_xg')
        original = super().transition_env(s, sp, {'x_u': xu, 'x_g': xg})
        ticket = Or(And(s['ticket1'] == 0, xu == 1),
                    And(sp['ticket1'] == s['ticket0'], xu == 2),
                    And(sp['ticket1'] == s['ticket0'] + 1, xu == 3))
        replacement = Or(And(command == 0, s['ticket1'] == 0),
                         And(command == 1, sp['ticket1'] == s['ticket0']),
                         And(command >= 2, command <= self.max_offset + 1,
                             sp['ticket1'] == s['ticket0'] + command - 1))
        normal = substitute(original, (ticket, replacement))
        normal = Or(And(command == self.max_offset + 2, substitute(normal, (xg, RealVal(1)))),
                    And(command != self.max_offset + 2, substitute(normal, (xg, RealVal(2)))))
        invalid = And(s['sched'] == 1,
                      Or(And(s['pc1'] == 0, command > self.max_offset + 1),
                         And(s['pc1'] == 1, command <= self.max_offset + 1)))
        failure = And(sp['pc0'] == 2, sp['pc1'] == 2,
                      *[sp[k] == s[k] for k in self.states if k not in ('pc0', 'pc1')])
        return Or(And(Not(invalid), normal), And(invalid, failure))
