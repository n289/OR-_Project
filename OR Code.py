#!/usr/bin/env python
# coding: utf-8

# In[1]:


from gerrychain import Graph


# In[2]:


# Read Alabama county graph from the json file "AL_county.json"
filepath = 'C:\\Users\\blrod\\Downloads\\districting-data-2020-county\\'
filename = 'ALL_county.json'

# GerryChain has a built-in function for reading graphs of this type:
G = Graph.from_json( filepath + filename )


# In[3]:


# For each node, print the node #, county name, population, and lat-long coordinates
for node in G.nodes:
    name = G.nodes[node]["NAME20"]
    population = G.nodes[node]['P0010001']
    G.nodes[node]['TOTPOP'] = population
    
    # query lat and long coordinates 
    G.nodes[node]['C_X'] = G.nodes[node]['INTPTLON20']  #longitude of county's center
    G.nodes[node]['C_Y'] = G.nodes[node]['INTPTLAT20']  #latitude of county's center
    
    print("Node",node,"is",name,"County, which has population",population,"and is centered at (",G.nodes[node]['C_X'],",",G.nodes[node]['C_Y'], ")")


# In[4]:


pip install geopy


# In[5]:


from geopy.distance import geodesic

# create distance dictionary
dist = { (i,j) : 0 for i in G.nodes for j in G.nodes }
for i in G.nodes:
    for j in G.nodes:
        loc_i = (G.nodes[i]['C_Y'],G.nodes[i]['C_X'])
        loc_j = (G.nodes[j]['C_Y'],G.nodes[j]['C_X'])
        dist[i,j] = geodesic(loc_i,loc_j).miles


# In[6]:


# Let's impose a 1% population deviation (+/- 0.5%)
deviation = 0.01

import math
k = 7          # number of districts
total_population = sum(G.nodes[node]['TOTPOP'] for node in G.nodes)

L = math.ceil((1-deviation/2)*total_population/k)
U = math.floor((1+deviation/2)*total_population/k)
print("Using L =",L,"and U =",U,"and k =",k)


# In[7]:


import gurobipy as gp
from gurobipy import GRB

# create model 
m =gp.Model()

# create x[i,j] variable which equals one when county i 
#    is assigned to (the district centered at) county j
x =m.addVars( G.nodes, G.nodes, vtype=GRB.BINARY)


# In[8]:


# objective is to minimize the moment of inertia: sum (d^2 * p * x over all i and j)
m.setObjective( gp.quicksum( dist[i,j] * dist[i,j] *G.nodes[i]['TOTPOP'] * x[i,j] for i in G.nodes for j in G.nodes ), GRB.MINIMIZE)


# In[9]:


# add constraints saying that each county i is assigned to one district
m.addConstrs( gp.quicksum( x[i,j] for j in G.nodes ) == 1 for i in G.nodes)

# add constraint saying there should be k district centers
m.addConstr( gp.quicksum( x[j,j] for j in G.nodes ) == k )

# add constraints that say: if j roots a district, then its population is between L and U.
m.addConstrs( gp.quicksum( G.nodes[i]['TOTPOP'] * x[i,j] for i in G.nodes ) >= L * x[j,j] for j in G.nodes )
m.addConstrs( gp.quicksum( G.nodes[i]['TOTPOP'] * x[i,j] for i in G.nodes ) <= U * x[j,j] for j in G.nodes )

# add coupling constraints saying that if i is assigned to j, then j is a center.
m.addConstrs( x[i,j] <= x[j,j] for i in G.nodes for j in G.nodes )

m.update()


# In[10]:


# add contiguity constraints
import networkx as nx
DG = nx.DiGraph(G)

#add flow variables
f = m.addVars( DG.edges, G.nodes ) # f[i,j,v] = flow across arc (i,j) that is sent from source/root v

#add constraints saying that if node i is assigned to node j
# then node i must consume one unit of node j's flow
m.addConstrs( gp.quicksum( f[u,i,j] - f[i,u,j] for u in G.neighbors(i) ) == x[i,j] for i in G.nodes for j in G.nodes if i != j )

# add constraints saying that node i can recieve flow of type j
#only if node i is assigned to node j
M = G.number_of_nodes() - 1
m.addConstrs( gp.quicksum( f[u,i,j] for u in G.neighbors(i) ) <= M * x[i,j] for i in G.nodes for j in G.nodes if i != j )

#add constraints saying that j cannot recieve flow of its own type
m.addConstrs( gp.quicksum( f[u,j,j] for u in G.neighbors(j) ) == 0 for j in G.nodes )
             


# In[11]:


# solve, making sure to set a 0.00% MIP gap tolerance(!)
m.Params.MIPGap = 0.0

m.optimize()


# In[12]:


# print the objective value
print(m.objVal)

# retrieve the districts and their populations
#    but first get the district "centers"

centers = [ j for j in G.nodes if x[j,j].x > 0.5 ]

districts = [ [i for i in G.nodes if x[i,j].x > 0.5] for j in centers]
district_counties = [ [ G.nodes[i]["NAME20"] for i in districts[j] ] for j in range(k)]
district_populations = [ sum(G.nodes[i]["TOTPOP"] for i in districts[j]) for j in range(k) ]

# print district info
for j in range(k):
    print("District",j,"has population",district_populations[j],"and contains counties",district_counties[j])
    print("")


# In[13]:


# Let's draw it on a map
import geopandas as gpd


# In[14]:


# Read Alabama county shapefile from "AL_county.shp"
filepath = 'C:\\Users\\blrod\\Downloads\\districting-data-2020-county\\'
filename = 'AL_county.shp'

# Read geopandas dataframe from file
df = gpd.read_file( filepath + filename )


# In[15]:


# Which district is each county assigned to?
assignment = [ -1 for i in G.nodes ]

labeling  = { i : -1 for i in G.nodes }
for j in range(k):
    district = districts[j]
    for i in district:
        labeling[i] = j

# Now add the assignments to a column of the dataframe and map it
node_with_this_geoid = {G.nodes[i]['GEOID20'] : i for i in G.nodes}

#pick a position u in the dataframe
for u in range(G.number_of_nodes()):
    
    geoid = df['GEOID20'][u]
    
    # what node in G has thus geoid?
    i = node_with_this_geoid[geoid]
    
    # position u in the dataframe should be given
    # the same district # that county i has in 'labeling'
    assignment[u] = labeling[i]

#now add the assignments to a column of our dataframe and then map it
df['assignment'] = assignment

my_fig = df.plot(column='assignment').get_figure()


# In[ ]:




