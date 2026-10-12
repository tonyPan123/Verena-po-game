"""RTT-finite_buffer-bad_converge benchmark."""
from z3 import *
from examples.game import Game

class CCAWaitGame(Game):
    def __init__(self, is_good=False):
        super().__init__()
        # Actions: guess value
        self.actions = {
            'guess': 'Real'
        }
        # Observable states: new_guess and old_guess
        self.observable_states = {
            'newsend': 'Real',
            'oldsend': 'Real',
            'loss': 'Real',
        }
        # Latent states: secret number
        self.latent_states = {
            'bandwidth': 'Real',
            'buffer': 'Real'
        }
        self.states = {**self.observable_states, **self.latent_states}
        self.is_good = is_good

    def initial(self, s):
        return And(
            s['bandwidth'] >= 2,
            s['buffer'] >= 2,
            s['oldsend'] == 0,
            s['newsend'] == 1,
            s['loss'] == 0
        )

    def safety(self, s):
        # Safety: either new_guess is within secret + 1 OR new_guess >= old_guess + 1
        if self.is_good:
            return And(s['newsend'] <= s['bandwidth'] + s['buffer'] + 1,
                    Or(
                        s['newsend'] >= s['bandwidth'] + s['buffer'],
                        s['newsend'] >= s['oldsend'] + 1,
                        ),
                        s['newsend'] >= 0,
                        s['oldsend'] >= 0
                    )
        else:
            return And(s['newsend'] <= s['bandwidth'] + s['buffer'],
                    Or(
                        s['newsend'] >= s['bandwidth'] + s['buffer'],
                        s['newsend'] >= s['oldsend'] + 1,
                        ),
                        s['newsend'] >= 0,
                        s['oldsend'] >= 0
                    )

    def enable_action(self, a):
        # guess must be non-negative
        return BoolVal(True)

    def transition_env(self, s, s_p, a):
        # Environment keeps state unchanged (no environment transitions needed)
        return And(
            # Update newsend with the action
            s_p['newsend'] == a['guess'],
            # Old send becomes the previous newsend
            s_p['oldsend'] == s['newsend'],
            # Bandwidth remains unchanged by controller
            s_p['bandwidth'] == s['bandwidth'],
            # Buffer remains unchanged by controller
            s_p['buffer'] == s['buffer'],
            Or(And(
                s_p['loss'] == 1,
                a['guess'] >= s['bandwidth'] + s['buffer']),
               And(
                s_p['loss'] == 0,
                a['guess'] < s['bandwidth'] + s['buffer']
               )
            )
        )
