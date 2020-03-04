from urllib.request import urlopen
import pandas as pd
import re
import numpy as np
import os
from requests import get
from requests.exceptions import RequestException
from contextlib import closing
from bs4 import BeautifulSoup
import datetime
from hydrodatahub.database.elements.bassin import Bassin
import geopandas as gpd
from config import Config


class StationParserCEHQ:
    """

    """

    def __init__(self,
                 url: str,
                 station_name: str,
                 encoding: str = "ISO-8859-1",

                 ):

        self.filename: str = url
        self.encoding: str = encoding
        self.station_name: str = station_name
        self.content: list = self.open_file(url, encoding)
        self.regularisation: str = self.content[3][15:].split()[-1]
        self.superficie: float = float(self.content[3][15:].split()[0])
        self.numero_station: str = self.content[2].split()[1]
        self.nom_station: str = self.get_station_name()
        self.latitude: float = self.get_lat_long()[0]
        self.longitude: float = self.get_lat_long()[1]
        self.values: pd.Dataframe = self.get_values()
        self.date_debut: str = self.get_start_end_date()[0]
        self.date_fin: str = self.get_start_end_date()[1]
        self.type_serie: str = self.get_type_serie()[0]
        self.nom_equivalent: str = self.get_equivalent_name_and_source()[0]
        self.pas_de_temps: str = '1_J'
        self.aggregation: str = "moy"
        self.unites: str = self.get_type_serie()[1]
        self.source: str = self.get_equivalent_name_and_source()[1]
        self.province: str = "QC"
        self.geom = self.get_geom()

    @staticmethod
    def open_file(filename, encoding) -> list:
        """

        :param filename:
        :param encoding:
        :return:
        """
        with urlopen(filename) as f:
            return f.read().decode(encoding).splitlines()

    def get_geom(self):
        """

        :return:
        """
        url = os.path.join(Config.GEOJSON_BUCKET,
                           'MELCC/json',
                           self.numero_station,
                           self.numero_station + '.json')
        geom = None

        try:
            gdf = gpd.read_file(url)
            geom = gdf.iloc[0].geometry
        except Exception:
            pass
        return geom

    def get_station_name(self) -> str:
        """

        :param filename:
        :param encoding:
        :return:
        """
        if self.station_name:
            nom_station = self.station_name
        else:
            full_description_line = self.content[2].split('-')[0]
            station_car_index = full_description_line.find(self.numero_station)
            nom_station = full_description_line[station_car_index+6:].strip()
        return nom_station

    def get_lat_long(self) -> list:
        """

        :param filename:
        :param encoding:
        :return:
        """
        lat_long = []
        latlng_coordinates = self.content[4][23:-1].split()
        if len(latlng_coordinates) < 5:
            latlng_coordinates = [x for x in latlng_coordinates if x]
            lat_long =  [float(latlng_coordinates[0]), float(latlng_coordinates[2])]
        elif len(latlng_coordinates) >= 5:
            latlng_coordinates = [re.sub(r'[^-\d]', '', coord) for coord in latlng_coordinates]
            latlng_coordinates = [x for x in latlng_coordinates if x]
            lat_long = [float(latlng_coordinates[0]) +
                        float(latlng_coordinates[1]) / 60 +
                        float(latlng_coordinates[2]) / 3600,
                        float(latlng_coordinates[3]) -
                        float(latlng_coordinates[4]) / 60 -
                        float(latlng_coordinates[5]) / 3600]
        return lat_long

    def get_values(self) -> pd.DataFrame:
        """

        :param filename:
        :param encoding:
        :return:
        """
        df = pd.DataFrame(self.content[22:]).fillna(np.nan)[0].str.split(" +", expand=True).iloc[:, 1:3]
        df.columns = ['date', 'value']
        df['value'] = df['value'].apply(pd.to_numeric, errors='coerce')
        df = df.set_index('date')
        df.index = pd.to_datetime(df.index)
        df.index = df.index.tz_localize("America/Montreal", ambiguous='infer', nonexistent='shift_forward')
        df.sort_index(inplace=True)
        return df

    def get_start_end_date(self) -> list:
        """

        :param filename:
        :param encoding:
        :return:
        """
        debut = self.values['value'].dropna().index[0]
        fin = self.values['value'].dropna().index[-1]
        return [debut, fin]

    def get_type_serie(self) -> list:
        """

        :param filename:
        :param encoding:
        :return:
        """
        type_serie_id = self.filename.split('/')[-1].split('.')[0][-1]
        return ["Debit", "m3/s"] if type_serie_id is "Q" else ['Niveau', "m"]

    def get_equivalent_name_and_source(self):
        root_path = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
        df = pd.read_csv(os.path.join(root_path, 'offline_data/equivalent_name_stations.csv'))

        equiv_name = df[df['MDDELCC'] == str(int(self.numero_station))]['HYDAT']
        if not any(equiv_name):
            equiv_name = ""
        else:
            equiv_name = equiv_name.values[0]
        source = df[df['MDDELCC'] == str(int(self.numero_station))]['Source']
        if not any(source):
            source = "MINISTERE DE L'ENVIRONNEMENT DU QUEBEC"
        else:
            source = source.values[0]
        if "".__eq__(source):
            source = "MINISTERE DE L'ENVIRONNEMENT DU QUEBEC"
        return [equiv_name, source]


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


def get_available_stations_from_cehq(url='https://www.cehq.gouv.qc.ca/hydrometrie/historique_donnees/ListeStation.asp?regionhydro=$&Tri=Non',
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


def import_cehq_to_sql(station):
    """

    :param station:
    :return:
    """
    CEHQ_URL = "https://www.cehq.gouv.qc.ca/depot/historique_donnees/fichier/"

    try:
        sta = StationParserCEHQ(url=CEHQ_URL + os.path.basename(station[0].strip()) + '_Q.txt',
                                station_name=station[1].strip())
        b = Bassin(sta)
        b.to_sql()
    except Exception:
        print(station[0].strip())
        pass
    # try:
    #     sta = StationParserCEHQ(CEHQ_URL + os.path.basename(station[0].strip()) + '_N.txt')
    #     b = Bassin(sta)
    #     b.to_sql()
    # except Exception:
    #     pass


if __name__ == '__main__':
    CEHQ_URL = "https://www.cehq.gouv.qc.ca/depot/historique_donnees/fichier/"
    station = '010802'
    sta = StationParserCEHQ(CEHQ_URL + os.path.basename(station) + '_Q.txt',
                            '010802')
    print(sta.values)