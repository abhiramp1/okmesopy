# mesonettools.py
#
# Abhiram Pamula (apamula@okstate.edu)
# Ben Rubinstein (brubinst@hawk.iit.edu)
#
# last updated: 08/10/2022
#
# contains the MesonetTools class
import pandas as pd
import numpy as np
from okmesopy import MesonetDownloader
from geopy import distance

class MesonetTools:
    '''
    The MesonetTools class contains methods to assist with processing time
        series generated by the MesonetDownloader class.
    '''

    def __init__(self, verbose=False):
        '''
        init method for the MesonetTools class

        arguments:
            verbose (bool): if true write detailed debugging to stdout
        '''
        self.verbose=verbose
        # these are used internally when replacing data
        self.nondatcols=['STID','STNM','TIME','DATE','DATETIME']
        self.errorcodes=[-994,-995,-996,-997,-998,-999]


    def replace_errors(self,df,code=1,column=None):
        '''
        Replace error codes in the dataset with NaN.

        Description of error codes:
            -999 - flagged bad by QA routines
            -998 - sensor not installed
            -997 - missing calibration coefficients
            -996 - station did not report
            -995 - data not reported on this time interval
            -994 - value is too wide to fit in column
        arguments:
            df (DataFrame or dict): the dataframe or dictionary of dataframes
                to be manipulated
            code (int): the specific error code to be replaced, the default 1
                replaces all error codes
            column (str): optional parameter that when specified changes only
                a single column

        returns:
            DataFrame or dict: the modified df object
        '''
        # check if we've been given a dict or dataframe
        if self.is_dict(df)==-1:
            if self.verbose:
                print('Warning: replace_errors() expects a DataFrame or dict'
                      ' not a {}. No actions performed.'.format(type(df)))
        # check that the error code argument is valid
        elif code != 1 and code not in self.errorcodes:
            if self.verbose:
                print('Warning: {} is not a valid error code. Nothing will'
                      ' be replaced. Use 1 or do not pass in a code argument'
                      ' to replace all error codes or enter one of the'
                      ' following: {}.'.format(code,self.errorcodes))
                print('help(MesonetTools.replace_errors) will give a'
                      ' description of the error codes.')
        # if df is a dictionary, recursively call this function for each of its keys
        elif self.is_dict(df)==1:
            for key in df:
                df[key] = self.replace_errors(df[key],code,column)
        # if df is a dataframe
        elif self.is_dict(df)==0:
            if code==1:
                # replace all error codes with NaN
                for i in self.errorcodes:
                    if column is None:
                        # replace for all columns
                        df = df.replace(str(i),np.nan)
                        df = df.replace(i,np.nan)
                    else:
                        # check if the column exists
                        if column in df.columns:
                            # replace for a single column
                            df[column] = df[column].replace(str(i),np.nan)
                            df[column] = df[column].replace(i,np.nan)
                        elif self.verbose:
                            print('Warning: there is no column named {}'
                                  ' in the dataframe. No actions will be'
                                  ' taken.'.format(column))
            # check if code is a valid error code
            else:
                if column is None:
                    # replace for all columns
                    df = df.replace(code,np.nan)
                    df = df.replace(code,np.nan)
                else:
                    # check if the column exists
                    if column in df.columns:
                        # replace for a single column
                        df[column] = df[column].replace(code,np.nan)
                        df[column] = df[column].replace(code,np.nan)
                    elif self.verbose:
                        print('Warning: there is no column named {}'
                              ' in the dataframe. No actions will be'
                              ' taken.'.format(column))
        return df


    def interpolate_missing(self,df,codes=[],column=None):
        '''
        Fills missing data with simple linear interpolation between known
            values
        
        This method will automatically ignore the following columns:
            'STID','STNM','TIME','DATE','DATETIME'

        arguments:
            df (DataFrame or dict): the dataframe or dictionary of dataframes
                to be manipulated
            codes (list): optional parameter that when specified interpolates
                only for the specified codes
            column (str): optional parameter that when specified changes only
                a single column

        returns:
            DataFrame or dict: the modified df object
        '''
        # check if we've been given a dict or dataframe
        if self.is_dict(df)==-1:
            if self.verbose:
                print('Warning: interpolate_missing() expects a DataFrame or'
                      ' dict not a {}. No actions performed.'.format(type(df)))
        # check that at least one error code in the list is valid
        elif codes and all(i not in self.errorcodes for i in codes):
            if self.verbose:
                print('Warning: No valid error codes were entered: {}. No'
                      ' changes will be made. Use an empty list or do not pass'
                      ' in the codes argument to replace all error codes or'
                      ' enter at least one of the following valid error codes:'
                      ' {}'.format(codes,self.errorcodes))
                print('help(MesonetTools.replace_errors) will give a'
                      ' description of the error codes.')
        # if df is a dictionary, recursively call this function for each of its keys
        elif self.is_dict(df)==1:
            for key in df:
                df[key] = self.interpolate_missing(df[key],codes,column)
        else:
            backup = pd.DataFrame()
            if codes:
                # store a backup so we can recovery error codes that shouldn't
                #   be replaced
                backup = df
            # replace all error codes
            df = self.replace_errors(df,column=column)
            if column is None:
                for ncolumn in df.columns:
                    if ncolumn not in self.nondatcols:
                        df[ncolumn] = df[ncolumn].interpolate()
            else:
                df[column] = df[column].interpolate()
            # if there were specific error codes provided, recover the others
            if codes:
                df = self.copy_errors(df,backup,codes,column)
        return df


    def fill_neighbor_data(self,df,downloader,codes=[],column=None):
        '''
        Fills missing data with the value from the geographically closest
            station that has the missing observation
        
        This method will automatically ignore -995 error codes and the
            following columns: 'STID','STNM','TIME','DATE','DATETIME'

        arguments:
            df (DataFrame or dict): the dataframe or dictionary of dataframes
                to be manipulated
            downloader (MesonetDownloader): a MesonetDownloader object is
                required to calculate distances and download new data
            codes (list): optional parameter that when specified interpolates
                only for the specified codes
            column (str): optional parameter that when specified changes only
                a single column

        returns:
            DataFrame or dict: the modified df object
        '''
        # make sure that downloader is a MesonetDownloader object
        if not isinstance(downloader, MesonetDownloader):
            if self.verbose:
                print('Warning: downloader must be an okmesopy.MesonetDownloader'
                      ' object not a {}. No changes will be made.'.format(type(downloader)))
        # check if we've been given a dict or dataframe
        elif self.is_dict(df)==-1:
            if self.verbose:
                print('Warning: fill_neighbor_data() expects a DataFrame or'
                      ' dict not a {}. No actions performed.'.format(type(df)))
        # check that at least one error code in the list is valid
        elif codes and all(i not in self.errorcodes for i in codes):
            if self.verbose:
                print('Warning: No valid error codes were entered: {}. No'
                      ' changes will be made. Use an empty list or do not pass'
                      ' in the codes argument to replace all error codes or'
                      ' enter at least one of the following valid error codes:'
                      ' {}'.format(codes,self.errorcodes))
                print('help(MesonetTools.replace_errors) will give a'
                      ' description of the error codes.')
        # if df is a dictionary, recursively call this function for each of its keys
        elif self.is_dict(df)==1:
            for key in df:
                df[key] = self.fill_neighbor_data(df[key],downloader,codes,column)
        else:
            stid = df.loc[0,'STID']
            print(stid)
            df.set_index(['DATETIME'],inplace=True)
            if not codes:
                codes = self.errorcodes
            # skip -995, no stations will have data on the not sampled intervals
            if -995 in codes: codes.remove(-995)
            for code in codes:
                df = self.replace_errors(df,code,column)
            # replace all error codes
            df = self.replace_errors(df,column=column)
            # create a list of stations sorted by distance
            target_coord = downloader.get_station_coord(stid)
            coord_tuple = list(downloader.metadata.loc[:,['nlat','elon']].itertuples(index = False, name = None))
            for i in coord_tuple:
                if i == target_coord:
                    coord_tuple.remove(i)
            req_loc = downloader.metadata['stid'].loc[downloader.metadata['stid']!=stid]
            station_list=[]
            for i,j in zip(req_loc,coord_tuple):
                station_list.append([i,distance.distance(target_coord,j).miles])
            station_list = sorted(station_list, key = lambda x:(x[1], x[0]))
            stids = [i[0] for i in station_list]
            for station in stids:
                # break when all data has been filled
                if df.isnull().sum().sum()==0:
                    break
                df = self.download_neighbor(df,downloader,station)
            df = df.reset_index()
        return df
                

    def download_neighbor(self,df,downloader,station_id):
        '''
        Helper function that downloads and fills data from a neighboring station

        arguments:
            df (DataFrame): the dataframe with missing data to be filled 
            downloader (MesonetDownloader): a MesonetDownloader object is
                required to download new data
            station_id (str): the station ID for the neighboring station

        returns:
            DataFrame: the modified df object
        '''
        # get a list of missing dates from the 
        missing_dates = list(df[df.isna().any(axis=1)]['DATE'].unique())
        # download data for each of the missing dates
        for miss_date in missing_dates:
            date = pd.to_datetime(miss_date).date()
            neighbor_df = downloader.download_station_data(station_id,date,date)
            if neighbor_df is not None:
                # we don't want to copy over any error codes so replace all of them
                neighbor_df = self.replace_errors(neighbor_df)
                # fill in data
                neighbor_df.set_index(['DATETIME'],inplace=True)
                df = df.fillna(neighbor_df)
        return df


    def copy_errors(self,df,backup,codes,column=None):
        '''
        Helper function that copies error codes back into a dataframe

        arguments:
            df (DataFrame): the dataframe
            backup (DataFrame): a copy of df with error codes still in place 
            codes (list): a list of codes to copy back into df
            column (str): optional parameter that when specified changes only
                a single column

        returns:
            DataFrame: the modified df object
        '''
        # TODO: fix the SettingWithCopyError?
        pd.options.mode.chained_assignment = None
        for code in self.errorcodes:
            if code not in codes:
                if column is not None:
                    df[column].loc[backup[column]==code] = code
                else:
                    for ncolumn in df.columns:
                        df[ncolumn].loc[backup[ncolumn]==code] = code
        pd.options.mode.chained_assignment = 'warn'
        return df


    def is_dict(self,df):
        '''
        MesonetDownloader creates single dataframes and dictionaries of
            dataframes. Returns 1 for dict, 0 for dataframe, and -1 as an
            error code for anything else

        arguments:
            df (DataFrame or dict): the object to type check

        returns:
            int: 1 for a dictionary, 0 for a DataFrame, -1 otherwise
        '''
        if isinstance(df,dict):
            return 1
        elif isinstance(df,pd.DataFrame):
            return 0
        else:
            return -1
