from urllib.request import urlopen
import pandas as pd
import re
import numpy as np
import os
from requests import get
from requests.exceptions import RequestException
from contextlib import closing
from bs4 import BeautifulSoup
from hydrodatahub.database.connectors import SQLAlchemyDBConnection
from hydrodatahub.database.elements.bassin import Bassin
import geopandas as gpd
from config import Config
from hydrodatahub.models import bassin, concatenations, meta_series, don_series
import os
from sqlalchemy.dialects import postgresql


class Concatenations:
    """

    """

    def __init__(self,
                 df: pd.Series
                 ):
        self.stations_list: pd.Series = self.get_stations_list(df)
        self.station_values: pd.DataFrame = self.get_values_from_station_numbers()
        self.metadata: pd.DataFrame = self.get_metadata_from_station_numbers()
        self.concatenation_results: list = self.data_concatenation()
        self.content: list = self.get_transposition_site_metadata()
        self.superficie: float = self.content[0].superficie.values[0]
        self.numero_station: str = 'C_' + '_'.join(self.concatenation_results[1])
        self.transposition_numero_station: str = self.content[0].numero_station.values[0]
        self.nom_station: str = self.content[0].nom_station.values[0]
        self.list_stations: list = self.concatenation_results[1]
        self.regularisation: str = self.content[0].regularisation.values[0]
        self.latitude: float = self.content[0].latitude.values[0]
        self.longitude: float = self.content[0].longitude.values[0]
        self.values: pd.Dataframe = self.concatenation_results[0]
        self.date_debut: str = self.get_start_end_date()[0]
        self.date_fin: str = self.get_start_end_date()[1]
        self.type_serie: str = self.content[1].type_serie.values[0]
        self.nom_equivalent: str = ''
        self.pas_de_temps: str = '1_J'
        self.aggregation: str = 'moy'
        self.unites: str = self.content[1].unites.values[0]
        self.source: str = self.content[1].source.values[0]
        self.province: str = self.content[0].province.values[0]
        self.geom = self.get_geom()

    @staticmethod
    def get_stations_list(df):
        return df.dropna().map(lambda x:
                               "{:06d}".format(int(x))
                               if not re.search('[a-zA-Z]', x)
                               else x).values

    def get_geom(self):
        """

        :return:
        """
        url = os.path.join(Config.GEOJSON_BUCKET,
                           'MELCC/json',
                           self.transposition_numero_station,
                           self.transposition_numero_station + '.json')
        geom = None

        try:
            gdf = gpd.read_file(url)
            geom = gdf.iloc[0].geometry
        except Exception:
            pass
        return geom

    def get_values_from_station_numbers(self):
        with SQLAlchemyDBConnection(Config.SQLALCHEMY_DATABASE_URI) as db:
            query = """
            SELECT d.date, d.value, b.numero_station FROM bassin b
            inner join meta_series m
            on b.uid = m.uid
            inner join don_series d
            on m.id = d.id
            WHERE b.numero_station in {}""".format(tuple(self.stations_list))
            df = pd.read_sql(query, db.session.bind).pivot_table(index='date', columns='numero_station', values='value')
            df.index = pd.to_datetime(df.index, utc=True).tz_convert('America/Montreal').tz_localize(None).normalize()
        return df

    def get_metadata_from_station_numbers(self):
        with SQLAlchemyDBConnection(Config.SQLALCHEMY_DATABASE_URI) as db:
            query = """
            SELECT b.numero_station, b.superficie FROM bassin b
            WHERE b.numero_station in {}""".format(tuple(self.stations_list))

            df_rivs = pd.read_sql(query, db.session.bind)
            df_rivs['Rapport Superficie'] = 1 / df_rivs['superficie'].divide(df_rivs['superficie'].max(), axis=0)
            df_rivs.sort_values(by='Rapport Superficie', inplace=True)
            df_rivs['Priorite'] = np.arange(1, len(df_rivs) + 1)
        return df_rivs.set_index('numero_station')

    def data_concatenation(self):
        df = self.station_values
        df_rivs = self.metadata

        df_1 = df * df_rivs['Rapport Superficie']
        df_2 = (df * df_rivs['Rapport Superficie']).notnull().astype('int')
        df_2 = df_2.replace({0: np.nan})
        priorite = (df_2 * df_rivs['Priorite']).min(axis=1).astype('int').to_frame(name='Priorite').dropna().astype(
            'float')
        a = df_rivs['Priorite'].to_dict()
        res = dict((v, k) for k, v in a.items())
        numero_station = priorite.replace(res)
        return [pd.DataFrame(index=priorite.index,
                             columns=['value'],
                             data=df_1.lookup(priorite.index, numero_station['Priorite'])).asfreq('D'),
                numero_station['Priorite'].unique()]

    def get_transposition_site_metadata(self):
        with SQLAlchemyDBConnection(Config.SQLALCHEMY_DATABASE_URI) as db:
            df_bassin = pd.read_sql(db.session.query(bassin) \
                                    .filter_by(numero_station=self.metadata.iloc[0].name) \
                                    .statement,
                                    db.session.bind)

            df_meta_series = pd.read_sql(db.session.query(meta_series) \
                                         .filter_by(uid=df_bassin.uid.values[0]) \
                                         .statement,
                                         db.session.bind)

            df = pd.read_sql(db.session.query(don_series) \
                             .filter_by(id=int(df_meta_series.id.values[0])) \
                             .statement,
                             db.session.bind)
            return [df_bassin, df_meta_series, df]

    def get_start_end_date(self) -> list:
        """

        :param filename:
        :param encoding:
        :return:
        """
        debut = self.values['value'].dropna().index[0]
        fin = self.values['value'].dropna().index[-1]
        return [debut, fin]


def get_available_stations_from_concat_file():
    """
    Get list of all available stations from cehq with station's number and name as value
    """
    return pd.read_csv(Config.CONCAT_FILENAME, dtype=object, index_col=None, header=None)


def import_concatenations_to_sql(stations_list):
    """

    :param station:
    :return:
    """

    try:
        print(stations_list)
        sta = Concatenations(df=stations_list)
        b = Bassin(sta)
        b.to_sql()

        with SQLAlchemyDBConnection(Config.SQLALCHEMY_DATABASE_URI) as db:
            connection = db.session.bind.raw_connection()
            cursor = connection.cursor()
            uid_sources = [i.uid for i in db.session.query(bassin) \
                .filter(bassin.numero_station.in_(tuple(sta.concatenation_results[1]))).all()]
            uid_conca = db.session.query(bassin) \
                .filter_by(numero_station=sta.numero_station).first().uid
            df = pd.DataFrame(uid_sources, columns=['bassin_inclus'])
            df.insert(0, column='bassin_concatene', value=uid_conca)

            insrt_stmnt = postgresql.insert(concatenations) \
                .values(df.to_dict(orient='records'))
            update_dict = {
                c.name: c
                for c in insrt_stmnt.excluded
            }
            do_nothing_stmt = insrt_stmnt.on_conflict_do_update(index_elements=['bassin_concatene', 'bassin_inclus'],
                                                                set_=update_dict)
            db.session.bind.execute(do_nothing_stmt)


    except Exception:
        print(stations_list)
        pass
    # try:
    #     sta = StationParserCEHQ(CEHQ_URL + os.path.basename(station[0].strip()) + '_N.txt')
    #     b = Bassin(sta)
    #     b.to_sql()
    # except Exception:
    #     pass


if __name__ == '__main__':
    df = get_available_stations_from_concat_file()
    stations_list = df.iloc[0]
    print(stations_list)
    conc = Concatenations(df=stations_list)
    b = Bassin(conc)
    print(conc.numero_station)
    # b.to_sql()
