from z3 import *
from examples.game import Game

class AltitudeGame3D(Game):
    def __init__(self):
        super().__init__()
        self.sensor_error_z = 25
        self.wind_error_z = 25
        self.actions = {
            'cmd_x': 'Real',  # Command for x-axis
            'cmd_y': 'Real',  # Command for y-axis
            'cmd_z': 'Real'   # Command for z-axis
        }
        self.observable_states = {
            'obs_x': 'Real',  # Observable x position
            'obs_y': 'Real',  # Observable y position
            'obs_z': 'Real'   # Observable z position
        }
        self.latent_states = {
            'alt_x': 'Real',  # True x position
            'alt_y': 'Real',  # True y position
            'alt_z': 'Real'   # True z position
        }
        self.states = {**self.observable_states, **self.latent_states}

    def initial(self, s):
        return And(
            s['alt_x'] == 500,
            s['alt_y'] == 500,
            s['alt_z'] == 500
        )

    def safety(self, s):
        return And(
            s['alt_x'] >= 450, s['alt_x'] <= 550,
            s['alt_y'] >= 450, s['alt_y'] <= 550,
            s['alt_z'] >= 450, s['alt_z'] <= 550
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
            s_p['obs_y'] <= s_p['alt_y'] + 25,

            # Z-axis transition with uncertainty
            s['alt_z'] + a['cmd_z'] - self.wind_error_z <= s_p['alt_z'],
            s_p['alt_z'] <= s['alt_z'] + a['cmd_z'] + self.wind_error_z,
            # Z-axis observation with uncertainty
            s_p['alt_z'] - self.sensor_error_z <= s_p['obs_z'],
            s_p['obs_z'] <= s_p['alt_z'] + self.sensor_error_z
        )
