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
import dash
import dash_core_components as dcc
import dash_html_components as html
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import sys
from dash.dependencies import Input, Output
from treelib import Node, Tree

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
# SUPPORTS ACCOUNT
headers = {
            "X-CP-API-ID": os.environ.get("X-CP-API-ID-Support", ""),
            "X-CP-API-KEY": os.environ.get("X-CP-API-KEY-Support", ""),
            "X-ECM-API-ID": os.environ.get("X-ECM-API-ID-Support", ""),
            "X-ECM-API-KEY": os.environ.get("X-ECM-API-KEY-Support", ""),
            'Content-Type': 'application/json'
           }

group_id = 145120



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
ftree = Tree()
rootNode = ftree.create_node("ROOT", "ROOT")


# The 4 lists below are what plotly uses to create the boxes
labels = []
ids = []
parents = []
values = []


def conf_parser_tree(routerid, config, head):
    """Add keys from a single router config to conf_keys_dict."""
    tags = {c.tag: c.identifier for c in ftree.children(head.identifier)}
    for key in config.keys():
        nodey = 0
        if key in tags:
            nodey = ftree.get_node(tags[key])
            nodey.data.append(routerid)
        else:
            nodey = ftree.create_node(key, parent=head, data=[routerid])
        if type(config.get(key)) == dict:  # If not a leaf
            conf_parser_tree(routerid, config.get(key), nodey)
        else:  # Child is a leaf node
            child_tags = {c.tag: c.identifier for c in ftree.children(
                    nodey.identifier)}
            stringKey = ''
            if type(config.get(key)) == list:  # if leaf with list data type
                stringKey = str(config.get(key))
            else:
                stringKey = config.get(key)
            if stringKey == 'True':
                continue
            if stringKey in child_tags:
                nodey_c = ftree.get_node(child_tags[stringKey])
                listN = json.loads(nodey_c.data)
                listN.extend([routerid])
                nodey_c.data = json.dumps(listN)
                # Update child node
                nodey_gc = ftree.children(nodey_c.identifier)[0]
                listN = json.loads(nodey_gc.data)
                listN.extend([routerid])
                nodey_gc.data = json.dumps(listN)
                listN = json.loads(nodey_gc.tag)
                listN.extend([routerid])
                nodey_gc.tag = json.dumps(listN)
            else:
                nodey_c = ftree.create_node(
                    stringKey, parent=nodey, data=json.dumps([routerid]))
                ftree.create_node(
                    tag=nodey_c.data, parent=nodey_c, data=nodey_c.data)
                


def groupFilter(node):
    if node.data == ['group']:
        return False
    return True


def path_to_root(node):
    """Return a string representing the path to root for treemap boxes."""
    returnStr = ''
    for i in ftree.rsearch(node.identifier):
        if ftree.get_node(i).tag == 'ROOT':
            returnStr = ftree.get_node(i).tag + returnStr
        else:
            newStr = ftree.get_node(i).tag
            returnStr = '.' + str(newStr) + returnStr
    return returnStr


def find_nid(path, startNode):
    """Return NID for a given path."""
    kids = {c.tag: c.identifier for c in ftree.children(startNode)}
    newNid = kids[path.pop(0)]
    if len(path) > 1:
        find_nid(path, newNid)
    else:
        return newNid


def treeGraphBuilder(f=None):
    """Parse tree to create lists used by treemap to create the map."""
    global labels
    global ids
    global parents
    global values
    labels = []
    ids = []
    parents = []
    values = []
    for x in ftree.expand_tree(sorting=False, filter=f):
        node = ftree.get_node(x)
        if node.tag == 'ROOT':
            values.extend([0])
            labels.extend([''])
            ids.extend(['ROOT'])
            parents.extend([''])
        else:
            if f is None:
                values.extend([len(node.data)])
                labels.extend([node.tag])
                dotNotation = path_to_root(node)
                ids.extend([dotNotation])
                dotNoteParent = path_to_root(ftree.parent(node.identifier))
                parents.extend([dotNoteParent])
            else:  # SStrips group out of lists
                if 'group' in node.data:
                    values.extend([len(node.data)-1])
                else:
                    values.extend([len(node.data)])
                if len(ftree.children(node.identifier)) == 0:  # a leaf node
                    tagCopy = node.tag#.copy()
                    if 'group' in tagCopy:
                        # tagCopy.remove('group')
                        str.replace('group', '')
                    labels.extend([tagCopy])
                else:
                    labels.extend([node.tag])
                dotNotation = path_to_root(node)
                ids.extend([dotNotation])
                dotNoteParent = path_to_root(ftree.parent(node.identifier))
                parents.extend([dotNoteParent])


for chunk in chunks(router_ids, 100):
    router_list = ','.join(chunk)
    url = f'{server}/configuration_managers/?router__in={router_list}&expand=router&limit=500'
    req = session.get(url, headers=headers)
    if req.status_code < 300:
        managers = req.json()['data']
        for manager in managers:
            config = manager['configuration'][0]
            conf_parser_tree(manager['router']['id'], config, rootNode)
            config['id'] = manager['router']['id']
            router_conf_store[manager['router']['id']] = config
    else:
        print(f'Error {req}')
        sys.exit(1)


conf_parser_tree('group', group_config[0], rootNode)
treeGraphBuilder()


fig = px.treemap(
    names=labels,
    parents=parents,
    ids=ids,
    values=values,
    maxdepth=5,  # Sets how many boxes deep are visible
    width=800,
    height=800,
    title=f"Configuration Breakdown of Devices in Group {group_id}",
    color_discrete_map={'*': 'lightgrey'}
    # textinfo = "label+value+percent parent+percent entry+percent root",
)

fig.update_traces(root_color="lightgrey")
fig.update_layout(clickmode='event+select')
fig.update_layout(margin=dict(
    t=50, l=25, r=25, b=25),  uniformtext=dict(minsize=12, mode='hide'),)

#fig.show(renderer="browser")  # To run without server
#ftree.save2file('config_layer_analysis.txt') #Saves ftree to a file


# The below code runs the treemap in a server.
app = dash.Dash()
app.layout = html.Div([
    dcc.Checklist(id='checklist',
                  options=[
                      {'label': 'Group', 'value': 'Group'},
                      {'label': 'Default (Firmware)', 'value': 'Default'}
                  ],
                  value=['Group']
                  ),
    html.Div([dcc.Graph(figure=fig, id='config_layers')]),
    html.Div([
        dcc.Textarea(
            id='textarea',
            placeholder='Enter a value...',
            value=str(ftree.to_dict()),#str(json.loads(ftree.to_json())),
            style={'width': '100%'},
            readOnly=True
        )
    ]),
    html.Button('Delete', id='del_but', n_clicks=0),
])
lastCheck = ['Group']


@app.callback(Output(component_id='config_layers',
                     component_property='figure'),
              [Input(component_id='checklist', component_property='value')])
def graph_update(checklist_value):
    """stop."""
    global lastCheck
    print(checklist_value)
    # If group was checked
    if ('Group' in checklist_value) and ('Group' not in lastCheck):
        treeGraphBuilder(f=None)
    # If group was unchecked
    elif (('Group' not in checklist_value) and ('Group' in lastCheck)):
        treeGraphBuilder(f=groupFilter)
    fig = px.treemap(
        names=labels,
        parents=parents,
        ids=ids,
        values=values,
        maxdepth=5,  # Sets how many boxes deep are visible
        #width=800,
        #height=800,
        title=f"Configuration Breakdown of Devices in Group {group_id}",
        color_discrete_map={'*': 'lightgrey'}
    )
    fig.update_traces(root_color="lightgrey")
    fig.update_layout(clickmode='event+select')
    fig.update_layout(margin=dict(
        t=50, l=25, r=25, b=25),  uniformtext=dict(minsize=12, mode='hide'),)
    lastCheck = checklist_value
    return fig


@app.callback(
    Output('textarea', 'value'),
    Input('config_layers', 'clickData'))
def display_click_data(clickData):
    if clickData is not None:
        path = clickData["points"][0]['id']
        if path == 'ROOT':
            return str(ftree.to_dict())
        else:
            newRoot = find_nid(path.split('.')[1:], "ROOT")
            return str(ftree.to_dict(nid=newRoot))


app.run_server(debug=True, use_reloader=False)
