import calculate_free_times

session_data = {'begin_date': '2017-11-20', 'end_date': '2017-11-27', 'begin_time': '07:00', 'end_time': '18:00' }

event_lists = [[{'date': '2017-11-22', 'start': '10:30', 'end': '17:30', 'summary': 'Something I have to do'}, {'date': '2017-11-24', 'start': '10:30', 'end': '17:30', 'summary': 'Something I have to do'}, {'date': '2017-11-27', 'start': '10:30', 'end': '17:30', 'summary': 'Something I have to do'}],                                                                                                                                                                                                                                                                                           [{'date': '2017-11-22', 'start': '06:30', 'end': '17:30', 'summary': 'Something I have to do'}, {'date': '2017-11-22', 'start': '17:30', 'end': '19:30', 'summary': 'Something I have to do'}, {'date': '2017-11-27', 'start': '10:30', 'end': '17:30', 'summary': 'Something I have to do'}],                                                                                                                                                        [{'date': '2017-11-22', 'start': '10:30', 'end': '22:30', 'summary': 'Something I have to do'}, {'date': '2017-11-24', 'start': '06:30', 'end': '18:30', 'summary': 'Something I have to do'}, {'date': '2017-11-27', 'start': 'All day', 'end': 'All day', 'summary': 'Something I have to do'}],                                                                                                                                                        [{'date': '2017-11-22', 'start': '10:30', 'end': '17:30', 'summary': 'Something I have to do'}, {'date': '2017-11-22', 'start': '05:30', 'end': '21:30', 'summary': 'Something I have to do'}, {'date': '2017-11-27', 'start': '10:30', 'end': '17:30', 'summary': 'Something I have to do'}]]



def test_times():
    assert {'date': '2017-11-22', 'start': '17:30', 'end': '18:00'} in calculate_free_times.get_free_times(event_lists[0], session_data)
    #assert {'date': '2017-11-22', 'start': '07:00', 'end': '10:30'} in calculate_free_times.get_free_times(event_lists[0], session_data)
    assert {'date': '2017-11-23', 'start': '07:00', 'end': '18:00'} in calculate_free_times.get_free_times(event_lists[0], session_data)

    assert '2017-11-22' not in calculate_free_times.get_free_times(event_lists[1], session_data)

    assert '2017-11-27' not in calculate_free_times.get_free_times(event_lists[2], session_data)

    assert '2017-11-22' not in calculate_free_times.get_free_times(event_lists[3], session_data)
