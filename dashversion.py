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
import dash_bootstrap_components as dbc
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
# PERSONAL ACCOUNT
'''
headers = {
            "X-CP-API-ID": os.environ.get("X-CP-API-ID", ""),
            "X-CP-API-KEY": os.environ.get("X-CP-API-KEY", ""),
            "X-ECM-API-ID": os.environ.get("X-ECM-API-ID", ""),
            "X-ECM-API-KEY": os.environ.get("X-ECM-API-KEY", ""),
            'Content-Type': 'application/json'
           }

group_id = 282021

'''

# SUPPORTS ACCOUNT
#Autofill the headers if they exist as environmental variables 
headers = {
            "X-CP-API-ID": os.environ.get("X-CP-API-ID-Support", ""), #change to match how your environmental variable have been set. 
            "X-CP-API-KEY": os.environ.get("X-CP-API-KEY-Support", ""),
            "X-ECM-API-ID": os.environ.get("X-ECM-API-ID-Support", ""),
            "X-ECM-API-KEY": os.environ.get("X-ECM-API-KEY-Support", ""),
            'Content-Type': 'application/json'
           }

group_id = ""# 145120


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
    response = session.get(url, headers=headers)
    if response.status_code != 200:
        return str(response.status_code) + ": " + str(response.text)
    firmware = response.json()['target_firmware']
    url = f'{firmware}default_configuration/'
    req = session.get(url, headers=headers)
    if req.status_code < 300:
        return req.json()
    else:
        print(f'Error {req}')
        return str(req.status_code) + ": " + str(req.text)


def conf_parser_tree(routerid, config, head):
    """Add keys from a single router config to conf_keys_dict."""
    tags = {c.tag: c.identifier for c in ftree.children(head.identifier)}
    for key in config.keys():
        nodey = 0
        if key in tags:
            nodey = ftree.get_node(tags[key])
            listN = json.loads(nodey.data)
            listN.extend([routerid])
            nodey.data = json.dumps(listN)
        else:
            nodey = ftree.create_node(
                key, parent=head, data=json.dumps([routerid]))
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


def my_to_dict(tree, nid=None):
    """Transform the whole tree into a dict."""
    nid = tree.root if (nid is None) else nid
    ntag = tree[nid].tag
    tree_dict = {ntag: {}}
    if tree[nid].expanded:
        queue = [tree[i] for i in tree[nid].fpointer]
        for elem in queue:
            if len(tree.children(elem.identifier)) > 0:
                tree_dict[ntag].update(my_to_dict(tree, elem.identifier))
            else:
                tree_dict[ntag] = {elem.tag}
        return tree_dict


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
                values.extend([len(json.loads(node.data))])
                labels.extend([node.tag])
                ids.extend([node.identifier])
                parents.extend([ftree.parent(node.identifier).identifier])
            else:  # Strips group out of lists
                if 'group' in node.data:
                    values.extend([len(json.loads(node.data))-1])
                else:
                    values.extend([len(json.loads(node.data))])
                if len(ftree.children(node.identifier)) == 0:  # a leaf node
                    tagCopy = node.tag
                    if ', \"group\"' in tagCopy:
                        tagCopy = tagCopy.replace(', \"group\"', '')
                    labels.extend([tagCopy])
                else:
                    labels.extend([node.tag])
                ids.extend([node.identifier])
                parents.extend([ftree.parent(node.identifier).identifier])

'''
    This dict stores every key value pair of every router config with a list
    of which router id's have a config for any given key or value. Example
    { firewall : router_ids: [182828, 34112, 345311], remote_admin:{...},
    ssh_admin: {...},  ....} The above means that there are 3 routers in the
    group that have a firewall configuration. The next keys, remote admin and
    so on, will have their own router_ids list until reaching each final value
    in the config.
'''
router_conf_store = {}  # Every router's config stored as a seperate entry
ftree = Tree()
rootNode = ftree.create_node("ROOT", "ROOT")
delete_section = ''  # Section of config the delete button deletes.


# The 4 lists below are what plotly uses to create the boxes
labels = []
ids = []
parents = []
values = []

def builder():
    firmware_config = get_default_conf(group_id)  # The default configuration
    if type(firmware_config) == str:#something went wrong, return error string
        return firmware_config
    group_config = get_group_conf(group_id)  # The group configuration
    router_ids = get_router_ids(group_id)  # All router IDs in the group
    print('There are', len(router_ids), 'routers in this group.')
    
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
app.layout = html.Div(
    [
      dbc.Alert(
            "",
            id="alert",
            dismissable=True,
            fade=False,
            is_open=False,
      ),
      dcc.Input(
            id="X-CP-API-ID",
            type="text",
            placeholder="X-CP-API-ID",
            value=headers['X-CP-API-ID']
        ),
      dcc.Input(
            id="X-CP-API-KEY",
            type="text",
            placeholder="X-CP-API-KEY",
            value=headers['X-CP-API-KEY']
        ),
      dcc.Input(
            id="X-ECM-API-ID",
            type="text",
            placeholder="X-ECM-API-ID",
            value=headers['X-ECM-API-ID']
        ),
      dcc.Input(
            id="X-ECM-API-KEY",
            type="text",
            placeholder="X-ECM-API-KEY",
            value=headers['X-ECM-API-KEY']
        ),
      dcc.Input(
            id="Group-ID",
            type="number",
            placeholder="Group-ID",
        ),
      html.Button('Submit', id='submit', n_clicks=0),
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
                value=str(my_to_dict(ftree)),
                style={'width': '100%'},
                readOnly=True
            )
        ]),
      html.Button('Delete', id='del_but', n_clicks=0),
    ]
)
lastCheck = ['Group']


@app.callback(
                Output('config_layers', 'figure'),
                Input('checklist', 'value'),
                Input('del_but', 'n_clicks'),
                Input('X-CP-API-ID', 'value'),
                Input('X-CP-API-KEY', 'value'),
                Input('X-ECM-API-ID', 'value'),
                Input('X-ECM-API-KEY', 'value'),
                Input('Group-ID', 'value'),
                Input('submit', 'n_clicks')
            )
def graph_update(checklist_value, btn1, XCPAPIID, XCPAPIKEY, XECMAPIID,
                 XECMAPIKEY, groupid, subbut):
    """Update treemap to include or exclude group data."""
    ctx = dash.callback_context
    global lastCheck
    global group_id
    if ctx.triggered[0]['prop_id'] == 'del_but.n_clicks' and ctx.triggered[0][
            'value'] != 0:
        print('activiate delete')
    elif ctx.triggered[0]['prop_id'] == 'submit.n_clicks' and XCPAPIID and \
            XCPAPIKEY and XECMAPIID and XECMAPIKEY and groupid:
        # update headers
        headers["X-CP-API-ID"] = ctx.inputs['X-CP-API-ID.value']
        headers["X-CP-API-KEY"] = ctx.inputs['X-CP-API-KEY.value']
        headers["X-ECM-API-ID"] = ctx.inputs['X-ECM-API-ID.value']
        headers["X-ECM-API-KEY"] = ctx.inputs['X-ECM-API-KEY.value']
        group_id = ctx.inputs['Group-ID.value']
        build_return = builder()
        if type(build_return) == str:
            #alert(build_return)
            return

    # If group was checked
    if ('Group' in checklist_value) and ('Group' not in lastCheck):
        treeGraphBuilder(f=None)
    # If group was unchecked
    elif (('Group' not in checklist_value) and ('Group' in lastCheck)):
        def groupFilter(node):
            if node.data == ['group']:
                return False
            return True
        treeGraphBuilder(f=groupFilter)
    fig = px.treemap(
        names=labels,
        parents=parents,
        ids=ids,
        values=values,
        maxdepth=5,  # Sets how many boxes deep are visible
        title=f"Configuration Breakdown of Devices in Group {group_id}",
        color_discrete_map={'*': 'lightgrey'}
    )
    fig.update_traces(root_color="lightgrey")
    fig.update_layout(clickmode='event+select')
    fig.update_traces(
        hovertemplate='label=%{label}<br>count=%{value}<br>parent=%{parent}')
    fig.update_layout(margin=dict(
        t=50, l=25, r=25, b=25),  uniformtext=dict(minsize=12, mode='hide'),)
    lastCheck = checklist_value
    return fig


@app.callback(
    Output('textarea', 'value'),
    Input('config_layers', 'clickData'))
def display_click_data(clickData):
    """Update text area based on current selection in treemap."""
    if clickData is not None:
        global delete_section
        newRoot = clickData["points"][0]['id']
        delete_section = newRoot
        return str(my_to_dict(ftree, newRoot))
'''
@app.callback(
    Output("alert", "is_open"),
    Input("alert-toggle", "n_clicks"))
def toggle_alert(n, is_open):
    if n:
        return not is_open
    return is_open
'''
app.run_server(debug=True, use_reloader=False)
