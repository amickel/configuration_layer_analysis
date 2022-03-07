# configuration_layer_analysis

This script takes Cradlepoint API v2 keys and a group ID as input and outputs a treemap showing the configuration layers of every device in a group in an intutive 
and interactive manner.
This is useful when trying to find routers in a group that have a conflicting configuration for configuation cleanup. 

This script uses the plotly and dash libraries to diplay the treemap. The data is stored in a tree structure using the treelib library. Note that a json print out of the current tree 
selection is also included on the page. 

![image](https://user-images.githubusercontent.com/51377202/157099755-51ed3d18-e304-43b9-bd4f-80636ab92439.png)

### Configuration options: ###

* Group checkbox: if the group checkbox is checked group level configuraitons will be included in the treemap.
* By default the maxdepth is set to 5. This hides configuration keys more than 5 levels deep so as to reduce noise. As the user dives into a specific branch more keys will appear.This can be changed in the source code to accomadate more complex environements. 
* To automatically save a print out of the underlying tree structure to a file uncomment the line "ftree.save2file('config_layer_analysis.txt')"


### To get started ###
plugin your api keys and group ID and run the script. Navigate to http://127.0.0.1:8050/ to see the treemap. 

### Todo: ###
* Add text boxes for api keys and group ID on dash page.
* Add functionality to the "delete" button.
* Add a button to save the tree structure to a file.
* Make the json print out a pretty print.
* Add unit tests.
* Add functionality to the default checkbox. 
