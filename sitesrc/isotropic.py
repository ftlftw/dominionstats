#!/usr/bin/env python
# -*- coding: utf-8 -*-

# TODO: Add copyright notice here

"""Scraping support for Isotropic.
"""

import boto.s3.connection
import bson.binary
import bz2
import cStringIO
import datetime
import io
import logging
import sys
import tarfile
import urllib2
import re

import utils


# Module-level logging instance
log = logging.getLogger(__name__)

#TODO: read this from config file?
#s3_location = 'ftl-goko-councilroom-test-bucket'
s3_location = 'static.councilroom.mccllstr.com'
time_from_filename_re = re.compile('game-\d{8}-(\d{6})-')

class IsotropicProcessingDate(object):
    # TODO: This is a partial implementation

    tracker = None
    date = None
    date_dict = None

    class Key(object):
        """Names of MongoDB keys"""
        GAME_DATE = 'game_date'
        STEPS = 'steps'

    def __init__(self, tracker, date):
        self.tracker = tracker
        self.date = date

        self.date_dict = tracker.tracker_col.find_one({self.Key.GAME_DATE: date,})
        if self.date_dict == None:
            self.date_dict = {self.Key.GAME_DATE: date,
                              self.Key.STEPS: []}
            tracker.tracker_col.save(self.date_dict)


class IsotropicTracker(object):
    """
    """
    # TODO: This is a partial implementation

    db = None
    tracker_col = None
    leaderboard_history_col = None
    raw_games_col = None

    def __init__(self, db):
        self.db = db
        self.tracker_col = db.isotropic_tracker
        self.raw_games_col = db.raw_games

    def scraped_game_count(self, date):
        """Count the number of raw games loaded for the specified date

        date is a string in the format 'YYYYMMDD'
        """
        return self.raw_games_col.find({'game_date': date}).count()




def dates_needing_scraping(db):
    # TODO: This is a partial implementation
    it = IsotropicTracker(db)

    for cur_datetime in utils.datetimerange(datetime.date(2010, 10, 15),
                                            datetime.date.today()):
        str_date = time.strftime("%Y%m%d", cur_date.timetuple())

        # Check on the status of the day in our scraper tracker



        raw_game_count = raw_games_col.find({'game_date': str_date}).count()


class ScrapeError(Exception):
    """Indicates an error with the requested scrape."""
    def __init__(self, reason):
        self.args = reason,
        self.reason = reason

    def __str__(self):
        return '<scrape error %s>' % self.reason


class IsotropicScraper:
    """Implements the functions necessary to scrape data (games and
    leaderboards) from Isotropic or its related mirrors.
    """

    db = None
    rawgames_col = None
    s3conn = None

    def __init__(self, db, rawgames_name='raw_games'):
        self.db = db
        if db:
            self.rawgames_col = db[rawgames_name]


    def our_gamelog_filename(self, gamedate):
        """Returns our filename of the rawgame archive for the specified datetime.date"""
        return '{date.year:04d}{date.month:02d}{date.day:02d}.all.tar.bz2'.format(date=gamedate)


    def gamelog_s3_keyname(self, gamedate):
        """Returns the S3 keyname for the rawgame archive for the specified datetime.date"""
        return 'scrape_data/{filename}'.format(filename=self.our_gamelog_filename(gamedate))


    def isotropic_rawgame_url(self, gamedate):
        """Returns the URL to the rawgame archive at isotropic for the specified datetime.date"""
        return 'http://dominion.isotropic.org/gamelog/{date.year:04d}{date.month:02d}/{date.day:02d}/all.tar.bz2'.format(date=gamedate)


    def s3_rawgame_url(self, gamedate):
        """Returns the URL to the rawgame archive in S3 for the specified datetime.date"""
        return 'http://'+s3_location+'/{keyname}'.format(keyname=self.gamelog_s3_keyname(gamedate))


    def establish_s3_connection(self):
        """Get a boto connection for s3 operations using credentials from the ini file"""
        if self.s3conn is None:
            self.s3conn = boto.s3.connection.S3Connection(**utils.get_aws_credentials())


    def is_rawgames_in_s3(self, date):
        """Returns true if there is a whole-day rawgame archive in S3 for the specified date"""
        self.establish_s3_connection()

        bucket = self.s3conn.get_bucket(s3_location)
        return bucket.get_key(self.gamelog_s3_keyname(date)) is not None


    def copy_rawgames_to_s3(self, date):
        """Copy the day's archive of rawgames from isotropic to our S3 bucket"""
        self.establish_s3_connection()

        # Get a response object for the source data
        try:
            response = urllib2.urlopen(self.isotropic_rawgame_url(date))
        except urllib2.HTTPError:
            raise ScrapeError("Unable to retrieve data from %s" % self.isotropic_rawgame_url(date))

        # Upload the contents to s3 in the appropriate key
        bucket = self.s3conn.get_bucket(s3_location)
        key = bucket.get_key(self.gamelog_s3_keyname(date))
        if not key:
            log.debug("Creating new key")
            key = bucket.new_key(self.gamelog_s3_keyname(date))
            log.debug("Starting copy from isotropic")
            contents = io.BytesIO(response.read())
            log.debug("Starting upload to S3")
            key.set_contents_from_file(contents,
                                       cb=lambda sent, total: log.info('Transferred %d of %d', sent, total),
                                       replace=False, policy='public-read')


    def get_rawgames_from_s3(self, date):
        """Return the whole-day rawgame archive from our S3 bucket for
        the specified datetime.date"""
        self.establish_s3_connection()
        bucket = self.s3conn.get_bucket(s3_location)
        key = bucket.get_key(self.gamelog_s3_keyname(date))
        return key.get_contents_as_string()


    def get_rawgames_from_s3_as_filelike(self, date):
        """Return the whole-day rawgame archive from our S3 bucket for
        the specified datetime.date, wrapped in a filelike object"""
        return cStringIO.StringIO(self.get_rawgames_from_s3(date))


    def scrape_and_store_rawgames(self, date):
        """Top-level function to scrape rawgames from isotropic and
        store them in the local database.

        Accepts a datetime.date as the date to scrape.
        Returns the number of games inserted.

        Will skip (noop) dates that have already been loaded.
        """
        yyyy_mm_dd = date.strftime('%Y%m%d')

        # We expect to operate from data stored in our S3 bucket, so
        # check that it is available, first.
        if not self.is_rawgames_in_s3(date):
            # Not in S3 yet, get it and store it
            self.copy_rawgames_to_s3(date)

        # Retrieve the game archive for the specified date
        rawgames_archive_contents = self.get_rawgames_from_s3_as_filelike(date)

        # Insert the individual games into MongoDB
        insert_count = 0
        with tarfile.open(fileobj=rawgames_archive_contents) as t:
            # Figure out how many raw games are in the database,
            # compared with how many are in the tarfile
            database_count = self.rawgames_col.find({'game_date': yyyy_mm_dd,
                                                     'src': 'I'}).count() + \
                             self.rawgames_col.find({'game_date': yyyy_mm_dd,
                                                     'src': None}).count()
            tarfile_count = len(t.getmembers())
            if tarfile_count == database_count:
                log.info("Raw games for %s have already been loaded", yyyy_mm_dd)
            else:
                # Insert all the games
                for tarinfo in t:
                    log.debug("Working on %s", tarinfo.name)
                    time_extract = time_from_filename_re.match(tarinfo.name)
                    if not time_extract:
                        raise ScrapeError("Unable to parse time for sortable id from %s" % tarinfo.name)
                    hh_mm_ss = time_extract.group(1)

                    g = { u'_id': tarinfo.name,
                          u'game_date': yyyy_mm_dd,
                          u'src': 'I',
                          u'sortable_id': "%s-%s-%s" % (yyyy_mm_dd, hh_mm_ss, tarinfo.name),
                          u'text': bson.Binary(bz2.compress(t.extractfile(tarinfo).read())) }
                    self.rawgames_col.save(g, safe=True)
                    insert_count += 1

        rawgames_archive_contents.close()

        return insert_count
