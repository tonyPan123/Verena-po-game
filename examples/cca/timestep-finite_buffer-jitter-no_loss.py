"""timestep-finite_buffer-jitter-no_loss benchmark."""
from fractions import Fraction
from z3 import *
from examples.game import Game

class CCARealJitterGame(Game):
    def __init__(self, not_easy=False, growth_interval=2, underutilization=1, min_utilization=None):
        super().__init__()
        if growth_interval not in (2, 3, 4):
            raise ValueError("growth_interval must be 2, 3, or 4")
        if underutilization <= 0:
            raise ValueError("underutilization must be positive")
        if min_utilization is not None and not 0 < Fraction(str(min_utilization)) <= 1:
            raise ValueError("min_utilization must be in (0, 1]")
        self.min_utilization = None if min_utilization is None else RealVal(str(min_utilization))
        self.underutilization = underutilization
        self.growth_interval = growth_interval
        # Actions: guess value
        self.actions = {
            'send': 'Real'
        }
        # Observable states: new_guess and old_guess
        self.observable_states = {
            'cum_send': 'Real',
            'newsend': 'Real',
            'oldsend': 'Real',
            'oldoldsend': 'Real',
            'cum_ack': 'Real',
        }
        if growth_interval >= 3:
            self.observable_states['older_send'] = 'Real'
        if growth_interval == 4:
            self.observable_states['oldest_send'] = 'Real'
        # Latent states: secret number
        self.latent_states = {
            'bandwidth': 'Real',
            "buffer": 'Real',
            "queue": 'Real',
            'cum_loss': 'Real',
            'ideal': 'Real',
        }
        self.states = {**self.observable_states, **self.latent_states}
        self.not_easy = not_easy

    def initial(self, s):
        return And(
            s['bandwidth'] >= 2,
            s['buffer'] >= 1,
            s['queue'] == 0,
            s['cum_send'] == 0,
            s['oldoldsend'] == 0,
            s['oldsend'] == 0,
            s['newsend'] == 2,
            s['cum_loss'] == 0,
            s['cum_ack'] == 0,
            s['ideal'] == 0,
            *([s['older_send'] == 0] if self.growth_interval >= 3 else []),
            *([s['oldest_send'] == 0] if self.growth_interval == 4 else []),
        )

    def safety(self, s):
        true_safety = s['cum_loss'] == 0
        if self.not_easy:
            past_send = s[{2: 'oldoldsend', 3: 'older_send', 4: 'oldest_send'}[self.growth_interval]]
            below_target = (s['newsend'] <= s['bandwidth'] - self.underutilization
                            if self.min_utilization is None else
                            s['newsend'] < self.min_utilization * s['bandwidth'])
            true_safety = And(s['cum_loss'] == 0, Implies(below_target, s['newsend'] >= past_send + 1))

        return And(true_safety,
                s['bandwidth'] >= 2,
                s['buffer'] >= 1,
                s['queue'] >= 0,
                s['cum_send'] >= 0,
                s['oldoldsend'] >= 0,
                s['oldsend'] >= 0,
                s['newsend'] >= 0,
                s['cum_loss'] >= 0,
                s['cum_ack'] >= 0,
                s['ideal'] >= 0,
            *([s['older_send'] >= 0] if self.growth_interval >= 3 else []),
            *([s['oldest_send'] >= 0] if self.growth_interval == 4 else []))

    def enable_action(self, a):
        # send must be non-negative
        return a['send'] >= 0

    def transition_env(self, s, s_p, a):
        # Environment keeps state unchanged (no environment transitions needed)
        # Compute loss_amount = max(0, queue + send - bandwidth - buffer)
        loss_amount = s['queue'] + a['send'] - s['bandwidth'] - s['buffer']
        # Compute queue_drain = max(0, queue + send - bandwidth - loss_amount)
        queue_next = s['queue'] + a['send'] - s['bandwidth']

        return And(
            s_p['cum_send'] == s['cum_send'] + a['send'],
            s_p['newsend'] == a['send'],
            s_p['oldsend'] == s['newsend'],
            s_p['oldoldsend'] == s['oldsend'],
            *([s_p['older_send'] == s['oldoldsend']] if self.growth_interval >= 3 else []),
            *([s_p['oldest_send'] == s['older_send']] if self.growth_interval == 4 else []),
            s_p['cum_send'] == s_p['ideal'] + s_p['cum_loss'] + s_p['queue'],
            # cum_loss increases by max(0, loss_amount)
            Or(
                And(s_p['cum_loss'] == s['cum_loss'] + loss_amount, loss_amount >= 0),
                And(s_p['cum_loss'] == s['cum_loss'], loss_amount < 0)
            ),
            s_p['bandwidth'] == s['bandwidth'],
            s_p['buffer'] == s['buffer'],
            # queue = max(0, queue + send - bandwidth - loss_amount)
            Or(
                And(s_p['queue'] == s['buffer'], loss_amount > 0),
                And(s_p['queue'] == queue_next, queue_next >= 0, loss_amount <= 0),
                And(s_p['queue'] == 0, queue_next < 0)
            ),
            And(s_p['cum_ack'] <= s_p['ideal'], s_p['cum_ack'] >= s['ideal'])
        )
