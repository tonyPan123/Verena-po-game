"""RTT-no_buffer-jitter-converge benchmark."""
from z3 import *
from examples.game import Game

class CCAWithJitterGame(Game):
    def __init__(self, is_good=True):
        super().__init__()
        # Actions: guess value
        self.actions = {
            'guess': 'Real'
        }
        # Observable states: new_guess, old_guess, oldold_guess, and delayed answer
        self.observable_states = {
            'newguess': 'Real',
            'oldguess': 'Real',
            'oldoldguess': 'Real',  # Guess from two intervals ago
            'delayed_answer': 'Real',  # Answer from previous interval (observable)
        }
        # Latent states: secret number and current answer (not yet observable)
        self.latent_states = {
            'secret': 'Real',
            'current_answer': 'Real',  # Current answer (becomes delayed_answer next interval)
        }
        self.states = {**self.observable_states, **self.latent_states}
        self.is_good = is_good

    def initial(self, s):
        if self.is_good:
            return And(
                s['secret'] > 2,
                s['oldoldguess'] == 0,
                s['oldguess'] == 0,
                s['newguess'] == 1, 
                s['current_answer'] == 0,
                s['delayed_answer'] == 0  # No answer available initially
            )
        else:
            return And(
                s['secret'] > 2,
                s['oldoldguess'] == 0,
                s['oldguess'] == 0,
                s['newguess'] == 2, 
                s['current_answer'] == 0,
                s['delayed_answer'] == 0  # No answer available initially
            )

    def safety(self, s):
        # Safety: newguess is within bounds and greater than oldoldguess by one
        if self.is_good:
            return And(
                s['newguess'] <= s['secret'] + 1, 
                Or(
                    s['newguess'] >= s['secret'],  
                    s['newguess'] >= s['oldoldguess'] + 1,  # Changed from oldguess to oldoldguess
                ),
                #s['newguess'] >=  s['oldguess']
            )
        else:
            return And(
                s['newguess'] <= s['secret'], 
                Or(
                    s['newguess'] >= s['secret'],  
                    s['newguess'] >= s['oldoldguess'] + 1,  # Changed from oldguess to oldoldguess
                ),
                #s['newguess'] >=  s['oldguess']
            )

    def enable_action(self, a):
        # guess must be non-negative
        return BoolVal(True)

    def transition_env(self, s, s_p, a):
        return And(
            # Update newguess with the action
            s_p['newguess'] == a['guess'],
            # Old guess becomes the previous newguess
            s_p['oldguess'] == s['newguess'],
            # Oldold guess becomes the previous oldguess
            s_p['oldoldguess'] == s['oldguess'],
            # Secret remains unchanged
            s_p['secret'] == s['secret'], 
            
            # Delayed answer gets the previous current_answer (one interval delay)
            s_p['delayed_answer'] == s['current_answer'],
            
            # Current answer is computed based on current guess vs secret
            # But this won't be observable until next interval
            Or(
                And(
                    s_p['current_answer'] == 1,
                    a['guess'] >= s['secret']
                ),
                And(
                    s_p['current_answer'] == 0,
                    a['guess'] < s['secret']
                )
            )
        )
