from z3 import *
from examples.game import Game

class AltitudeGame2D(Game):
    def __init__(self):
        super().__init__()
        self.actions = {
            'cmd_x': 'Real',  # Command for x-axis
            'cmd_y': 'Real'   # Command for y-axis
        }
        self.observable_states = {
            'obs_x': 'Real',  # Observable x position
            'obs_y': 'Real'   # Observable y position
        }
        self.latent_states = {
            'alt_x': 'Real',  # True x position
            'alt_y': 'Real'   # True y position
        }
        self.states = {**self.observable_states, **self.latent_states}

    def initial(self, s):
        return And(
            s['alt_x'] == 500,
            s['alt_y'] == 500
        )

    def safety(self, s):
        return And(
            s['alt_x'] >= 450, s['alt_x'] <= 550,
            s['alt_y'] >= 450, s['alt_y'] <= 550
        )

    def enable_action(self, a):
        return BoolVal(True)

    def transition_env(self, s, s_p, a):
        return And(
            # X-axis transition with uncertainty
            s['alt_x'] + a['cmd_x'] - 25 <= s_p['alt_x'],
            s_p['alt_x'] <= s['alt_x'] + a['cmd_x'] + 25,
            # X-axis observation with uncertainty
            s_p['alt_x'] - 25 <= s_p['obs_x'],
            s_p['obs_x'] <= s_p['alt_x'] + 25,

            # Y-axis transition with uncertainty
            s['alt_y'] + a['cmd_y'] - 25 <= s_p['alt_y'],
            s_p['alt_y'] <= s['alt_y'] + a['cmd_y'] + 25,
            # Y-axis observation with uncertainty
            s_p['alt_y'] - 25 <= s_p['obs_y'],
            s_p['obs_y'] <= s_p['alt_y'] + 25
        )

class AltitudeDiscretize2DGame(Game):
    def __init__(self, action_num=25):
        super().__init__()
        self.action_num = action_num
        self.actions = {
            'cmd_x': 'Int',  # Command for x-axis
            'cmd_y': 'Int'   # Command for y-axis
        }
        self.observable_states = {
            'obs_x': 'Int',  # Observable x position
            'obs_y': 'Int'   # Observable y position
        }
        self.latent_states = {
            'alt_x': 'Int',  # True x position
            'alt_y': 'Int'   # True y position
        }
        self.states = {**self.observable_states, **self.latent_states}

    def initial(self, s):
        return And(
            s['alt_x'] == 500,
            s['alt_y'] == 500
        )

    def safety(self, s):
        return And(
            s['alt_x'] >= 450, s['alt_x'] <= 550,
            #s['alt_y'] >= 450, s['alt_y'] <= 550
        )

    def enable_action(self, a):
        return And(
            a['cmd_x'] <= self.action_num, a['cmd_x'] >= -self.action_num,
            a['cmd_y'] <= self.action_num, a['cmd_y'] >= -self.action_num
        )

    def transition_env(self, s, s_p, a):
        return And(
            # X-axis transition with uncertainty
            s['alt_x'] + a['cmd_x'] - self.action_num <= s_p['alt_x'],
            s_p['alt_x'] <= s['alt_x'] + a['cmd_x'] + self.action_num,
            # X-axis observation with uncertainty
            s_p['alt_x'] - self.action_num <= s_p['obs_x'],
            s_p['obs_x'] <= s_p['alt_x'] + self.action_num,

            # Y-axis transition with uncertainty
            s['alt_y'] + a['cmd_y'] - self.action_num <= s_p['alt_y'],
            s_p['alt_y'] <= s['alt_y'] + a['cmd_y'] + self.action_num,
            # Y-axis observation with uncertainty
            s_p['alt_y'] - self.action_num <= s_p['obs_y'],
            s_p['obs_y'] <= s_p['alt_y'] + self.action_num
        )
