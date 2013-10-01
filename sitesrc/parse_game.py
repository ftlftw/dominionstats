#!/usr/bin/python
# -*- coding: utf-8 -*-

"""Parse raw game into parsed game documents.
High-level functionality that isn't implementation-specific.
Calls parse_goko_game and parse_iso_game."""

import bz2
import collections
import datetime
import logging
import logging.handlers
import re
import sys

from dominioncards import index_to_card
from game import Game
from keys import *
import parse_iso_game
import parse_goko_game
import parse_common


KEYWORDS = [locals()[w] for w in dict(locals()) if w.startswith('KW_')]

def assign_win_points(game_dict):
    """ Set win_points to number of win points for each player in game_dict."""
    def win_tuple(deck_dict):
        """ Return tuple ordered by increasing final standing. """
        # negate turns so that max() behaves; points good, turns bad.
        num_normal_turns = sum(not ( (POSSESSION in t and t[POSSESSION]) or \
                                     (OUTPOST in t and t[OUTPOST]))
                               for t in deck_dict[TURNS])
        return (deck_dict[POINTS], -num_normal_turns)

    decks = game_dict[DECKS]
    winner_tuple = max(win_tuple(p) for p in decks)
    winners = [p for p in decks if win_tuple(p) == winner_tuple]

    win_points = float(len(decks)) / len(winners)
    for player in decks:
        player[WIN_POINTS] = win_points if player in winners else 0.0


GOKO_LOG_RE = re.compile(r"^------------ Game Setup ------------", re.MULTILINE)
ISO_LOG_RE = re.compile(r"^<html><head>", re.MULTILINE)

def parse_game(game_str, dubious_check = False):
    """ Parse game_str into game dictionary

    game_str: Entire contents of a log file.
    dubious_check: If true, raise a BogusGame exception if the game is
      suspicious.

    determines whether the log file is from Goko or iso. Calls specialized
    parse functions in parse_iso_game and parse_goko_game

    returns a dict with the following fields:
      decks: A list of player decks, as documend in parse_deck().
      supply: A list of cards in the supply.
      players: A list of normalized player names.
      game_end: List of cards exhausted that caused the game to end.
      resigned: True iff some player in the game resigned..
      start_decks: A list of initial player decks. 
      rating_type: how the game was rated. 
    """

    try:
        if ISO_LOG_RE.match(game_str):
            game_dict = parse_iso_game.parse_game(game_str, dubious_check)
        elif GOKO_LOG_RE.match(game_str):
            game_dict = parse_goko_game.parse_game(game_str, dubious_check)
    except (parse_common.BogusGameError, parse_common.ParsingError,
            parse_common.ParseTurnHeaderError):
        # These are anticipated, and should just be passed upwards
        raise
    except:
        # Unexpected exception
        import traceback
        raise parse_common.ParsingError(traceback.format_exc())

    assign_win_points(game_dict)
    if dubious_check and Game(game_dict).dubious_quality():
        raise parse_common.BogusGameError('Dubious Quality')

    return game_dict

def save_parse_error(parse_error_col, log, game, message):
    """ Store parsing errors with the game ID so we can reflow them later """
    parse_error = {'game_id': game['_id'],
                   'game_date': game['game_date'],
                   'message': message,
                   'inserted': datetime.datetime.isoformat(datetime.datetime.now()),
                   }
    try:
        parse_error_col.save(parse_error, safe=True, check_keys=True)
    except Exception:
        log.exception("Got exception on trying to save parsing error for game %s", game['_id'])


def parse_game_from_dict(log, parse_error_col, game):
    """ Parse game from raw_game collection dict object. """
    contents = bz2.decompress(game['text']).decode('utf-8')

    if not contents:
        log.debug('%s is empty game', game['_id'])
        return None
    if '<b>game aborted' in contents:
        log.warning('%s is aborted game', game['_id'])
        return None
    if '<title>403 Forbidden' in contents or '<title>404 Not Found' in contents:
        log.warning('%s mis-downloaded game', game['_id'])
        return None
    try:
        parsed = parse_game(contents, dubious_check = True)
        parsed['_id'] = game['_id']
        parsed['sortable_id'] = game['sortable_id']
        parsed['game_date'] = game['game_date']
        return parsed
    except parse_common.BogusGameError as bge:
        log.debug('%s got %s', game['_id'], bge)
    except (parse_common.ParsingError, parse_common.ParseTurnHeaderError,
            AssertionError) as ex:
        log.warning('%s got %s', game['_id'], ex)
        save_parse_error(parse_error_col, log, game, str(ex))
    return None

def parse_and_insert(log, raw_games, games_col, parse_error_col, year_month_day):
    """ Parse the list of games and insert them into the MongoDB.

    log: Logging object
    raw_games: List of games to parse, each in dict format
    games_col: Destination MongoDB collection
    parse_error_col: MongoDB collection for parse errors (for potential reflow later)
    year_month_day: string in yyyymmdd format encoding date
    """
    log.debug('Beginning to parse %d games for %s', len(raw_games), year_month_day)
    parsed_games = map(lambda x: parse_game_from_dict(log, parse_error_col, x), raw_games)

    log.debug('Beginning to filter %d games for %s', len(parsed_games), year_month_day)
    parsed_games = [x for x in parsed_games if x]
    track_brokenness(log, parse_error_col, parsed_games)

    log.debug('Beginning to insert %d games for %s', len(parsed_games), year_month_day)

    for game in parsed_games:
        try:
            games_col.save(game, safe=True, check_keys=True)
        except Exception:
            log.exception("Got exception on trying to insert parsed game %s", game['_id'])

    return len(parsed_games)


def track_brokenness(log, parse_error_col, parsed_games):
    """Print some summary statistics about cards that cause bad parses."""
    failures = 0
    wrongness = collections.defaultdict(int)
    overall = collections.defaultdict(int)
    for raw_game in parsed_games:
        accurately_parsed = check_game_sanity(Game(raw_game), log)
        if not accurately_parsed:
            log.warning('Failed to accurately parse game %s', raw_game['_id'])
            save_parse_error(parse_error_col, log, raw_game, 'check_game_sanity failed')
            failures += 1
        for card in raw_game[SUPPLY]:
            if not accurately_parsed:
                wrongness[card] += 1
            overall[card] += 1

    ratios = []
    for card in overall:
        ratios.append(((float(wrongness[card]) / overall[card]), index_to_card(card)))
    ratios.sort()
    if ratios and ratios[-1][0] > 0:
        log.warning("Ratios for problem cards %s, %d failures out of %d games", ratios[-10:],
                    failures, len(parsed_games))
    else:
        log.debug('Perfect parsing, %d games!', len(parsed_games))


__problem_deck_index__ = 0
def check_game_sanity(game_val, log):
    """ Check if if game_val is self consistent.

    In particular, check that the end game player decks match the result of
    simulating deck interactions saved in game val."""

    global __problem_deck_index__

    supply = game_val.get_supply()
    if game_val.any_resigned():
        return True # Resign leaves deck in arbitrary state, don't catch that

    # ignore known bugs.
    #if set(supply).intersection([get_card('Masquerade'), get_card('Black Market'), get_card('Trader')]):
        #return True

    # TODO: add score sanity checking here
    last_state = None
    game_state_iterator = game_val.game_state_iterator()
    for game_state in game_state_iterator:
        last_state = game_state
    for player_deck in game_val.get_player_decks():
        parsed_deck_comp = player_deck.Deck()
        computed_deck_comp = last_state.get_deck_composition(
            player_deck.name())

        parse_common.delete_keys_with_empty_vals(parsed_deck_comp)
        computed_dict_comp = dict(computed_deck_comp)
        parse_common.delete_keys_with_empty_vals(computed_dict_comp)

        if parsed_deck_comp != computed_deck_comp:
            found_something_wrong = False
            for card in set(parsed_deck_comp.keys() +
                            computed_deck_comp.keys()):
                if parsed_deck_comp.get(card, 0) != \
                        computed_deck_comp.get(card, 0):
                    if not found_something_wrong:
                        __problem_deck_index__ += 1
                        log.debug('[%d] %18s %9s %9s', __problem_deck_index__, 'card', 'from-data', 'from-sim')
                    log.debug('[%d] %-18s %9d %9d', __problem_deck_index__, card, parsed_deck_comp.get(card, 0),
                              computed_deck_comp.get(card, 0))
                    found_something_wrong = True
            if found_something_wrong:
                try:
                    log.debug('[%d] insane game for %s %s: %s', __problem_deck_index__, player_deck.name(), game_val.get_id(),
                              ' '.join(map(str, game_val.get_supply())))
                except UnicodeEncodeError:
                    pass
                return False
    return True
