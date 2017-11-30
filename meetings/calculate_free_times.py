import arrow
import flask
import logging

app = flask.Flask(__name__)

def get_free_times(cooked_events, session_data):
    free_times = []
    blocks_by_day = {}
    for day in arrow.Arrow.span_range('day', arrow.get(session_data['begin_date'][:10]), arrow.get(session_data['end_date'][:10])):
        date = day[0].isoformat()[:10]
        morning_start = '00:00'
        morning_end = session_data['begin_time']
        evening_start = session_data['end_time']
        evening_end = '23:59'
        morning_block = {'date': date, 'start': morning_start, 'end': morning_end}
        print("Added morning block: " + str(morning_block))
        evening_block = {'date': date, 'start': evening_start, 'end': evening_end}
        print("Added evening block: " + str(evening_block))
        cooked_events.append(morning_block)
        cooked_events.append(evening_block)
    while contains_overlapping(cooked_events):
        for event1 in cooked_events:
            for event2 in cooked_events:
                if overlapping(event1, event2):
                    merged_event=merge_events(event1, event2)
                    if event1 in cooked_events:                       
                        cooked_events.remove(event1)
                    if event2 in cooked_events:
                        cooked_events.remove(event2)
                    cooked_events.append(merged_event)
    app.logger.debug("Merged events: " + str(cooked_events))
    app.logger.debug("Busy Blocks: " + str(cooked_events))
#    for day in arrow.Arrow.span_range('day', arrow.get(session_data['begin_date'][:10]), arrow.get(session_data['end_date'][:10])):
#        for block in cooked_events:
#            if block['date'] == day[0].isoformat()[:10]:
#                blocks_by_day[day[0].isoformat()[:10]].append(block)
    cooked_events = sorted(cooked_events, key=lambda k: arrow.get(k["date"]))
    index = 1
    for event in cooked_events:
        if event['end'] != '23:59':
            if cooked_events[index]['start'] == '00:00':
                new_end = session_data['end_time']
            else:
                new_end = cooked_events[index]['start']
            if event['end'][:5] != new_end[:5]:
                free_times.append({'date': event['date'], 'start': event['end'][:5], 'end': new_end[:5]})
        index += 1
        if index == len(cooked_events):
            break
    print("Full busy blocks: " + str(cooked_events))
    while contains_overlapping(free_times):
        for block1 in free_times:
            for block2 in free_times:
                if overlapping(block1, block2):
                    merged_block = merge_free_blocks(block1, block2)
                    if block1 in free_times:
                        free_times.remove(block1)
                    if block2 in free_times:
                        free_times.remove(block2)
                    if merged_block['start'] != merged_block['end']:
                        free_times.append(merged_block)
    free_times = sorted(free_times, key=lambda k: k['start'])
    free_times = sorted(free_times, key=lambda j: j['date'])
    print("Free Time Blocks: " + str(free_times))
    
    return free_times

def merge_free_blocks(block1, block2):
    merged_block={}
    start1 = block1['start']
    start2 = block2['start']
    end1 = block1['end']
    end2 = block2['end']

    merged_block['date'] = block1['date']
    merged_block['start'] = max(start1, start2)
    merged_block['end'] = min(end1, end2)
    return merged_block

def merge_events(ev1, ev2):
    merged_event={}
    start1 = ev1['start']
    start2 = ev2['start']
    end1 = ev1['end']
    end2 = ev2['end']
    
    if start1 == 'All day' or start2 == 'All day':
        merged_event['start'] = 'All day'
        merged_event['end'] = 'All_day'
        return merged_event

    merged_event['date'] = ev1['date']
    merged_event['start'] = min(start1, start2)
    merged_event['end'] = max(end1, end2)
    return merged_event

def overlapping(ev1, ev2):
    app.logger.debug("Comparing " + str(ev1)+ " and " + str(ev2))
    if ev1['date'] != ev2['date']:
        app.logger.debug("Does not overlap")
        return False
    if ev1 == ev2:
        app.logger.debug("Does not overlap")
        return False
    start1 = ev1['start']
    start2 = ev2['start']
    if start1 == 'All day' or start2 == 'All day':
        app.logger.debug("Overlaps")
        return True
    end1 = ev1['end']
    end2 = ev2['end']
    if start1 <= end2 and start2 <= end1:
        app.logger.debug("Overlaps")
        return True
    else:
        app.logger.debug("Does not overlap")
        return False

def contains_overlapping(event_list):
    for event1 in event_list:
        for event2 in event_list:
            if event1 != event2 and overlapping(event1, event2):
                app.logger.debug("Conatains overlapping appointments")
                return True
    app.logger.debug("Does not conatain overlapping appointments")
    return False
