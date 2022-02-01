"""Visualize group and device level configurations using plotly treemaps.

This script displays the indi level config of all devices in a specified
group. Note that it is possible for the indi config to have the same
(duplicate) setting as the group, in which case those settings will show up
here. This also has the optional ability to display what is configured at the
group level. This script currently does NOT support displaying removal lists.
"""

import requests
import json
import jsondiff
import os
import plotly.express as px
import plotly.graph_objects as go
import dash
import dash_core_components as dcc
import dash_html_components as html
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import sys

""" This will make all HTTP requests from the same session
retry for a total of 10 times, sleeping between retries with an
exponentially increasing backoff of 1s, 2s, 4s, and so on... It
will retry on basic connectivity issues and the listed HTTP
status codes. """

session = requests.session()
retries = Retry(total=10,  # Total number of retries to allow.
                backoff_factor=1,
                status_forcelist=[408, 429, 502, 503, 504],
                )
session.mount('https://', HTTPAdapter(max_retries=retries))

server = 'https://www.cradlepointecm.com/api/v2'

headers = {
            "X-CP-API-ID": os.environ.get("X-CP-API-ID-Support", ""),
            "X-CP-API-KEY": os.environ.get("X-CP-API-KEY-Support", ""),
            "X-ECM-API-ID": os.environ.get("X-ECM-API-ID-Support", ""),
            "X-ECM-API-KEY": os.environ.get("X-ECM-API-KEY-Support", ""),
            'Content-Type': 'application/json'
           }

group_id = 145120

#INDOT
#group_id = 281325

def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def get_router_ids(group_id):
    """Get all router_ids for group."""
    router_ids = []
    url = f'{server}/routers/?group={group_id}&fields=id&limit=500'
    while url:
        req = session.get(url, headers=headers)
        if req.status_code < 300:
            req = req.json()
            routers = req['data']
            for router in routers:
                router_ids.append(router['id'])
            url = req['meta']['next']
        else:
            print(f'Error {req}')
            sys.exit(1)
    return router_ids


def get_group_conf(group_id):
    """Get a copy of the entire group config."""
    url = f'{server}/groups/{group_id}/?fields=configuration'
    req = session.get(url, headers=headers)
    if req.status_code < 300:
        json_conf = req.json()['configuration']
        return json.loads(json.dumps(json_conf))
    else:
        print(f'Error {req}')
        sys.exit(1)


def get_default_conf(group_id):
    """Return default config for firmware."""
    url = f'{server}/groups/{group_id}/?fields=target_firmware'
    firmware = session.get(url, headers=headers).json()['target_firmware']
    url = f'{firmware}default_configuration/'
    req = session.get(url, headers=headers)
    if req.status_code < 300:
        return req.json()
    else:
        print(f'Error {req}')
        sys.exit(1)


router_conf_store = {}  # Every router's config stored as a seperate entry
group_config = get_group_conf(group_id)  # The group configuration
router_ids = get_router_ids(group_id)  # All router IDs in the group
print('There are', len(router_ids), 'routers in this group.')

firmware_config = get_default_conf(group_id)  # The default configuration

'''
    This dict stores every key value pair of every router config with a list
    of which router id's have a config for any given key or value. Example
    { firewall : router_ids: [182828, 34112, 345311], remote_admin:{...},
    ssh_admin: {...},  ....} The above means that there are 3 routers in the
    group that have a firewall configuration. The next keys, remote admin and
    so on, will have their own router_ids list until reaching each final value
    in the config.
'''
conf_keys_dict = {}

conf_keys_dict_tree_parents = conf_keys_dict.keys()

# The 4 lists below are what plotly uses to create the boxes
labels = []
ids = []
parents = []
values = []


def conf_parser(config, conf_keys_dict, path):
    """Add keys from a single router config to conf_keys_dict."""
    for key in config.keys():
        '''diff = jsondiff.diff(
            group_config[0].get(key, ''), config.get(key, ''))
        if(diff != {}):'''
        routerid = manager['router']['id']
        if key in conf_keys_dict:
            conf_keys_dict[key]['router_ids'].append(routerid)
        else:
            conf_keys_dict[key] = {'router_ids': [routerid]}
        if type(config.get(key)) == dict:
            if path:
                conf_parser(config.get(key), conf_keys_dict.get(key),
                            path+"."+str(key))
            else:
                conf_parser(config.get(key), conf_keys_dict.get(key),
                            str(key))
        elif type(config.get(key)) == list:
            stringKey = str(config.get(key))
            if stringKey in conf_keys_dict[key]:
                conf_keys_dict[key][stringKey].extend([routerid])
            else:
                conf_keys_dict[key][stringKey] = [routerid]
        else:
            if config.get(key) in conf_keys_dict[key]:
                conf_keys_dict[key][config.get(key)].extend([routerid])
            else:
                conf_keys_dict[key][config.get(key)] = [routerid]


def group_parser(conf, conf_keys_dict, path):
    """Add keys from the group to conf_keys_dict."""
    for key in conf.keys():
        if key != 'router_ids':
            if key in conf_keys_dict:
                conf_keys_dict[key]['router_ids'].append('group')
            else:
                conf_keys_dict[key] = {'router_ids': ['group']}
            if type(conf.get(key)) == dict:
                if path:
                    group_parser(conf.get(key), conf_keys_dict.get(key),
                                 path + "." + str(key))
                else:
                    group_parser(conf.get(key), conf_keys_dict.get(key),
                                 str(key))
            elif type(conf.get(key)) == list:
                stringKey = str(config.get(key))
                if stringKey in conf_keys_dict[key]:
                    conf_keys_dict[key][stringKey].extend(['group'])
                else:
                    conf_keys_dict[key][stringKey] = ['group']
            else:
                if conf.get(key) in conf_keys_dict[key]:
                    conf_keys_dict[key][conf.get(key)].extend(['group'])
                else:
                    conf_keys_dict[key][conf.get(key)] = ['group']


def graphBuilder(config, path):
    """Parse conf to create the lists (parents, values, labels) plotly uses."""
    for key in config.keys():
        if key != 'router_ids':
            if type(config.get(key)) == dict:
                if path:
                    for x in config.get(key).keys():
                        if x != 'router_ids':
                            parents.extend([path + '.' + key])
                            ids.extend([path + '.' + str(key) + '.' + str(x)])
                            labels.extend([str(x)])
                            if type(config[key][x]) == dict:
                                values.extend(
                                    [len(config[key][x]['router_ids'])])
                            else:
                                values.extend([len(config[key][x])])
                    graphBuilder(config.get(key), path + "." + str(key))
                else:
                    parents.extend([''])
                    labels.extend([key])
                    ids.extend([key])
                    values.extend([len(config[key]['router_ids'])])
                    for x in config.get(key).keys():
                        if x != 'router_ids':
                            parents.extend([key])
                            ids.extend([str(key) + '.' + x])
                            labels.extend([x])
                            if type(config[key][x]) == dict:
                                values.extend(
                                    [len(config[key][x]['router_ids'])])
                            else:
                                values.extend([len(config[key][x])])
                    graphBuilder(config.get(key), str(key))
            else:
                if path:
                    parents.extend([path + '.' + str(key)])
                    ids.extend(
                        [path + '.' + str(key) + '.' + str(config.get(key))])
                    labels.extend([str(config.get(key))])
                values.extend([len(config.get(key))])


for chunk in chunks(router_ids, 100):
    router_list = ','.join(chunk)
    url = f'{server}/configuration_managers/?router__in={router_list}&expand=router&limit=500'
    req = session.get(url, headers=headers)
    if req.status_code < 300:
        managers = req.json()['data']
        for manager in managers:
            config = manager['configuration'][0]
            conf_parser(config, conf_keys_dict, '')
            config['id'] = manager['router']['id']
            router_conf_store[manager['router']['id']] = config
    else:
        print(f'Error {req}')
        sys.exit(1)
        
group_parser(group_config[0], conf_keys_dict, '') # Uncomment to include the group configuration in the treemap
graphBuilder(conf_keys_dict, '')

'''
TODO
df5 = pd.json_normalize(list(conf_keys_dict.values()))#  ORRRR df5 = pd.json_normalize(list(conf_keys_dict.values())).T
df5.index = conf_keys_dict.keys()
'''

fig = px.treemap(
    names=labels,
    parents=parents,
    ids=ids,
    values=values,
    maxdepth=5,  # Sets how many boxes deep are visible
    # width=800,
    # height=800,
    title=f"Configuration Breakdown of Devices in Group {group_id}",
    color_discrete_map={'*': 'lightgrey'}
    # textinfo = "label+value+percent parent+percent entry+percent root",
)

fig.update_traces(root_color="lightgrey")
fig.update_layout(margin=dict(
    t=50, l=25, r=25, b=25),  uniformtext=dict(minsize=12, mode='hide'),)

fig.show(renderer="browser")  # To run without server


# TODO: Hidden elements: group and default config. When the checkbox is
# checked for either of these the graph includes ids with either "GROUP" or
# "Default"

#The below code runs the treemap in a server. 
'''
app = dash.Dash()
app.layout = html.Div([
    dcc.Graph(figure=fig)
])

app.run_server(debug=True, use_reloader=False)  # Turn off reloader if inside Jupyter
'''