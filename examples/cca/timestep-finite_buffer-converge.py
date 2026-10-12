"""timestep-finite_buffer-converge benchmark."""
from z3 import *
from examples.game import Game

class CCARealGame(Game):
    def __init__(self, not_easy=True):
        super().__init__()
        # Actions: guess value
        self.actions = {
            'send': 'Real'
        }
        # Observable states: new_guess and old_guess
        self.observable_states = {
            'cum_send': 'Real',
            'newsend': 'Real',
            'oldsend': 'Real', 
            'cum_ack': 'Real',
        }
        # Latent states: secret number
        self.latent_states = {
            'bandwidth': 'Real',
            "buffer": 'Real', 
            "queue": 'Real',
            'cum_loss': 'Real', 
        }
        self.states = {**self.observable_states, **self.latent_states}
        self.not_easy = not_easy

    def initial(self, s):
        return And(
            s['bandwidth'] >= 2,
            s['buffer'] >= 1,
            s['queue'] == 0,
            s['cum_send'] == 0,
            s['oldsend'] == 0,
            s['newsend'] == 2, 
            s['cum_loss'] == 0, 
            s['cum_ack'] == 0,
        )

    def safety(self, s):
        true_safety = s['cum_loss'] == 0
        if self.not_easy:
            true_safety = And(s['cum_loss'] == 0, Implies(s['newsend'] <= s['bandwidth'] - 1, s['newsend'] >= s['oldsend'] + 1))

        return And(true_safety, 
                s['bandwidth'] >= 2,
                s['buffer'] >= 1,
                s['queue'] >= 0,
                s['cum_send'] >= 0,
                s['oldsend'] >= 0,
                s['newsend'] >= 0, 
                s['cum_loss'] >= 0, 
                s['cum_ack'] >= 0,)

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
            s_p['cum_send'] == s_p['cum_ack'] + s_p['cum_loss'] + s_p['queue'],
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
            )
        )
