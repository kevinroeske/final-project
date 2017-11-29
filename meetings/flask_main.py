import flask
from flask import render_template
from flask import request
from flask import url_for
import pymongo
from pymongo import MongoClient
import bson
import uuid
import calculate_free_times
import json
import logging



# Date handling 
import arrow # Replacement for datetime, based on moment.js
# import datetime # But we still need time
from dateutil import tz  # For interpreting local times


# OAuth2  - Google library implementation for convenience
from oauth2client import client
import httplib2   # used in oauth2 flow

# Google API for services 
from apiclient import discovery

###
# Globals
###
import config
if __name__ == "__main__":
    CONFIG = config.configuration()
else:
    CONFIG = config.configuration(proxied=True)

app = flask.Flask(__name__)
app.debug=CONFIG.DEBUG
app.logger.setLevel(logging.DEBUG)
app.secret_key=CONFIG.SECRET_KEY


#########
#
# The code for the mongo stuff is lifted from project 6
#
#########

MONGO_CLIENT_URL = "mongodb://{}:{}@{}:{}/{}".format(
    CONFIG.DB_USER,
    CONFIG.DB_USER_PW,
    CONFIG.DB_HOST,
    CONFIG.DB_PORT,
    CONFIG.DB)
app.logger.debug("Using URL '{}'".format(MONGO_CLIENT_URL))

try:
    dbclient = MongoClient(MONGO_CLIENT_URL)
    db = getattr(dbclient, CONFIG.DB)
    app.logger.debug("Database acquired.")
    collection = db.dated
except Exception as err:
    app.logger.debug("Failed to access database.")
    app.logger.debug(str(err))

def get_profiles():
    """ 
    Returns all memos in the database, in a form that
    can be inserted directly in the 'session' object.
    """
    records = [ ] 
    for record in collection.find( { "type": "profile" } ):
        records.append(record)
    return records

SCOPES = 'https://www.googleapis.com/auth/calendar.readonly'
CLIENT_SECRET_FILE = CONFIG.GOOGLE_KEY_FILE  ## You'll need this
APPLICATION_NAME = 'MeetMe class project'

#############################
#
#  Pages (routed from URLs)
#
#############################

@app.route("/")
@app.route("/index")
def index():
  app.logger.debug("Entering index")
  flask.session.clear();
  app.logger.debug("Flask session state:" + str(flask.session))
  init_session_values()
  return render_template('index.html')

@app.route("/select", methods=['POST'])
def select():
    state_object = {}
    user_name = request.form['name']
    flask.session['user_name'] = user_name
    app.logger.debug("Name collected: " + flask.session['user_name'])
    col = get_profiles()
    app.logger.debug("Profiles found: " + str(col))
    for profile in col:
        if profile['name'] == user_name:
            for key in profile['session']:
                flask.session[key] = profile['session'][key]
            app.logger.debug("Session restored: " + str(flask.session))
            return render_template('select.html')
    state_object['type'] = "profile"
    state_object['name'] = flask.session['user_name']
    state_object['session'] = dict(flask.session)
    collection.delete_one({"name": state_object['name']})
    collection.insert(state_object)
    app.logger.debug("Profile details: " + str(state_object))
    app.logger.debug("State saved.")    
    return render_template('select.html')

@app.route("/choose")
def choose():
    ## We'll need authorization to list calendars 
    ## I wanted to put what follows into a function, but had
    ## to pull it back here because the redirect has to be a
    ## 'return' 
    app.logger.debug("Checking credentials for Google calendar access")
    credentials = valid_credentials()
    if not credentials:
      app.logger.debug("Redirecting to authorization")
      return flask.redirect(flask.url_for('oauth2callback'))

    gcal_service = get_gcal_service(credentials)
    app.logger.debug("Returned from get_gcal_service")
    flask.g.calendars = list_calendars(gcal_service)
    return render_template('select.html')

####
#
#  Google calendar authorization:
#      Returns us to the main /choose screen after inserting
#      the calendar_service object in the session state.  May
#      redirect to OAuth server first, and may take multiple
#      trips through the oauth2 callback function.
#
#  Protocol for use ON EACH REQUEST: 
#     First, check for valid credentials
#     If we don't have valid credentials
#         Get credentials (jump to the oauth2 protocol)
#         (redirects back to /choose, this time with credentials)
#     If we do have valid credentials
#         Get the service object
#
#  The final result of successful authorization is a 'service'
#  object.  We use a 'service' object to actually retrieve data
#  from the Google services. Service objects are NOT serializable ---
#  we can't stash one in a cookie.  Instead, on each request we
#  get a fresh serivce object from our credentials, which are
#  serializable. 
#
#  Note that after authorization we always redirect to /choose;
#  If this is unsatisfactory, we'll need a session variable to use
#  as a 'continuation' or 'return address' to use instead. 
#
####

def valid_credentials():
    """
    Returns OAuth2 credentials if we have valid
    credentials in the session.  This is a 'truthy' value.
    Return None if we don't have credentials, or if they
    have expired or are otherwise invalid.  This is a 'falsy' value. 
    """
    if 'credentials' not in flask.session:
      return None

    credentials = client.OAuth2Credentials.from_json(
        flask.session['credentials'])

    if (credentials.invalid or
        credentials.access_token_expired):
      return None
    return credentials


def get_gcal_service(credentials):
  """
  We need a Google calendar 'service' object to obtain
  list of calendars, busy times, etc.  This requires
  authorization. If authorization is already in effect,
  we'll just return with the authorization. Otherwise,
  control flow will be interrupted by authorization, and we'll
  end up redirected back to /choose *without a service object*.
  Then the second call will succeed without additional authorization.
  """
  app.logger.debug("Entering get_gcal_service")
  http_auth = credentials.authorize(httplib2.Http())
  service = discovery.build('calendar', 'v3', http=http_auth)
  app.logger.debug("Returning service")
  return service

@app.route('/oauth2callback')
def oauth2callback():
  """
  The 'flow' has this one place to call back to.  We'll enter here
  more than once as steps in the flow are completed, and need to keep
  track of how far we've gotten. The first time we'll do the first
  step, the second time we'll skip the first step and do the second,
  and so on.
  """
  app.logger.debug("Entering oauth2callback")
  flow =  client.flow_from_clientsecrets(
      CLIENT_SECRET_FILE,
      scope= SCOPES,
      redirect_uri=flask.url_for('oauth2callback', _external=True))
  ## Note we are *not* redirecting above.  We are noting *where*
  ## we will redirect to, which is this function. 
  
  ## The *second* time we enter here, it's a callback 
  ## with 'code' set in the URL parameter.  If we don't
  ## see that, it must be the first time through, so we
  ## need to do step 1. 
  app.logger.debug("Got flow")
  if 'code' not in flask.request.args:
    app.logger.debug("Code not in flask.request.args")
    auth_uri = flow.step1_get_authorize_url()
    return flask.redirect(auth_uri)
    ## This will redirect back here, but the second time through
    ## we'll have the 'code' parameter set
  else:
    ## It's the second time through ... we can tell because
    ## we got the 'code' argument in the URL.
    app.logger.debug("Code was in flask.request.args")
    auth_code = flask.request.args.get('code')
    credentials = flow.step2_exchange(auth_code)
    flask.session['credentials'] = credentials.to_json()
    ## Now I can build the service and execute the query,
    ## but for the moment I'll just log it and go back to
    ## the main screen
    app.logger.debug("Got credentials")
    return flask.redirect(flask.url_for('choose'))

#####
#
#  Option setting:  Buttons or forms that add some
#     information into session state.  Don't do the
#     computation here; use of the information might
#     depend on what other information we have.
#   Setting an option sends us back to the main display
#      page, where we may put the new information to use. 
#
#####

@app.route('/show_appointments')
def show_appointments():
    service = get_gcal_service(valid_credentials())
    calendar_list = service.calendarList().list().execute()["items"]
    app.logger.debug("calendar_list: " + str(calendar_list))
    cal_sum_list = request.values.getlist('checked')
    app.logger.debug("cal_sum_list: " + str(cal_sum_list))
    app.logger.debug("Calendars selected: " + str(cal_sum_list))
    events = []
    app.logger.debug("Times: " +flask.session['begin_time'] + " " + flask.session['end_time'])
    begin_time_stamp = arrow.get(flask.session['begin_date'] + "T" + flask.session['begin_time']).isoformat()
    end_time_stamp = arrow.get(flask.session['end_date'] + "T" + flask.session['end_time']).isoformat()
    for calendar in calendar_list:
        if calendar["id"] in cal_sum_list:
            eventsResult = service.events().list(
              calendarId=calendar["id"], timeMin=begin_time_stamp, timeMax=end_time_stamp, singleEvents=True,
              orderBy='startTime').execute()
            app.logger.debug("Events retreived: " + str(eventsResult))
            for event in eventsResult['items']:
                if 'dateTime' in event['start']:
                    busy_date = arrow.get(event['start']['dateTime'])
                else:
                    busy_date = arrow.get(event['start']['date'])
                if 'dateTime' in event['start']:
                    busy_s_time = arrow.get(interpret_time(event['start']['dateTime']))
                else:
                    busy_s_time = arrow.get(busy_date.isoformat()[:10]+"T"+'00:00:00')
                if 'dateTime' in event['end']:
                    busy_e_time = arrow.get(interpret_time(event['end']['dateTime']))
                else:
                    busy_e_time = arrow.get(busy_date.isoformat()[:10]+"T"+'11:59:59')
                if busy_date >= arrow.get(flask.session['begin_date']) and busy_date <= arrow.get(flask.session['end_date']):
                    if busy_e_time >= arrow.get(interpret_time(
                        flask.session['begin_time'])) and busy_s_time <= arrow.get(
                        interpret_time(flask.session['end_time'])) and event['status'] == 'confirmed':
                        events.append(event)
            app.logger.debug("Events dump: " + str(events))
            cooked_events = cook_events(events)
            app.logger.debug("Cooked events: " + str(cooked_events))
            free_time_list = calculate_free_times.get_free_times(cooked_events, flask.session)
            flask.g.events = cooked_events
            app.logger.debug("Full busy blocks: " + str(cooked_events))
            app.logger.debug("Free blocks: " + str(free_time_list))
            flask.g.freetime = free_time_list
            
    return render_template('appointments.html')

@app.route('/setrange', methods=['POST'])
def setrange():
    """
    User chose a date range with the bootstrap daterange
    widget.
    """
    app.logger.debug("Entering setrange")  
    flask.flash("Setrange gave us '{}'".format(
      request.form.get('daterange')))
    daterange = request.form.get('daterange')
    flask.session['daterange'] = daterange
    daterange_parts = daterange.split()
    time_start = str(request.form.get("starttime"))
    time_end = str(request.form.get("endtime"))
    app.logger.debug("Time range: " + time_start + " - " + time_end)
    flask.session['begin_time'] = interpret_time(time_start)[:19][11:]
    flask.session['end_time'] = interpret_time(time_end)[:19][11:]
    app.logger.debug("Times saved as: " + flask.session['begin_time'] + " and " + flask.session['end_time'])
    flask.session['begin_date'] = interpret_date(daterange_parts[0])[:10]+"T"+flask.session['begin_time']
    flask.session['end_date'] = interpret_date(daterange_parts[2])[:10]+"T"+flask.session['end_time']
    app.logger.debug("Setrange parsed {} - {}  dates as {} - {}".format(
      daterange_parts[0], daterange_parts[1], 
      flask.session['begin_date'], flask.session['end_date']))
    return flask.redirect(flask.url_for("choose"))

####
#
#   Initialize session variables 
#
####

def init_session_values():
    """
    Start with some reasonable defaults for date and time ranges.
    Note this must be run in app context ... can't call from main. 
    """
    # Default date span = tomorrow to 1 week from now
    now = arrow.now('local')     # We really should be using tz from browser
    tomorrow = now.replace(days=+1)
    nextweek = now.replace(days=+7)
    flask.session["begin_date"] = tomorrow.floor('day').isoformat()
    flask.session["end_date"] = nextweek.ceil('day').isoformat()
    flask.session["daterange"] = "{} - {}".format(
        tomorrow.format("MM/DD/YYYY"),
        nextweek.format("MM/DD/YYYY"))
    # Default time span each day, 8 to 5
    flask.session["begin_time"] = interpret_time("9am")[:19][11:]
    flask.session["end_time"] = interpret_time("5pm")[:19][11:]

def interpret_time( text ):
    """
    Read time in a human-compatible format and
    interpret as ISO format with local timezone.
    May throw exception if time can't be interpreted. In that
    case it will also flash a message explaining accepted formats.
    """
    app.logger.debug("Decoding time '{}'".format(text))
    time_formats = ["ha", "h:mma",  "h:mm a", "H:mm"]
    try: 
        as_arrow = arrow.get(text, time_formats).replace(tzinfo=tz.tzlocal())
        as_arrow = as_arrow.replace(year=2016) #HACK see below
        app.logger.debug("Succeeded interpreting time")
    except:
        app.logger.debug("Failed to interpret time")
        flask.flash("Time '{}' didn't match accepted formats 13:30 or 1:30pm"
              .format(text))
        raise
    return as_arrow.isoformat()
    #HACK #Workaround
    # isoformat() on raspberry Pi does not work for some dates
    # far from now.  It will fail with an overflow from time stamp out
    # of range while checking for daylight savings time.  Workaround is
    # to force the date-time combination into the year 2016, which seems to
    # get the timestamp into a reasonable range. This workaround should be
    # removed when Arrow or Dateutil.tz is fixed.
    # FIXME: Remove the workaround when arrow is fixed (but only after testing
    # on raspberry Pi --- failure is likely due to 32-bit integers on that platform)


def interpret_date( text ):
    """
    Convert text of date to ISO format used internally,
    with the local time zone.
    """
    try:
      as_arrow = arrow.get(text, "MM/DD/YYYY").replace(
          tzinfo=tz.tzlocal())
    except:
        flask.flash("Date '{}' didn't fit expected format 12/31/2001")
        raise
    return as_arrow.isoformat()

def next_day(isotext):
    """
    ISO date + 1 day (used in query to Google calendar)
    """
    as_arrow = arrow.get(isotext)
    return as_arrow.replace(days=+1).isoformat()

####
#
#  Functions (NOT pages) that return some information
#
####
  
def list_calendars(service):
    """
    Given a google 'service' object, return a list of
    calendars.  Each calendar is represented by a dict.
    The returned list is sorted to have
    the primary calendar first, and selected (that is, displayed in
    Google Calendars web app) calendars before unselected calendars.
    """
    app.logger.debug("Entering list_calendars")  
    calendar_list = service.calendarList().list().execute()["items"]
    result = [ ]
    for cal in calendar_list:
        kind = cal["kind"]
        id = cal["id"]
        if "description" in cal: 
            desc = cal["description"]
        else:
            desc = "(no description)"
        summary = cal["summary"]
        # Optional binary attributes with False as default
        selected = ("selected" in cal) and cal["selected"]
        primary = ("primary" in cal) and cal["primary"]
        

        result.append(
          { "kind": kind,
            "id": id,
            "summary": summary,
            "selected": selected,
            "primary": primary
            })
    return sorted(result, key=cal_sort_key)


def cal_sort_key( cal ):
    """
    Sort key for the list of calendars:  primary calendar first,
    then other selected calendars, then unselected calendars.
    (" " sorts before "X", and tuples are compared piecewise)
    """
    if cal["selected"]:
       selected_key = " "
    else:
       selected_key = "X"
    if cal["primary"]:
       primary_key = " "
    else:
       primary_key = "X"
    return (primary_key, selected_key, cal["summary"])

def cook_events(events):
    cooked = []
    for event in events:
        if 'dateTime' in event['start']:
            start = event['start']['dateTime'][11:][:5]
            date = event['start']['dateTime'][:10]
        else:
            start = "All day"
            date = event['start']['date'][:10]
        if 'dateTime' in event['end']:
            end = event['end']['dateTime'][11:][:5]
        else:
            end = "All day"
        summary = event['summary']
        cooked.append({"date": date, "start" : start, "end": end, "summary": summary})
    cooked = sorted(cooked, key=lambda k: arrow.get(k["date"]))
    return cooked

#################
#
# Functions used within the templates
#
#################

@app.template_filter( 'fmtdate' )
def format_arrow_date( date ):
    try: 
        normal = arrow.get( date )
        return normal.format("ddd MM/DD/YYYY")
    except:
        return "(bad date)"

@app.template_filter( 'fmttime' )
def format_arrow_time( time ):
    try:
        normal = arrow.get( time )
        return normal.format("HH:mm")
    except:
        return "(bad time)"
    
#############


if __name__ == "__main__":
  # App is created above so that it will
  # exist whether this is 'main' or not
  # (e.g., if we are running under green unicorn)
  app.run(port=CONFIG.PORT,host="0.0.0.0")
    
