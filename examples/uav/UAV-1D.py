from z3 import *
from examples.game import Game

class AltitudeGame(Game):
    def __init__(self):
        super().__init__()
        self.actions = {
            'cmd': 'Real'
        }
        self.observable_states = {
            'obs': 'Real'
            #'cmd_last': 'Int'
        }
        self.latent_states = {
            'alt': 'Real'
        }
        self.states = {**self.observable_states, **self.latent_states}

    def initial(self, s):
        return s['alt'] == 500

    def safety(self, s):
        return And(s['alt'] >= 450, s['alt'] <= 550)

    def enable_action(self, a):
        #return Or(a['cmd'] == 0, a['cmd'] == 25, a['cmd'] == -25)
        return BoolVal(True)

    def transition_env(self, s, s_p, a):
        return And(
            s['alt'] + a['cmd'] - 25 <= s_p['alt'],
            s_p['alt'] <= s['alt'] + a['cmd'] + 25,
            s_p['alt'] - 25 <= s_p['obs'],
            s_p['obs'] <= s_p['alt'] + 25,
            #s_p['cmd_last'] == a['cmd']  # remember the last command
        )


class AltitudeDiscretizeGame(Game):
    def __init__(self, action_num=25):
        super().__init__()
        self.action_num = action_num
        self.actions = {
            'cmd': 'Int'
        }
        self.observable_states = {
            'obs': 'Int'
        }
        self.latent_states = {
            'alt': 'Int'
        }
        self.states = {**self.observable_states, **self.latent_states}

    def initial(self, s):
        return s['alt'] == 500

    def safety(self, s):
        return And(s['alt'] >= 450, s['alt'] <= 550)

    def enable_action(self, a):
        return And(a['cmd'] <= self.action_num, a['cmd'] >= -self.action_num)

    def transition_env(self, s, s_p, a):
        return And(
            s['alt'] + a['cmd'] - self.action_num <= s_p['alt'],
            s_p['alt'] <= s['alt'] + a['cmd'] + self.action_num,
            s_p['alt'] - self.action_num <= s_p['obs'],
            s_p['obs'] <= s_p['alt'] + self.action_num
        )



