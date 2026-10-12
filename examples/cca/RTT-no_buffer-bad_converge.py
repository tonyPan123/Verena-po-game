"""RTT-no_buffer-bad_converge benchmark."""
from z3 import *
from examples.game import Game

class GuessNumberGame(Game):
    def __init__(self, is_good=False):
        super().__init__()
        # Actions: guess value
        self.actions = {
            'guess': 'Real'
        }
        # Observable states: new_guess and old_guess
        self.observable_states = {
            'newguess': 'Real',
            'oldguess': 'Real',
            'answer': 'Real',
        }
        # Latent states: secret number
        self.latent_states = {
            'secret': 'Real'
        }
        self.states = {**self.observable_states, **self.latent_states}
        self.is_good = is_good

    def initial(self, s):
        return And(
            s['secret'] >= 2,
            #s['secret'] <= 6,
            s['oldguess'] == 0,
            s['newguess'] == 1,
            s['answer'] == 0
        )

    def safety(self, s):
        # Safety: either new_guess is within secret + 1 OR new_guess >= old_guess + 1
        if self.is_good:
            return And(s['newguess'] <= s['secret'] + 1,
                    Or(
                        s['newguess'] >= s['secret'],
                        s['newguess'] >= s['oldguess'] + 1,
                        ),
                        s['newguess'] >= 0,
                        s['oldguess'] >= 0
                    )
        else:
            return And(s['newguess'] <= s['secret'],
                    Or(
                        s['newguess'] >= s['secret'],
                        s['newguess'] >= s['oldguess'] + 1,
                        ),
                        s['newguess'] >= 0,
                        s['oldguess'] >= 0
                    )

    def enable_action(self, a):
        # guess must be non-negative
        return BoolVal(True)

    def transition_env(self, s, s_p, a):
        # Environment keeps state unchanged (no environment transitions needed)
        return And(
            # Update newguess with the action
            s_p['newguess'] == a['guess'],
            # Old guess becomes the previous newguess
            s_p['oldguess'] == s['newguess'],
            # Secret remains unchanged by controller
            s_p['secret'] == s['secret'],
            Or(And(
                s_p['answer'] == 1,
                a['guess'] >= s['secret']),
               And(
                s_p['answer'] == 0,
                a['guess'] < s['secret']
               )
            )
        )
