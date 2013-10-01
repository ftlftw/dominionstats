#!/usr/bin/python

import dominioncards
import game
import utils

def games_stream(scanner, games_col):
    for raw_game in utils.progress_meter(scanner.scan(games_col, {})):
        yield game.Game(raw_game)

def available_cards(game_obj, gained_list):
    ret = set()
    ret.update(game_obj.get_supply())
    ret.update(dominioncards.EVERY_SET_CARDS)
    ret.update(gained_list)
    if dominioncards.Tournament in ret:
        ret.update(dominioncards.TOURNAMENT_WINNINGS)
    return ret
    
