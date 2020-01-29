import requests
import pandas as pd
import glob
import re
import numpy as np
import os
from requests import get
from requests.exceptions import RequestException
from contextlib import closing
from bs4 import BeautifulSoup
from multiprocessing import Pool
import datetime
from sqlalchemy import MetaData
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import create_engine
import sqlite3


engine = create_engine('postgresql+psycopg2://postgres:postgres@localhost:5432/hydrodatahub',
                       echo=False, use_batch_mode=True)


shp_path = r'H:\Projets_communs\2019\SH-XX-XX-XX-HYD-CRU-FREQ-LaGrande\01_Intrants\06_Données_physio\shp'


def hydat_daily2(df, get_flow, to_plot):
    # Deux ou plus stations
    # station_number = "'02TC001' OR STATION_NUMBER='02TC002'"
    # station1 = "'02TC001'"
    # station2 = "'02TC002'"
    # qstr = "SELECT * FROM DLY_FLOWS WHERE STATION_NUMBER=%s OR STATION_NUMBER=%s\n" %(station1, station2)
    # qstr = SELECT * FROM DLY_FLOWS WHERE STATION_NUMBER='02TC001' OR STATION_NUMBER='02TC002'
    # ATTENTION PEUT ETRE TRES LONG

    # print(df)
    # if get_flow == True:
    #     header = "^FLOW\\d+"
    # else:
    #     header = "^LEVEL\\d+"
    header = "^FLOW\\d+" if get_flow == True else "^LEVEL\\d+"

    dly = df[["STATION_NUMBER", "YEAR", "MONTH"]]
    dly.columns = ["STATION_NUMBER", "YEAR", "MONTH"]
    dly
    # value.cols = df.columns[df.filter(regex="^FLOW\\d+")]
    # filter  sur les FLOW
    value = df.filter(regex=header)
    valuecols = value.columns
    # print(dlydata.shape)
    # now melt the data frame for data and flags
    dlydata = pd.melt(df, id_vars=["STATION_NUMBER", "YEAR", "MONTH"], value_vars=valuecols)

    if get_flow is True:
        dlydata["DAY"] = dlydata['variable'].apply(lambda x: np.int8(x[4:]))
    else:
        dlydata["DAY"] = dlydata['variable'].apply(lambda x: np.int8(x[5:]))
    # flowvariable = dlydata["variable"]
    # days = [x[4:6] for x in flowvariable]
    # dlydata["DAY"] = list(map(int, days))
    # censor ambiguous dates (e.g., 31st day for Apr, Jun, Sept, Nov)
    d = dlydata.loc[dlydata["MONTH"].isin([4, 6, 9, 11]) & (dlydata["DAY"] > 30)]
    d30 = d
    # print(d.index[:])
    # print(len(d))#

    if len(d) > 0:
        dlydata = dlydata.drop(d.index).reset_index(drop=True)
    # print(dlydata.shape)

    d = dlydata.loc[(dlydata["MONTH"].isin([2]) &
                     pd.to_datetime(dlydata["YEAR"], format='%Y').dt.is_leap_year &
                     (dlydata["DAY"] > 29))]
    if len(d) > 0:
        dlydata = dlydata.drop(d.index).reset_index(drop=True)
    d29 = d
    # print(dlydata.shape)

    d = dlydata.loc[(dlydata["MONTH"].isin([2]) &
                     ~pd.to_datetime(dlydata["YEAR"], format='%Y').dt.is_leap_year.values &
                     (dlydata["DAY"] > 28))]
    # print(d)
    if len(d) > 0:
        dlydata = dlydata.drop(d.index).reset_index(drop=True)
    d28 = d
    # print(dlydata.shape)
    # print(valuecols)

    # ----------------------------------SYMBOL--------------------------------------------------
    header_sym = "^FLOW_SYMBOL\\d+" if get_flow == True else "^LEVEL_SYMBOL\\d+"
    flag = df.filter(regex=header_sym)
    flagcols = flag.columns
    # print(flagcols)
    # ordonner les flag dans un dataframe
    dlyflags = pd.melt(df, id_vars=["STATION_NUMBER", "YEAR", "MONTH"], value_vars=flagcols)

    if len(d30) > 0:
        dlyflags = dlyflags.drop(d30.index).reset_index(drop=True)
    # print(dlyflags.shape)

    if len(d29) > 0:
        dlyflags = dlyflags.drop(d29.index).reset_index(drop=True)
    # print(dlyflags.shape)

    if len(d28) > 0:
        dlyflags = dlyflags.drop(d28.index).reset_index(drop=True)
    # print(dlyflags.shape)
    # -----------------------------------END SYMBOL---------------------------------------------

    # transform date
    dlydata.insert(loc=1, column='DATE', value=pd.to_datetime(dlydata[['YEAR', 'MONTH', 'DAY']]))
    # ---------------------------------plot the dataframe--------------------------------------
    dlytoplot = dlydata[['DATE', 'value']].set_index('DATE')
    dlydata = dlydata.drop(['YEAR', 'MONTH', 'DAY', 'variable'], axis=1)
    print(dlydata.shape)

    if to_plot == 1:
        dlytoplot.plot()
        return dlytoplot
    else:
        return dlydata


def parse_data_from_hydat_files(source,
                                regions_list=['QC', 'ON', 'NB', 'NL']):
    """
    Get list of all available stations from cehq with station's number and name as value
    """
    cnx = sqlite3.connect(source)

    df1 = pd.read_sql_query("SELECT * FROM STATIONS", cnx)

    df1 = df1[df1['PROV_TERR_STATE_LOC'].isin(regions_list)]
    df1 = df1[['STATION_NUMBER', 'STATION_NAME', 'PROV_TERR_STATE_LOC', 'DRAINAGE_AREA_GROSS', 'LATITUDE', 'LONGITUDE']]
    df1.columns = ['station_number', 'station_name', 'province', 'drainage_area', 'latitude', 'longitude']
    df1.insert(loc=0, column='id_point', value=df1['station_number'])
    df1['id_point'] = df1['station_number'].astype(str)
    df1.insert(loc=3, column='data_type', value='Flow')

    df2 = pd.read_sql_query("SELECT * FROM STN_REGULATION", cnx)
    df = pd.merge(df1, df2, how='left', left_on=['station_number'], right_on=['STATION_NUMBER'])
    df.insert(loc=5, column='regulation', value=df['REGULATED'].map({0: 'Naturel', 1: 'Influencé', np.nan: 'Indisponible'}))
    df_sup1 = df.drop(columns=['YEAR_FROM', 'YEAR_TO', 'REGULATED', 'station_number'])

    meta_sta_hydro = df_sup1.drop(columns=['id_point', 'data_type'])
    meta_sta_hydro = meta_sta_hydro.drop_duplicates()
    meta_sta_hydro.insert(loc=1, column='equivalent_name', value=np.nan)
    meta_sta_hydro.insert(loc=0, column='station_number', value=meta_sta_hydro['STATION_NUMBER'])
    meta_sta_hydro = meta_sta_hydro.drop(columns=['STATION_NUMBER'])
    meta_sta_hydro.insert(loc=0, column='id_point', value=range(2000, 2000 + meta_sta_hydro.shape[0], 1))

    meta_ts = df_sup1.drop(columns=['station_name', 'regulation', 'drainage_area', 'latitude', 'longitude'])
    meta_ts['id_point'] = range(2000, 2000 + meta_sta_hydro.shape[0], 1)
    meta_ts.insert(loc=3, column='time_step', value='1_J')
    meta_ts.insert(loc=4, column='aggregation', value='moy')
    meta_ts.insert(loc=5, column='units', value='m3/s')
    meta_ts.insert(loc=7, column='source', value='HYDAT')

    meta_ts = pd.merge(meta_ts, meta_sta_hydro[['station_number']],
                       left_on='STATION_NUMBER', right_on='station_number', how='left').drop(columns=['station_number'])

    cols = meta_ts.columns.tolist()
    cols = cols[-1:] + cols[:-1]
    meta_ts = meta_ts[cols]

    meta_ts.insert(loc=0, column='id_time_serie', value=range(2000, 2000 + meta_ts.shape[0], 1))
    print(meta_ts.columns)
    print(df.columns)

    # df = pd.merge(df, meta_ts[['id_time_serie', 'STATION_NUMBER']],
    #               left_on='id_point', right_on='STATION_NUMBER', how='left').drop(columns=['id_point'])
    # cols = df.columns.tolist()
    # cols = cols[-1:] + cols[:-1]
    # df = df[cols]

    meta_ts = meta_ts.drop(columns=['STATION_NUMBER','province'])

    meta_ts['start_date'] = np.nan
    meta_ts['end_date'] = np.nan


    # Débit
    list_df = []
    for idx, row in meta_sta_hydro.iterrows():
        numero_station = row['station_number']

        sql = """
               SELECT *
               FROM DLY_FLOWS
               WHERE STATION_NUMBER in
               ("%s"
               )
               """ % (numero_station)
        chunk = pd.read_sql_query(sql, cnx)
        daily_station = hydat_daily2(chunk, True, False)
        daily_station.columns = ['id_time_serie', 'date', 'value']
        daily_station = daily_station.set_index(["date"])
        daily_station.index = pd.to_datetime(daily_station.index)
        daily_station.index = daily_station.index.tz_localize("America/Montreal", ambiguous='infer',
                                                              nonexistent='shift_forward')
        print(row['id_point'])
        daily_station['id_time_serie'] = meta_ts[meta_ts['id_point'] == row['id_point']]['id_time_serie'].values[0]
        daily_station.reset_index(level=0, inplace=True)
        if daily_station['date'].shape[0]>0:
            meta_ts.loc[meta_ts['id_point'] == row['id_point'], 'start_date'] = daily_station.dropna()['date'].iloc[0]
            meta_ts.loc[meta_ts['id_point'] == row['id_point'], 'end_date'] = daily_station.dropna()['date'].iloc[-1]
            list_df.append(daily_station)
        else:
            meta_ts = meta_ts[meta_ts['id_point'] != row['id_point']]
            meta_sta_hydro = meta_sta_hydro[meta_sta_hydro['id_point'] != row['id_point']]
    df = pd.concat(list_df)

    print(meta_sta_hydro.head())
    print(meta_ts.head())
    print(df.head())
    return [meta_sta_hydro, meta_ts, df]


def load_files_from_hydat(stations_list,
                         store='tmp'):
    """

    """


def delete_files_in_store(store='tmp'):
    import os
    import shutil
    for root, dirs, files in os.walk(store):
        for f in files:
            os.unlink(os.path.join(root, f))
        for d in dirs:
            shutil.rmtree(os.path.join(root, d))


def df_update_index_basins(df=None):
    """

    """
    # query on station_number field (unique field for CEHQ only)
    df_db = pd.read_sql("""
    SELECT id_point, station_number FROM basins    
    """, con=engine, index_col='station_number')
    print(df_db.shape[0])
    if df_db.shape[0] > 0:
        id_point_new = df_db['id_point'].max() + 1
        # replace df's  index with the one from database
        df = df.set_index('station_number')
        print(df[['id_point']].head())
        print(df_db[['id_point']].head())
        df_index = pd.merge(df[['id_point']], df_db[['id_point']], left_index=True, right_index=True)
        df_index.to_csv('/home/slanglois/PycharmProjects/flask-hydrodatahub/test.csv')
        dict_index = df_index[['id_point_x', 'id_point_y']].set_index('id_point_x')
        df['id_point'].update(df_db['id_point'])

        df.loc[~df.index.isin(df_db.index)]['id_point'] = range(id_point_new, id_point_new +
                                                                df.loc[~df.index.isin(df_db.index)]['id_point'].shape[0], 1)
        df = df.reset_index()
    return df, dict_index


def df_update_index_ts(df=None):
    """

    """
    # query on station_number field (unique field for CEHQ only)
    df_db = pd.read_sql("""
    SELECT * FROM meta_ts    
    """, con=engine, index_col=['id_point', 'data_type', 'time_step',
                                'aggregation', 'units', 'source'])
    print(df_db.shape[0])
    if df_db.shape[0] > 0:
        id_point_new = df_db['id_time_serie'].max() + 1
        # replace df's  index with the one from database
        df = df.set_index(['id_point', 'data_type', 'time_step',
                            'aggregation', 'units', 'source'])
        df_index = pd.merge(df[['id_time_serie']], df_db[['id_time_serie']], left_index=True, right_index=True)
        dict_index = df_index[['id_time_serie_x', 'id_time_serie_y']].set_index('id_time_serie_x')
        df['id_time_serie'].update(df_db['id_time_serie'])
        print(dict)

        df.loc[~df.index.isin(df_db.index)]['id_time_serie'] = range(id_point_new, id_point_new +
                                                                     df.loc[~df.index.isin(df_db.index)]
                                                                     ['id_time_serie'].shape[0], 1)
        df = df.reset_index()
    return df, dict_index



def df_to_sql(all_dfs, n=200000):
    """

    """
    # Basins metadata
    meta_sta_hydro, meta_ts, df = all_dfs
    meta_sta_hydro.columns = meta_sta_hydro.columns.str.lower()
    meta_ts.columns = meta_ts.columns.str.lower()
    df.columns = df.columns.str.lower()
    meta = MetaData(bind=engine)
    meta.reflect(bind=engine)
    meta_sta_hydro, basins_index = df_update_index_basins(meta_sta_hydro)
    insrt_vals = meta_sta_hydro.to_dict(orient='records')
    table = meta.tables['basins']
    insrt_stmnt = insert(table).values(insrt_vals)
    update_dict = {
        c.name: c
        for c in insrt_stmnt.excluded
        if not c.primary_key
    }
    do_nothing_stmt = insrt_stmnt.on_conflict_do_update(index_elements=['id_point'],
                                                        set_=update_dict)
    engine.execute(do_nothing_stmt)

    # time series metadata
    meta_ts['id_point'].update(basins_index['id_point_y'])
    meta_ts, ts_index = df_update_index_ts(meta_ts)
    insrt_vals = meta_ts.to_dict(orient='records')
    table = meta.tables['meta_ts']
    insrt_stmnt = insert(table).values(insrt_vals)
    update_dict = {
        c.name: c
        for c in insrt_stmnt.excluded
        if not c.primary_key
    }
    do_nothing_stmt = insrt_stmnt.on_conflict_do_update(index_elements=['id_time_serie'],
                                                        set_=update_dict)
    engine.execute(do_nothing_stmt)


    list_df = [df[i:i + n] for i in range(0, df.shape[0], n)]
    table = meta.tables['don_ts']
    constraint = table.primary_key.columns.keys()
    for idx, chunked_df in enumerate(list_df):
        chunked_df['id_time_serie'] = chunked_df['id_time_serie'].replace(ts_index.index,
                                                                          ts_index['id_time_serie_y'])
        try:
            print(str(idx*n))
            # chunked_df['id_time_serie'].update(ts_index['id_time_serie_y'])
            insrt_vals = chunked_df.drop_duplicates().to_dict(orient='records')
            insrt_stmnt = insert(table).values(insrt_vals)
            update_dict = {
                c.name: c
                for c in insrt_stmnt.excluded
                if not c.primary_key
            }
            do_nothing_stmt = insrt_stmnt.on_conflict_do_update(index_elements=constraint,
                                                                set_=update_dict)
            engine.execute(do_nothing_stmt)
        except :
            print('chunk # {} was not inserted correctly in database'.format(idx))


if __name__ == '__main__':


    # load_files_from_cehq(stations)


    all_dfs = parse_data_from_hydat_files('/home/slanglois/Downloads/Hydat_sqlite3_20191016/Hydat.sqlite3',
                                      regions_list=['QC', 'ON', 'NB', 'NL'])
    df_to_sql(all_dfs)
    #delete_files_in_store()

