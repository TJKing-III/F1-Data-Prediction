from urllib.request import urlopen
import json
import fastf1

session = fastf1.get_session(2021, 22, 'Race')
print(session.name, session.event)

def get_data(url):
    response = urlopen(url)
    data = json.loads(response.read().decode('utf-8'))
    return data