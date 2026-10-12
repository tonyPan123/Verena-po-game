#!/usr/bin/env python3
"""Generate finite-action benchmark configurations with the selected action counts."""
import json
from importlib import import_module
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BakeryPastedFiniteGame = import_module('examples.finite_action.bakery.bakery-8-actions-matched').BakeryPastedFiniteGame
RobotFiniteGame = import_module('examples.finite_action.robot.robot-10-actions-matched').RobotFiniteGame
ProductionSystemScaleGame = import_module('examples.finite_action.parts.parts-2-actions-matched').ProductionSystemScaleGame

AE = ROOT / 'artifact'


def main():
    cases = []
    families = [
        ('bakery', [4,9,14,19,24], BakeryPastedFiniteGame, 'max_offset', [0,True,5,1,False]),
        ('parts', [1,3,5,7,9], ProductionSystemScaleGame, 'scale', [2,True,100,1,False]),
        ('robot', [4,9,14,19,24], RobotFiniteGame, 'max_distance', [0,True,5,1,False]),
    ]
    for family, values, game_class, parameter, options in families:
        for value in values:
            game = game_class(value)
            menu = ([{'box': i} for i in range(value+1)] if family == 'parts' else game.menu())
            name = f'{family}-{len(menu)}-actions-matched'
            cases.append({
                'name': name, 'module': f'examples.finite_action.{family}.{name}', 'class': game_class.__name__,
                'kwargs': {parameter: value}, 'expected': 'realizable', 'reconstructed': True,
                'family': family, 'paper_actions': len(menu),
                'strategy_backend': 'skeleton-qe', 'args': options,
            })
    po = {
        'family': 'Finite Action', 'table_i_mapping_confirmed': False,
        'paper': {'instances':15, 'sat':15, 'unsat':0, 'solved':15},
        'instances': cases,
    }
    (AE/'benchmarks/finite-action.json').write_text(json.dumps(po,indent=2)+'\n')


if __name__ == '__main__':
    main()
