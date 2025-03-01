import pandas as pd
import numpy as np
import os
import sys
import urllib
import argparse
from bs4 import BeautifulSoup
from tqdm import tqdm
import glob
import shutil 
import numpy as np 
import pandas as pd 
from sklearn import *
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_samples, silhouette_score

def ParseArguments():
    parser = argparse.ArgumentParser(description = 'Apply secondary cutoff filtering and one hot encode based on desired variable (must be a column name in uniprot annotation sheet).')

    parser.add_argument('annotated_file', help = 'The name of the annotated file created by uniprot_annotation script.')

    parser.add_argument('-pv', '-p-value_cutoff', help = 'Desired p-value cutoff for secondary filtering (default = <=0.05).', type = float, default = 0.05)

    parser.add_argument('-fc', '-fold-change_cutoff', help = 'Desired fold-change cutoff value (default = >=1.5).', type = float, default = 1.5)

    parser.add_argument('-et', '-encoding_target', help = 'Target for one-hot encoding analysis. Must be a column name in uniprot annotated file generated from uniprot_annotation script (default = Domains).', type = str, default = 'Domains')

    parser.add_argument('-sc', '-score_cutoff', help = 'Desired cutoff for andromeda score. General values: >40 = high confidence, 10-40 = medium confidence, <10 = low confidence. Default = 10', type = float, default = 10)

    parser.add_argument('-bh', '-bh_correction', help = 'Optionally, implement the Benjamini-Hochberg correction to filter proteins based on a FDR associated with P-Value testing. Supply a desired FDR cutoff as an argument. (i.e. 0.05) *NOTE* This means that of the data you filter 5 percent of it will be false-positives! Set a lower FDR value for more stringent filtering. Default = 0.0', type = float, default = 0.0)

    parser.add_argument('-kmeans', '-kmeans_clustering', help = 'Argument for kmeans clustering. Default = False', type = str, default = False)

    parser.add_argument('-top_d', '-top_domains', help = 'Desired number of top domains to pass on to k-means clustering. Default = 100', type = int, default = 100)

    parser.add_argument('-e_clusters', '-explicit_clusters', help = 'Explicitly set the desired number of clusters for k-means clustering. (default = False, uses optimized k)', type = int, default = False)

    args = parser.parse_args()

    return args

def FindIdealNumberOfClusters(Data, lower_lim, upper_lim, spacing):

    clusters_to_try = np.arange(lower_lim, upper_lim + spacing, spacing)
    silhouette_dict = {}

    for cluster in clusters_to_try:
        clusterer = KMeans(n_clusters=cluster, random_state=10)
        clusterer.fit(Data)

        cluster_labels = clusterer.predict(Data)
        silhouette_avg = silhouette_score(Data, cluster_labels)
        silhouette_dict.update({cluster:silhouette_avg})

    return silhouette_dict

def PlotBarCharts():

    return None

args = ParseArguments()
file_arg = args.annotated_file
pv_cut_arg = args.pv
fc_cut_arg = args.fc
et_arg = args.et
kmeans_arg = args.kmeans
sc_cut_arg = args.sc
top_domains_arg = args.top_d
bh_cutoff_arg = args.bh
e_clusters_arg = args.e_clusters

file_df = pd.read_csv(file_arg, index_col = 0)

#test Benjamini-Hochberg
if bh_cutoff_arg != 0.0:
    print('Implementing Benjamini-Hochberg corrections ... ')
    print('FDR set to ' + str(bh_cutoff_arg))
    file_df['P-Value Ranks'] = file_df['P-Value'].rank(axis = 0) 
    file_df['BH Correction'] = (file_df['P-Value Ranks']/len(file_df))*bh_cutoff_arg
    BH_filter_list = []
    for index, row in file_df.iterrows():
        test_stat = row['BH Correction'] - row['P-Value']
        if test_stat > 0:
            BH_filter_list.append(row['P-Value Ranks'])
        else:
            pass
    
    maximum_rank_cutoff = max(BH_filter_list)
    bh_cutoff_filter = file_df['P-Value Ranks'] <= maximum_rank_cutoff

#filtering
if bh_cutoff_arg == 0.0:
    print('No BH-correction implemented ... P-Values greater than ' + str(pv_cut_arg) + ' filtered out.')
    pval_filter = file_df['P-Value'] <= pv_cut_arg
    file_df = file_df[pval_filter]
else:
    file_df = file_df[bh_cutoff_filter]

fc_filter = file_df['Imputed Average'] >= fc_cut_arg
sc_filter = file_df['Score'] >  sc_cut_arg
file_df = file_df[fc_filter & sc_filter]

#domain cleanup and generation of non-redundant encoding target list
if et_arg == 'Domains':
    master_domain_list = []
    for index, row in file_df.iterrows():
        encoding_target = str(row[et_arg])
        encoding_target = encoding_target.split(', ')
        clean_encoding_target = []
        clean_nr_encoding_target = []
        #remove site of domain
        for item in encoding_target:
            if ' {' in item:
                item = item.split(' {')
                item = item[:-1]
                item = ''.join(item)
                clean_encoding_target.append(item)
            else:
                clean_encoding_target.append(item)
        #remove redundancies in the list
        for domain in clean_encoding_target:
            domain_list = domain.split()
            try:
                if int(domain_list[-1]) in range(1, 100):
                    nr_domain_name = ' '.join(domain_list[:-1])
                else:
                    nr_domain_name = domain
            except:
                nr_domain_name = domain
            clean_nr_encoding_target.append(nr_domain_name)
        
        clean_nr_encoding_target = list(set(clean_nr_encoding_target))
        file_df.loc[index, 'NR Domains'] = ', '.join(clean_nr_encoding_target)
        for thing in clean_nr_encoding_target:
            master_domain_list.append(thing)
    
    master_domain_list = list(set(master_domain_list))

    #one hot encoding
    encoded_df = pd.get_dummies(master_domain_list)
    encoded_df = encoded_df.reindex(file_df['Fasta headers'])
    encoded_df = encoded_df.fillna(0.0)

    for index, row in file_df.iterrows():
        domain_list = row['NR Domains'].split(', ')
        protein_id = row['Fasta headers']
        for element in domain_list:
            encoded_df[element][protein_id] = 1
    
    encoded_df = encoded_df[encoded_df['nan'] != 1.0]
    domain_analysis_df = pd.DataFrame(encoded_df.sum(), columns = ['Domain Sum'])
    total_domain_count = domain_analysis_df['Domain Sum'].sum()
    number_of_domains = len(domain_analysis_df)
    total_protein_count = len(encoded_df)
    n_largest = pd.DataFrame(domain_analysis_df['Domain Sum'].nlargest(top_domains_arg))
    n_largest_sum = n_largest['Domain Sum'].sum()
    percentage_of_dataset = 100*(n_largest_sum/total_domain_count)
    print(str(top_domains_arg) + ' top domains composes ' + str(percentage_of_dataset) + ' percent of total domains')
    encoded_df = encoded_df[n_largest.index]
    encoded_df = encoded_df.loc[(encoded_df != 0.0).any(1)]
else:
    pass

#kmeans clustering

if kmeans_arg != False:
    if e_clusters_arg == False:
        max_clusters = top_domains_arg - 1
    else:
        max_clusters = e_clusters_arg

    silhouette_dictionary = FindIdealNumberOfClusters(encoded_df, 2, max_clusters, 1)
    keys = list(silhouette_dictionary.keys())
    values = list(silhouette_dictionary.values())

    maximum = max(values)
    value_max_idx = values.index(maximum)
    num_clusters = keys[value_max_idx]

    kmeans = KMeans(n_clusters=num_clusters, random_state=10)
    kmeans.fit(encoded_df)
    cluster_labels = kmeans.predict(encoded_df)

    encoded_df['ClusterLabel'] = cluster_labels
    encoded_df = encoded_df.sort_values('ClusterLabel')

    cluster_domain_dictionaries = {}

    for cluster in cluster_labels:
        tmp_encoded_df = encoded_df[encoded_df['ClusterLabel'] == cluster]
        tmp_encoded_df = tmp_encoded_df.drop(['ClusterLabel'], axis=1)

        tmp_domain_stats = pd.DataFrame(tmp_encoded_df.sum(), columns=['DomainSum'])
        
        tmp_domain_stats = tmp_domain_stats[tmp_domain_stats['DomainSum'] != 0.0]
        tmp_domain_stats.index.name = 'Domain'

        #tmp_domain_stats.plot(kind='bar')

        cluster_domain_dictionaries.update({cluster : tmp_domain_stats.to_dict()})

    encoded_df = pd.DataFrame(encoded_df['ClusterLabel'])
    encoded_df.to_csv('KMeansClustering_' + str(num_clusters) + 'Clusters.csv')

    file_df_fasta_indexed = file_df.set_index('Fasta headers')
    detailed_clustered_df = file_df_fasta_indexed.loc[encoded_df.index]

    detailed_clustered_df = detailed_clustered_df.merge(encoded_df, left_index = True, right_index = True)

    detailed_clustered_df.to_csv('DetailedClusteredDF.csv')
else:
    pass




