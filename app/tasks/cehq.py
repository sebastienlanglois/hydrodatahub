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
from config import Config

engine = create_engine(Config.SQLALCHEMY_DATABASE_URI,
                       echo=False)
# engine = db.engine

# Functions
def simple_get(url):
    """
    Attempts to get the content at `url` by making an HTTP GET request.
    If the content-type of response is some kind of HTML/XML, return the
    text content, otherwise return None.
    """
    try:
        with closing(get(url, stream=True)) as resp:
            if is_good_response(resp):
                return resp.content
            else:
                return None

    except RequestException as e:
        log_error('Error during requests to {0} : {1}'.format(url, str(e)))
        return None


def is_good_response(resp):
    """
    Returns True if the response seems to be HTML, False otherwise.
    """
    content_type = resp.headers['Content-Type'].lower()
    return (resp.status_code == 200
            and content_type is not None
            and content_type.find('html') > -1)


def log_error(e):
    """
    Prints log errors
    """
    print(e)


def function_requests(args):
    """
    Function to apply when requesting file from url in args
    :param args:
    :return:
    """
    store, stations = args

    CEHQ_URL = "https://www.cehq.gouv.qc.ca/depot/historique_donnees/fichier/"

    rq = requests.get(CEHQ_URL + os.path.basename(stations[0].strip()) + '_Q.txt')  # create HTTP response object
    if rq.status_code == 200:
        print(store + '/' + stations[0].strip() + '_Q.txt')
        with open(store + '/' + stations[0].strip() + '_Q.txt', 'wb') as f:
            f.write(rq.content)

    rn = requests.get(CEHQ_URL + os.path.basename(stations[0].strip()) + '_N.txt')  # create HTTP response object
    if rn.status_code == 200:
        print(store + '/' + stations[0].strip() + '_N.txt')
        with open(store + '/' + stations[0].strip() + '_N.txt', 'wb') as f:
            f.write(rn.content)


def get_available_stations_from_cehq(url,
                                     regions_list=["%02d" % n for n in range(0, 13)]):
    """
    Get list of all available stations from cehq with station's number and name as value
    """
    print('[' + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + '] Getting all available stations...')

    stations = []
    for region in regions_list:
        file_url = url.replace('$', region)
        raw_html = simple_get(file_url)
        html = BeautifulSoup(raw_html, 'html.parser')

        for list_element in (html.select('area')):
            if list_element['href'].find('NoStation') > 0:
                try:
                    station_infos = list_element['title'].split('-', 1)
                    stations.append(station_infos)

                except RequestException as e:
                    log_error('Error during requests to {0} : {1}'.format(url, str(e)))

    print('[' + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + '] ' + str(len(stations)) + ' available stations...')
    print('[' + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + '] Getting all available stations...done')
    return stations


def get_lecacy_files(PATH1, PATH2):
    folder1 = os.listdir(PATH1)  # folder containing your files
    folder2 = os.listdir(PATH2)  # the other folder
    match = list(set(PATH1) - set(PATH2))

    return [item for item in PATH2 if any(x in item for x in match)]


def load_files_from_cehq(stations_list,
                         apply_func=function_requests,
                         store='tmp'):
    """

    """
    [apply_func([store, stations]) for stations in stations_list]


def del_if_2_cols(lines):
    if (len(lines[0].split())) != 4:
        lines.pop(0)
        del_if_2_cols(lines)
    return lines


def delete_files_in_store(store='tmp'):
    import os
    import shutil
    for root, dirs, files in os.walk(store):
        for f in files:
            os.unlink(os.path.join(root, f))
        for d in dirs:
            shutil.rmtree(os.path.join(root, d))


def parse_metadata_from_cehq_files(stations_list,
                                   store='tmp'):
    """

    """
    # get list of all files
    listeStations = glob.glob(store + "/*.txt")

    # Validate or correct file
    encoding = "ISO-8859-1"
    for file in listeStations:
        with open(file, 'r', encoding=encoding) as f:
            head = f.readlines()[0:21]
            f.close()
        with open(file, 'r', encoding=encoding) as f:
            lines = f.readlines()[22:]
            f.close()
        if lines and (len(lines[0].split())) != 4:
            print(os.path.splitext(os.path.basename(file))[0])
            del_if_2_cols(lines)
            text_fin = head + lines
            with open(file, "w", encoding=encoding)as f:
                f.write(''.join(map(str, text_fin)))
                f.close()

    # One empty list per metadata variable of interest in .txt file
    # cehq metadata from .txt files are quite small in size and will reasonably fit in memory
    list_coordinates = []
    list_area = []
    list_stations = []
    list_type = []
    list_id = []
    list_stations_name = []
    list_regulated = []

    list_stations_number = np.array([os.path.basename(file).split(' ')[0] for file in np.array(stations_list)[:, 0]])
    for file in listeStations:
        try:
            with open(file, encoding=encoding) as f:
                lines = f.readlines()
            # get variable type
            variable_type = os.path.basename(file).replace('.', '_').split('_')[1]
            # Variable is of type : Flow
            if variable_type == 'Q':
                list_type.append('Flow')
            # Variable is of type : Water level
            else:
                list_type.append('Water level')

            # get station's full description (long name)
            full_description_line = lines[2]
            long_name_car_position = np.where(list_stations_number == full_description_line.split()[1])
            long_name = stations_list[long_name_car_position[0][0]][-1].strip()
            list_stations_name.append(long_name)

            # get stations's regulation type
            list_regulated.append(lines[3][15:].split()[-1])

            # get stations's short name
            list_stations.append(full_description_line.split()[1])

            # create stations's unique id
            list_id.append(full_description_line.split()[1] + '_' + variable_type)

            # get drainage area from file
            area = float(lines[3][15:].split()[0])
            list_area.append(area)

            # get latitude and longitude from file
            latlng_coordinates = lines[4][22:-2].split()
            if len(latlng_coordinates) < 5:
                latlng_coordinates = [x for x in latlng_coordinates if x]
                list_coordinates.append([float(latlng_coordinates[0]), float(latlng_coordinates[2])])
            elif len(latlng_coordinates) >= 5:
                latlng_coordinates = [re.sub(r'[^-\d]', '', coord) for coord in latlng_coordinates]
                latlng_coordinates = [x for x in latlng_coordinates if x]
                list_coordinates.append([float(latlng_coordinates[0]) +
                                         float(latlng_coordinates[1]) / 60 +
                                         float(latlng_coordinates[2]) / 3600,
                                         float(latlng_coordinates[3]) -
                                         float(latlng_coordinates[4]) / 60 -
                                         float(latlng_coordinates[5]) / 3600])
        except RuntimeError:
            print("File {} is either incomplete or does not respect CEHQ format. It will be omitted.".format(file))
    print('[' + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + '] Parsing all available stations...done')

    print('[' + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") + '] Making metadata dataframe...')
    metadata_df = pd.DataFrame(np.array([list_id, list_stations, list_stations_name,
                                        list_type, list_regulated, list_coordinates,
                                        list_area]).T,
                                        columns=['STATION_ID', 'numero_station', 'nom_station',
                                                 'type_serie', 'regularisation', 'COORDINATES', 'superficie'])
    metadata_df['latitude'], metadata_df['longitude'] = metadata_df['COORDINATES'].map(lambda x: ':'.join(list(map(str, x)))).str.split(':', 1).str
    metadata_df = metadata_df.drop('COORDINATES', axis=1)
    metadata_df = metadata_df.sort_values(by=['numero_station']).reset_index().drop(['index'], axis=1)
    return metadata_df


def parse_data_from_cehq_files(metadata_df,
                               store='tmp'):
    """

    """
    # get list of all files
    list_stations = glob.glob(store + "/*.txt")

    # Import all .txt files as a dictionary of pandas dataframes
    dict_df = {os.path.splitext(os.path.basename(station))[0] :
               pd.read_csv(station, skiprows=22, delim_whitespace=True,
                           usecols=[1, 2], names=['DATE', 'VALUE'], header=None,
                           encoding='latin1').fillna(np.nan)
               for station in list_stations}


    key_to_delete = []
    for key, value in dict_df.items():
        # Clean value column where characters exists instead of floats
        #value['VALUE'] = value['VALUE'].map(lambda x: float(str(x).lstrip('+-').rstrip('aAbBcC')) if x <= 2.5 else 'false')
        value['VALUE'] = value['VALUE'].apply(pd.to_numeric, errors='coerce')
        # set date as index and assign tz
        value = value.set_index('DATE')
        value.index = pd.to_datetime(value.index)
        # value.index = value.index.tz_localize("Etc/GMT+5", ambiguous='infer', nonexistent='shift_forward')
        value.index = value.index.tz_localize("America/Montreal", ambiguous='infer', nonexistent='shift_forward')
        # set key as index
        value['STATION_ID'] = key
        # reassign corrected values
        dict_df[key] = value

        # if numerical data exists
        if len(value['VALUE'].dropna()) > 0:
            debut = value['VALUE'].dropna().index[0]
            fin = value['VALUE'].dropna().index[-1]
            metadata_df.loc[metadata_df.index[metadata_df['STATION_ID'] == key], 'date_debut'] = debut
            metadata_df.loc[metadata_df.index[metadata_df['STATION_ID'] == key], 'date_fin'] = fin
        # store list of keys where no data is available to delete down the line
        else:
            metadata_df.drop(metadata_df.index[metadata_df['STATION_ID'] == key], inplace=True)
            key_to_delete.append(key)
    # delete keys for which data is empty
    for k in key_to_delete:
        dict_df.pop(k, None)
    # create dataframe of time series
    df = pd.concat(dict_df.values())
    df.reset_index(level=0, inplace=True)

    # Update station metadata (meta_sta_hydro) and time series metadata (meta_ts)
    meta_sta_hydro = metadata_df.drop(columns=['STATION_ID', 'type_serie', 'date_debut', 'date_fin'])
    meta_sta_hydro = meta_sta_hydro.drop_duplicates()
    meta_sta_hydro.insert(loc=2, column='province', value='QC')
    meta_sta_hydro.insert(loc=0, column='id_bassin', value=range(1000, 1000 + meta_sta_hydro.shape[0], 1))
    meta_sta_hydro.insert(loc=3, column='nom_equivalent', value=np.nan)

    meta_ts = metadata_df.drop(columns = ['nom_station', 'regularisation', 'superficie', 'latitude', 'longitude'])
    meta_ts.insert(loc=3, column='pas_de_temps', value='1_J')
    meta_ts.insert(loc=4, column='aggregation', value='moy')
    meta_ts.insert(loc=5, column='unites', value='m3/s')
    meta_ts.insert(loc=8, column='source', value='CEHQ')
    meta_ts = pd.merge(meta_ts, meta_sta_hydro[['id_bassin', 'numero_station']],
                       left_on='numero_station', right_on='numero_station',
                       how='left').drop(columns=['numero_station'])
    cols = meta_ts.columns.tolist()
    cols = cols[-1:] + cols[:-1]
    meta_ts = meta_ts[cols]

    meta_ts.insert(loc=0, column='id', value=range(1000, 1000 + meta_ts.shape[0], 1))
    meta_ts['date_debut'] = pd.to_datetime(meta_ts['date_debut'])
    meta_ts['date_fin'] = pd.to_datetime(meta_ts['date_fin'])

    df = pd.merge(df, meta_ts[['id', 'STATION_ID']],
                 left_on='STATION_ID', right_on='STATION_ID', how='left').drop(columns=['STATION_ID'])
    meta_ts = meta_ts.drop(columns=['STATION_ID'])
    cols = df.columns.tolist()
    cols = cols[-1:] + cols[:-1]
    df = df[cols]

    return [meta_sta_hydro, meta_ts, df]


def df_update_index_basins(df=None):
    """

    """
    # query on station_number field (unique field for CEHQ only)
    df_db = pd.read_sql("""
    SELECT id_bassin, numero_station FROM bassin   
    """, con=engine, index_col='numero_station')
    print(df_db.shape[0])
    if df_db.shape[0] > 0:
        id_point_new = df_db['id_bassin'].max() + 1
        # replace df's  index with the one from database
        df = df.set_index('numero_station')
        df_index = pd.merge(df[['id_bassin']], df_db[['id_bassin']], left_index=True, right_index=True)
        dict_index = df_index[['id_bassin_x', 'id_bassin_y']].set_index('id_bassin_x')
        df['id_bassin'].update(df_db['id_bassin'])

        df.loc[~df.index.isin(df_db.index)]['id_bassin'] = range(id_point_new, id_point_new +
                                                                df.loc[~df.index.isin(df_db.index)]['id_bassin'].shape[0], 1)
        df = df.reset_index()
    else:
        dict_index = pd.DataFrame()
    return df, dict_index


def df_update_index_ts(df=None):
    """

    """
    # query on station_number field (unique field for CEHQ only)
    df_db = pd.read_sql("""
    SELECT * FROM meta_series    
    """, con=engine, index_col=['id_bassin', 'type_serie', 'pas_de_temps',
                                'aggregation', 'unites', 'source'])
    print(df_db.shape[0])
    if df_db.shape[0] > 0:
        id_point_new = df_db['id'].max() + 1
        # replace df's  index with the one from database
        df = df.set_index(['id_bassin', 'type_serie', 'pas_de_temps',
                            'aggregation', 'unites', 'source'])
        df_index = pd.merge(df[['id']], df_db[['id']], left_index=True, right_index=True)
        dict_index = df_index[['id_x', 'id_y']].set_index('id_x')
        df['id'].update(df_db['id'])
        print(dict)

        df.loc[~df.index.isin(df_db.index)]['id'] = range(id_point_new, id_point_new +
                                                                     df.loc[~df.index.isin(df_db.index)]
                                                                     ['id'].shape[0], 1)
        df = df.reset_index()
    else:
        dict_index = pd.DataFrame()

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
    table = meta.tables['bassin']
    insrt_stmnt = insert(table).values(insrt_vals)
    update_dict = {
        c.name: c
        for c in insrt_stmnt.excluded
        if not c.primary_key
    }
    do_nothing_stmt = insrt_stmnt.on_conflict_do_update(index_elements=['id_bassin'],
                                                        set_=update_dict)
    engine.execute(do_nothing_stmt)

    # time series metadata
    print(basins_index)
    if not basins_index.empty:
        meta_ts['id_bassin'].update(basins_index['id_bassin_y'])
    meta_ts, ts_index = df_update_index_ts(meta_ts)
    insrt_vals = meta_ts.to_dict(orient='records')
    table = meta.tables['meta_series']
    insrt_stmnt = insert(table).values(insrt_vals)
    update_dict = {
        c.name: c
        for c in insrt_stmnt.excluded
        if not c.primary_key
    }
    do_nothing_stmt = insrt_stmnt.on_conflict_do_update(index_elements=['id'],
                                                        set_=update_dict)
    engine.execute(do_nothing_stmt)


    list_df = [df[i:i + n] for i in range(0, df.shape[0], n)]
    table = meta.tables['don_series']
    constraint = table.primary_key.columns.keys()
    for idx, chunked_df in enumerate(list_df):
        if not ts_index.empty:
            chunked_df['id'] = chunked_df['id'].replace(ts_index.index,
                                                                          ts_index['id_y'])
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


def main():
    root_path = os.path.abspath(os.path.dirname(__file__))
    print(root_path)
    store = os.path.join(root_path, 'tmp')
    from pathlib import Path
    Path(store).mkdir(parents=True, exist_ok=True)

    ORIGINAL_PATH = 'https://www.cehq.gouv.qc.ca/hydrometrie/historique_donnees/ListeStation.asp?regionhydro=$&Tri=Non'
    stations = get_available_stations_from_cehq(ORIGINAL_PATH)
    # load_files_from_cehq(stations,
    #                     store=store)
    metadata_df = parse_metadata_from_cehq_files(stations,
                                                 store=store)
    all_dfs = parse_data_from_cehq_files(metadata_df,
                                         store=store)
    df_to_sql(all_dfs)
    delete_files_in_store(store=store)


if __name__ == '__main__':
    main()

