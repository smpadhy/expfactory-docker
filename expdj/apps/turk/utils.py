from boto.mturk.connection import MTurkConnection
from boto.mturk.question import ExternalQuestion
from boto.mturk.price import Price
from expdj.settings import BASE_DIR
from numpy.random import choice
import ConfigParser
import datetime
import pandas
import json
import os

from django.conf import settings


# RESULTS UTILS
def to_dict(input_ordered_dict):
    '''to_dict converts an input ordered dict into a standard dict
    :param input_ordered_dict: the ordered dict
    '''
    return json.loads(json.dumps(input_ordered_dict))


PRODUCTION_HOST = u'mechanicalturk.amazonaws.com'
SANDBOX_HOST = u'mechanicalturk.sandbox.amazonaws.com'

PRODUCTION_WORKER_URL = u'https://www.mturk.com'
SANDBOX_WORKER_URL = u'https://workersandbox.mturk.com'


class InvalidTurkSettings(Exception):
    """Connection settings for Turk are invalid"""
    def __init__(self, value):
        self.parameter = value

    def __unicode__(self):
        return repr(self.parameter)
    __str__ = __unicode__


def amazon_string_to_datetime(amazon_string):
    """Return datetime from passed Amazon format datestring"""

    amazon_iso_format = '%Y-%m-%dT%H:%M:%SZ'
    return datetime.datetime.strptime(
            amazon_string,
            amazon_iso_format)

def get_host():
    """Read configuration file and get proper host

    The host returned will be the contents of either PRODUCTION_HOST or
    PRODUCTION_HOST as defined in this module. Because the host
    parameter is optional, if it is omitted, the PRODUCTION_HOST is
    returned. Therefore, to use the sandbox, one has to explicitly set
    the host parameter to 'mechanicalturk.sandbox.amazonaws.com' in
    either the TURK or TURK_CONFIG_FILE parmeters/files.
    """
    host = PRODUCTION_HOST

    if hasattr(settings, 'TURK') and settings.TURK is not None:

        # Determine if we are in debug mode, set host appropriately
        if "debug" in settings.TURK:
            if settings.TURK["debug"] == 1:
                if "sandbox_host" in settings.TURK:
                    host = settings.TURK["sandbox_host"]
            else:
                if 'host' in settings.TURK:
                    host = settings.TURK['host']


    # A settings file will just be used in production, no debug option
    elif hasattr(settings, 'TURK_CONFIG_FILE') and\
                          settings.TURK_CONFIG_FILE is not None:
        config = ConfigParser.ConfigParser()
        config.read(settings.TURK_CONFIG_FILE)
        if config.has_option('Connection', 'host'):
            host = config.get('Connection', 'host')

    # We don't want any custom URL addresses
    if host.startswith('http://'):
        host = host.replace('http://', '', 1)

    if host.startswith('https://'):
        host = host.replace('https://', '', 1)

    # This will trigger error if user is not using external submit
    assert host in [SANDBOX_HOST, PRODUCTION_HOST]

    return host


def is_sandbox():
    """Return True if configuration is configured to connect to sandbox"""

    host = get_host()
    return host == SANDBOX_HOST


def get_worker_url():
    """Get proper URL depending upon sandbox settings"""

    if is_sandbox():
        return SANDBOX_WORKER_URL
    else:
        return PRODUCTION_WORKER_URL


def get_credentials(battery):
    """Load credentials from a credentials file"""
    credentials = "%s/expdj/auth/%s" %(BASE_DIR,battery.credentials)
    credentials = pandas.read_csv(credentials,sep="=",index_col=0,header=None)
    AWS_ACCESS_KEY_ID=credentials.loc["AWS_ACCESS_KEY_ID"][1]
    AWS_SECRET_ACCESS_KEY_ID=credentials.loc["AWS_SECRET_ACCESS_KEY_ID"][1]
    return AWS_ACCESS_KEY_ID,AWS_SECRET_ACCESS_KEY_ID

def get_connection(aws_access_key_id,aws_secret_access_key):
    """Create connection based upon settings/configuration parameters"""

    host = get_host()
    debug = 1

    if hasattr(settings, 'TURK') and settings.TURK is not None:
        if 'debug' in settings.TURK:
            debug = settings.TURK['debug']
    else:
        raise InvalidTurkSettings("Turk settings not found")

    return MTurkConnection(
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        host=host,
        debug=debug)


def get_app_url():
    if hasattr(settings, 'TURK') and settings.TURK is not None:
        if "app_url" in settings.TURK:
            return settings.TURK["app_url"]

# Selection Algorithms ###############################################################################

def select_experiments_time(maximum_time_allowed,experiments):
    '''select_experiments_time
    a selection algorithm that selects experiments from list based on not exceeding some max time
    :param maximum_time_allowed: the maximum time allowed, in seconds
    :param experiments: list of experiment.Experiment objects, with time variable specified in minutes
    '''
    # Add tasks with random selection until we reach the time limit
    task_list = []
    total_time = 0
    exps = experiments[:]
    while (total_time < maximum_time_allowed) and len(exps)>0:
        # Randomly select an experiment
        experiment = exps.pop(choice(range(len(exps))))
        if (total_time + experiment.template.time*60.0) <= maximum_time_allowed:
            task_list.append(experiment)
    return task_list

def select_random_n(experiments,N):
    '''select_experiments_N
    a selection algorithm that selects a random N experiments from list
    :param experiments: list of experiment.Experiment objects, with time variable specified in minutes
    :param N: the number of experiments to select
    '''
    if N>len(experiments):
        N=len(experiments)
    return choice(experiments,N).tolist()


def get_worker_experiments(worker,battery,completed=False):
    '''get_worker_experiments returns a list of experiment tags that
    a worker has/has not completed for a particular battery
    '''
    from expdj.apps.turk.models import Result
    battery_tags = [x.template.exp_id for x in battery.experiments.all()]
    worker_experiments = Result.objects.filter(worker=worker,battery=battery)
    worker_tags = [x.experiment.exp_id for x in worker_experiments if x.completed==True]

    if completed==False:
        uncompleted_experiments = [e for e in battery_tags if e not in worker_tags]
        return uncompleted_experiments
    else:
        completed_experiments = [e for e in worker_tags if e in battery_tags]
        return completed_experiments

def get_time_difference(t1,t2,format='%Y-%m-%d %H:%M:%S'):
    '''calculate difference between two time strings, t1 and t2, returns minutes'''
    d1 = datetime.datetime.strptime(t1, format)
    d2 = datetime.datetime.strptime(t2, format)
    return (d2 - d1).total_seconds() / 60
