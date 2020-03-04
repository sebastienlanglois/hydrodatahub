import pandas as pd
import numpy as np
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker
from config import Config
import os
from hydrodatahub.database.elements.bassin import Bassin
import geopandas as gpd


class StationParserLEGACY:
    """

    """

    def __init__(self,
                 station_number,
                 type_serie: str = 'Debit'
                 ):

        self.content: list = self.open_files(station_number)
        self.superficie: float = self.content[0].DRAINAGE_AREA.values[0]
        self.numero_station: str = station_number
        self.nom_station: str = self.content[0].STATION_NAME.values[0]
        self.regularisation: str = self.content[0].REGULATION.values[0]
        self.latitude: float = self.content[0].LATITUDE.values[0]
        self.longitude: float = self.content[0].LONGITUDE.values[0]
        self.values: pd.Dataframe = self.get_values()
        self.date_debut: str = self.get_start_end_date()[0]
        self.date_fin: str = self.get_start_end_date()[1]
        self.type_serie: str = type_serie
        self.nom_equivalent: str = self.get_equivalent_name_and_source()[0]
        self.pas_de_temps: str = '1_J'
        self.aggregation: str = 'moy'
        self.unites: str = self.get_type_serie()[1]
        self.source: str = 'HYDRO-QUEBEC EQUIPEMENT'
        self.province: str = 'QC'
        self.geom = self.get_geom()

    @staticmethod
    def open_files(station_number) -> list:
        """

        :param station_number:
        :param filename:
        :return:
        """

        bassin = pd.read_csv(os.path.join(Config.HQE_LECAGY_FOLDER, 'bassins.csv'))
        bassin = bassin[bassin['STATION_NUMBER'].isin([station_number])]
        meta_series = pd.read_csv(os.path.join(Config.HQE_LECAGY_FOLDER, 'meta_ts.csv'))
        meta_series = meta_series[meta_series['ID_POINT'].isin([bassin['ID_POINT']])]

        don_series = pd.read_csv(os.path.join(Config.HQE_LECAGY_FOLDER, 'cehq_legacy_data.csv'))
        don_series = don_series[don_series['ID_TIME_SERIE'].isin([meta_series['ID_TIME_SERIE']])]


        return [bassin, meta_series, don_series]

    def get_geom(self):
        """

        :return:
        """
        url = os.path.join(Config.GEOJSON_BUCKET,
                           'LEGACY/json',
                           self.numero_station,
                           self.numero_station + '.json')
        geom = None

        try:
            gdf = gpd.read_file(url)
            geom = gdf.iloc[0].geometry
        except Exception:
            pass
        return geom

    def get_values(self) -> pd.DataFrame:
        """

        :param type_serie:
        :return:
        """

        df = self.content[2].drop(columns=['ID_TIME_SERIE'])
        df.columns = ['date', 'value']
        df['value'] = df['value'].apply(pd.to_numeric, errors='coerce')
        df = df.set_index('date')
        df.index = pd.to_datetime(df.index, utc=True)
        df.index = df.index.tz_convert("America/Montreal")
        print(df.index)
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

        return ["Debit", "m3/s"] if self.type_serie is "Debit" else ['Niveau', "m"]

    def get_equivalent_name_and_source(self):
        root_path = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
        df = pd.read_csv(os.path.join(root_path, 'offline_data/equivalent_name_stations.csv'))

        equiv_name = df[df['HYDAT'] == self.numero_station]['MDDELCC']
        if not any(equiv_name):
            equiv_name = ""
        else:
            equiv_name = "{:06d}".format(int(equiv_name.values[0]))

        source = df[df['HYDAT'] == self.numero_station]['Source']
        if not any(source):
            source = "WATER SURVEY OF CANADA (DOE) (CANADA)"
        else:
            source = source.values[0]
        if "".__eq__(source):
            source = "WATER SURVEY OF CANADA (DOE) (CANADA)"
        return [equiv_name, source]


class SQLAlchemyDBConnection(object):
    """SQLAlchemy database connection"""

    def __init__(self, connection_string):
        self.connection_string = connection_string
        self.session = None

    def __enter__(self):
        engine = create_engine(self.connection_string)
        Session = sessionmaker()
        self.session = Session(bind=engine)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.close()


def get_available_stations_from_legacy():
    """
    Get list of all available stations from cehq with station's number and name as value
    """
    return pd.read_csv(os.path.join(Config.HQE_LECAGY_FOLDER, 'bassins.csv'))['STATION_NUMBER']


def import_legacy_to_sql(station):
    """

    :param station:
    :return:
    """

    try:
        sta = StationParserLEGACY(station_number=station.strip())
        b = Bassin(sta)
        b.to_sql()
    except Exception:
        print(station[0].strip())
        pass
        # try:
        #     sta = StationParserHYDAT(filename=hydat_sqlite,
        #                              station_number=station.strip(),
        #                              type_serie='Niveau')
        #     b = Bassin(sta)
        #     b.to_sql()
        # except Exception:
        #     pass

if __name__ == '__main__':
    bassins = get_available_stations_from_legacy()
    station = bassins[2]
    sta = StationParserLEGACY(station_number=station.strip())
    b = Bassin(sta)
    b.to_sql()
    # all_dfs = parse_data_from_hydat_files('/home/slanglois/Downloads/Hydat_sqlite3_20191016/Hydat.sqlite3',
    #                                   regions_list=['QC', 'ON', 'NB', 'NL'])
    # df_to_sql(all_dfs)
    # #delete_files_in_store()
