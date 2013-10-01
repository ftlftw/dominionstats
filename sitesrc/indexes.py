#!/usr/bin/python

import logging
import logging.handlers
import os
import os.path
import re
import sys

import dominionstats.utils.log
import utils

from keys import *


# Module-level logging instance
log = logging.getLogger(__name__)


INDEXES = {
    'games': [
        PLAYERS,
        SUPPLY,
        SRC,
        ],
    'raw_games': [
        'game_date',
        'src',
        'sortable_id',
        ],
    'goals': [
        'goals.player',
        'goals.goal_name',
        ],
    }


def ensure_all_indexes(db):
    """Ensure all expected indexes are in place, for all tables"""
    for table_name, index_list in INDEXES.items():
        for index in index_list:
            log.info("Ensuring %s index for %s", index, table_name)
            db[table_name].ensure_index(index)


def main(parsed_args):
    ensure_all_indexes(utils.get_mongo_database())


if __name__ == '__main__':
    parser = utils.base_parser()
    args = parser.parse_args()
    dominionstats.utils.log.initialize_logging(args.debug)
    main(args)
